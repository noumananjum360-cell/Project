"""A tiny CenterNet-style detector implemented and trained in pure NumPy.

Why NumPy? The app must train customer models *offline* on an ordinary office
PC without installing PyTorch/CUDA. This network is small (~60k parameters),
fast on CPU (a few ms per frame through ONNX Runtime) and good enough to learn
one site's bags and cartons from a few hundred annotated frames. Customers that
have the optional Ultralytics stack installed can train a full YOLO model
instead (see trainer.py); both export to ONNX and plug into the same runtime.

Architecture (input 3 x H x W, output stride 4):
    conv3x3/s2 16 -> conv3x3/s2 32 -> conv3x3 32 -> conv3x3 d2 32 -> conv3x3 d4 32
    -> conv3x3 d8 32 -> conv1x1 (C heatmaps + 2 log-size channels)
Receptive field ~125 px at the input resolution.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass

import numpy as np

STRIDE = 4
LAYERS = [  # (cin, cout, k, stride, dilation, relu)
    (3, 16, 3, 2, 1, True),
    (16, 32, 3, 2, 1, True),
    (32, 32, 3, 1, 1, True),
    (32, 32, 3, 1, 2, True),
    (32, 32, 3, 1, 4, True),
    (32, 32, 3, 1, 8, True),
]


class Conv:
    def __init__(self, cin, cout, k, stride, dil, relu, rng):
        fan_in = cin * k * k
        self.W = (rng.standard_normal((cout, cin, k, k)) * math.sqrt(2.0 / fan_in)).astype(np.float32)
        self.b = np.zeros(cout, np.float32)
        self.k, self.s, self.d, self.relu = k, stride, dil, relu
        self.pad = dil * (k // 2)
        self.cache = None

    def forward(self, x, train=False):
        n, c, h, w = x.shape
        k, s, d, p = self.k, self.s, self.d, self.pad
        ho = (h + 2 * p - d * (k - 1) - 1) // s + 1
        wo = (w + 2 * p - d * (k - 1) - 1) // s + 1
        xp = np.pad(x, ((0, 0), (0, 0), (p, p), (p, p))) if p else x
        if k == 1:
            cols = xp[:, :, ::s, ::s].transpose(0, 2, 3, 1).reshape(-1, c)
        else:
            sl = [xp[:, :, i * d: i * d + s * (ho - 1) + 1: s, j * d: j * d + s * (wo - 1) + 1: s]
                  for i in range(k) for j in range(k)]
            cols = np.stack(sl, axis=2).transpose(0, 3, 4, 1, 2).reshape(n * ho * wo, c * k * k)
        out = cols @ self.W.reshape(self.W.shape[0], -1).T + self.b
        if self.relu:
            out = np.maximum(out, 0)
        out = out.reshape(n, ho, wo, -1).transpose(0, 3, 1, 2)
        if train:
            self.cache = (x.shape, xp.shape, cols, out, ho, wo)
        return np.ascontiguousarray(out)

    def backward(self, dout):
        xshape, xpshape, cols, out, ho, wo = self.cache
        n, c, h, w = xshape
        k, s, d, p = self.k, self.s, self.d, self.pad
        if self.relu:
            dout = dout * (out > 0)
        co = self.W.shape[0]
        d2 = dout.transpose(0, 2, 3, 1).reshape(-1, co)
        self.dW = (d2.T @ cols).reshape(self.W.shape)
        self.db = d2.sum(0)
        dcols = d2 @ self.W.reshape(co, -1)
        dxp = np.zeros(xpshape, np.float32)
        if k == 1:
            dxp[:, :, ::s, ::s] += dcols.reshape(n, ho, wo, c).transpose(0, 3, 1, 2)
        else:
            dc = dcols.reshape(n, ho, wo, c, k * k).transpose(0, 3, 4, 1, 2)
            idx = 0
            for i in range(k):
                for j in range(k):
                    dxp[:, :, i * d: i * d + s * (ho - 1) + 1: s, j * d: j * d + s * (wo - 1) + 1: s] += dc[:, :, idx]
                    idx += 1
        self.cache = None
        return dxp[:, :, p:p + h, p:p + w] if p else dxp


class CenterNetLite:
    def __init__(self, classes: list[str], input_hw=(192, 320), seed=0):
        self.classes = list(classes)
        self.input_hw = tuple(input_hw)
        rng = np.random.default_rng(seed)
        self.layers = [Conv(*cfg, rng) for cfg in LAYERS]
        self.head = Conv(LAYERS[-1][1], len(classes) + 2, 1, 1, 1, False, rng)
        # focal-loss prior: start heatmaps near 0.01
        self.head.b[: len(classes)] = -4.6
        self.head.W *= 0.1
        self.adam_t = 0
        self.m = None
        self.v = None

    @property
    def params(self):
        out = []
        for l in self.layers + [self.head]:
            out += [l.W, l.b]
        return out

    def grads(self):
        out = []
        for l in self.layers + [self.head]:
            out += [l.dW, l.db]
        return out

    def forward(self, x, train=False):
        for l in self.layers:
            x = l.forward(x, train)
        return self.head.forward(x, train)

    def backward(self, dout):
        d = self.head.backward(dout)
        for l in reversed(self.layers):
            d = l.backward(d)

    # --------------------------------------------------------------- training step
    def loss_and_grad(self, raw, heat_t, size_t, mask):
        """Penalty-reduced focal loss (CenterNet) + L1 on log sizes at centres."""
        nc = len(self.classes)
        logits = raw[:, :nc]
        p = 1 / (1 + np.exp(-np.clip(logits, -30, 30)))
        p = np.clip(p, 1e-4, 1 - 1e-4)
        pos = heat_t >= 0.999
        npos = max(1.0, float(pos.sum()))
        neg_w = (1 - heat_t) ** 4
        lpos = -((1 - p) ** 2) * np.log(p)
        lneg = -neg_w * (p ** 2) * np.log(1 - p)
        loss_h = (lpos[pos].sum() + lneg[~pos].sum()) / npos
        # d/dlogit
        gpos = (1 - p) ** 2 * (2 * p * np.log(p) - (1 - p))  # derivative of lpos wrt logit
        # lneg = -w p^2 log(1-p)  =>  dl/dz = -w [2 p^2 (1-p) log(1-p) - p^3]
        gneg = -neg_w * (2 * p * p * (1 - p) * np.log(1 - p) - p ** 3)
        g = np.where(pos, gpos, gneg) / npos
        pred_s = raw[:, nc:]
        m = mask[:, None]
        nm = max(1.0, float(mask.sum()))
        diff = (pred_s - size_t) * m
        loss_s = np.abs(diff).sum() / nm
        dsize = np.sign(diff) / nm * 0.1
        dout = np.concatenate([g, dsize], axis=1).astype(np.float32)
        return loss_h + 0.1 * loss_s, loss_h, loss_s, dout

    def adam_step(self, lr, wd=1e-4, b1=0.9, b2=0.999, eps=1e-8):
        params, grads = self.params, self.grads()
        if self.m is None:
            self.m = [np.zeros_like(p) for p in params]
            self.v = [np.zeros_like(p) for p in params]
        self.adam_t += 1
        t = self.adam_t
        for i, (p, g) in enumerate(zip(params, grads)):
            g = np.clip(g, -5, 5)
            self.m[i] = b1 * self.m[i] + (1 - b1) * g
            self.v[i] = b2 * self.v[i] + (1 - b2) * g * g
            mh = self.m[i] / (1 - b1 ** t)
            vh = self.v[i] / (1 - b2 ** t)
            p -= lr * (mh / (np.sqrt(vh) + eps) + wd * p * (p.ndim > 1))

    # --------------------------------------------------------------- weights io
    def state(self) -> dict:
        return {"classes": self.classes, "input_hw": list(self.input_hw),
                "params": [p.copy() for p in self.params]}

    def load_state(self, st: dict):
        for p, q in zip(self.params, st["params"]):
            p[...] = q

    def to_onnx(self, path: str, extra_meta: dict | None = None):
        export_onnx(self, path, extra_meta)

    @classmethod
    def from_onnx(cls, path: str) -> "CenterNetLite":
        import onnx
        from onnx import numpy_helper
        m = onnx.load(path)
        meta = {p.key: p.value for p in m.metadata_props}
        classes = json.loads(meta["classes"])
        hw = json.loads(meta.get("input_hw", "[192, 320]"))
        net = cls(classes, hw)
        inits = {i.name: numpy_helper.to_array(i) for i in m.graph.initializer}
        for li, l in enumerate(net.layers + [net.head]):
            l.W[...] = inits[f"W{li}"]
            l.b[...] = inits[f"B{li}"]
        return net


def preprocess(frame_bgr: np.ndarray, input_hw) -> np.ndarray:
    import cv2
    h, w = input_hw
    x = cv2.resize(frame_bgr, (w, h), interpolation=cv2.INTER_AREA)
    x = x[:, :, ::-1].astype(np.float32) / 255.0  # RGB 0..1
    return x.transpose(2, 0, 1)[None]


def export_onnx(net: CenterNetLite, path: str, extra_meta: dict | None = None):
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    nodes, inits = [], []
    cur = "images"
    for li, l in enumerate(net.layers + [net.head]):
        inits += [numpy_helper.from_array(l.W, f"W{li}"), numpy_helper.from_array(l.b, f"B{li}")]
        out = f"c{li}"
        nodes.append(helper.make_node("Conv", [cur, f"W{li}", f"B{li}"], [out], kernel_shape=[l.k, l.k],
                                      strides=[l.s, l.s], dilations=[l.d, l.d], pads=[l.pad] * 4))
        if l.relu:
            nodes.append(helper.make_node("Relu", [out], [out + "r"]))
            out += "r"
        cur = out
    nc = len(net.classes)
    inits += [numpy_helper.from_array(np.array([0], np.int64), "s0"),
              numpy_helper.from_array(np.array([nc], np.int64), "s1"),
              numpy_helper.from_array(np.array([nc + 2], np.int64), "s2"),
              numpy_helper.from_array(np.array([1], np.int64), "ax")]
    nodes += [
        helper.make_node("Slice", [cur, "s0", "s1", "ax"], ["heat_logits"]),
        helper.make_node("Sigmoid", ["heat_logits"], ["heat"]),
        helper.make_node("Slice", [cur, "s1", "s2", "ax"], ["size"]),
        helper.make_node("Concat", ["heat", "size"], ["output"], axis=1),
    ]
    h, w = net.input_hw
    graph = helper.make_graph(
        nodes, "nomload_centernet_lite",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, ["N", 3, h, w])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, ["N", nc + 2, h // STRIDE, w // STRIDE])],
        inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)], producer_name="nomload")
    model.ir_version = 8
    meta = {"format": "nomload-centernet", "classes": json.dumps(net.classes),
            "input_hw": json.dumps(list(net.input_hw)), "stride": str(STRIDE),
            "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    meta.update({k: str(v) for k, v in (extra_meta or {}).items()})
    for k, v in meta.items():
        e = model.metadata_props.add()
        e.key, e.value = k, v
    onnx.checker.check_model(model)
    onnx.save(model, path)


# ------------------------------------------------------------------ targets
def gaussian_targets(labels, nc, input_hw, src_hw):
    """labels: [(cls, x0, y0, x1, y1)] in source pixel coords."""
    h, w = input_hw
    oh, ow = h // STRIDE, w // STRIDE
    sy, sx = h / src_hw[0], w / src_hw[1]
    heat = np.zeros((nc, oh, ow), np.float32)
    size = np.zeros((2, oh, ow), np.float32)
    mask = np.zeros((oh, ow), np.float32)
    yy, xx = np.mgrid[0:oh, 0:ow].astype(np.float32)
    for c, x0, y0, x1, y1 in labels:
        bw, bh = (x1 - x0) * sx / STRIDE, (y1 - y0) * sy / STRIDE
        if bw < 0.5 or bh < 0.5:
            continue
        cx, cy = (x0 + x1) / 2 * sx / STRIDE, (y0 + y1) / 2 * sy / STRIDE
        ix, iy = int(min(ow - 1, max(0, cx))), int(min(oh - 1, max(0, cy)))
        sig_x, sig_y = max(0.6, bw / 6), max(0.6, bh / 6)
        g = np.exp(-(((xx - ix) ** 2) / (2 * sig_x ** 2) + ((yy - iy) ** 2) / (2 * sig_y ** 2)))
        heat[c] = np.maximum(heat[c], g)
        heat[c, iy, ix] = 1.0
        size[:, iy, ix] = (math.log(bw), math.log(bh))
        mask[iy, ix] = 1.0
    return heat, size, mask


def augment(img, labels, rng: np.random.Generator):
    import cv2
    h, w = img.shape[:2]
    if rng.random() < 0.5:
        img = img[:, ::-1].copy()
        labels = [(c, w - 1 - x1, y0, w - 1 - x0, y1) for c, x0, y0, x1, y1 in labels]
    a = rng.uniform(0.7, 1.3)
    b = rng.uniform(-30, 30)
    img = img.astype(np.float32) * a + b
    if rng.random() < 0.3:
        img = img * rng.uniform(0.85, 1.15, (1, 1, 3))
    if rng.random() < 0.25:
        img = cv2.GaussianBlur(img, (3, 3), 0)
    if rng.random() < 0.3:
        # random zoom around the centre
        s = rng.uniform(0.8, 1.2)
        cx, cy = w / 2 + rng.uniform(-40, 40), h / 2 + rng.uniform(-20, 20)
        m = np.float32([[s, 0, (1 - s) * cx], [0, s, (1 - s) * cy]])
        img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
        labels = [(c, x0 * s + m[0, 2], y0 * s + m[1, 2], x1 * s + m[0, 2], y1 * s + m[1, 2])
                  for c, x0, y0, x1, y1 in labels]
        labels = [(c, max(0, x0), max(0, y0), min(w - 1, x1), min(h - 1, y1)) for c, x0, y0, x1, y1 in labels
                  if min(w - 1, x1) - max(0, x0) > 4 and min(h - 1, y1) - max(0, y0) > 4]
    img = np.clip(img + rng.normal(0, rng.uniform(0, 6), img.shape), 0, 255).astype(np.uint8)
    return img, labels


@dataclass
class TrainConfig:
    iterations: int = 3000
    batch: int = 8
    lr: float = 2e-3
    seed: int = 0
    log_every: int = 50


def train(net: CenterNetLite, samples: list, cfg: TrainConfig, progress=None, should_stop=None) -> dict:
    """samples: list of (bgr_image, labels[(cls, x0,y0,x1,y1)]). Returns history."""
    import cv2
    rng = np.random.default_rng(cfg.seed)
    h, w = net.input_hw
    nc = len(net.classes)
    hist = {"loss": []}
    t0 = time.time()
    run = None
    for it in range(cfg.iterations):
        if should_stop and should_stop():
            break
        idx = rng.integers(0, len(samples), cfg.batch)
        xs, hs, ss, ms = [], [], [], []
        for i in idx:
            img, labels = samples[i]
            img, labels = augment(img, labels, rng)
            x = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)[:, :, ::-1].astype(np.float32) / 255.0
            xs.append(x.transpose(2, 0, 1))
            ht, st, mk = gaussian_targets(labels, nc, (h, w), img.shape[:2])
            hs.append(ht); ss.append(st); ms.append(mk)
        x = np.stack(xs).astype(np.float32)
        raw = net.forward(x, train=True)
        loss, lh, ls, dout = net.loss_and_grad(raw, np.stack(hs), np.stack(ss), np.stack(ms))
        net.backward(dout)
        warm = min(1.0, (it + 1) / 100)
        lr = cfg.lr * warm * (0.5 * (1 + math.cos(math.pi * it / cfg.iterations)) * 0.95 + 0.05)
        net.adam_step(lr)
        run = loss if run is None else 0.95 * run + 0.05 * loss
        if it % cfg.log_every == 0 or it == cfg.iterations - 1:
            hist["loss"].append((it, float(run)))
            if progress:
                progress(it + 1, cfg.iterations, float(run), time.time() - t0)
    return hist
