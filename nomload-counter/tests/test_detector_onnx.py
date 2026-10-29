import numpy as np

from nomload.training.nn import CenterNetLite


def test_onnx_export_matches_numpy(tmp_path):
    net = CenterNetLite(["bag", "carton"], (64, 96), seed=3)
    x = np.random.default_rng(0).random((1, 3, 64, 96)).astype(np.float32)
    raw = net.forward(x)
    p = tmp_path / "m.onnx"
    net.to_onnx(str(p))
    import onnxruntime as ort
    out = ort.InferenceSession(str(p), providers=["CPUExecutionProvider"]).run(None, {"images": x})[0]
    nc = 2
    assert np.allclose(out[:, :nc], 1 / (1 + np.exp(-raw[:, :nc])), atol=1e-4)
    assert np.allclose(out[:, nc:], raw[:, nc:], atol=1e-3)
    back = CenterNetLite.from_onnx(str(p))
    assert np.allclose(back.forward(x), raw, atol=1e-5)


def test_decode_centernet_peaks():
    from nomload.core.detector import decode_centernet
    out = np.zeros((3, 20, 30), np.float32)
    out[0, 5, 10] = 0.9
    out[0, 5, 11] = 0.5   # neighbour, suppressed by max-pool
    out[0, 15, 20] = 0.8
    out[1:, :, :] = np.log(4.0)
    dets = decode_centernet(out, ["bag"], 4, 1.0, 1.0, 0.3)
    assert len(dets) == 2 and dets[0].score == np.float32(0.9)
    assert abs((dets[0].x1 - dets[0].x0) - 16) < 1e-3


def test_gradient_check_small():
    from nomload.training.nn import gaussian_targets
    net = CenterNetLite(["a"], (32, 48), seed=1)
    x = np.random.default_rng(1).random((1, 3, 32, 48)).astype(np.float32)
    ht, st, mk = gaussian_targets([(0, 8, 8, 30, 20)], 1, (32, 48), (32, 48))
    H, S, M = ht[None], st[None], mk[None]
    raw = net.forward(x, True)
    _l, *_r, d = net.loss_and_grad(raw, H, S, M)
    net.backward(d)
    W = net.head.W
    g = net.head.dW[0, 0, 0, 0]
    e = 1e-2
    W[0, 0, 0, 0] += e
    lp = net.loss_and_grad(net.forward(x), H, S, M)[0]
    W[0, 0, 0, 0] -= 2 * e
    lm = net.loss_and_grad(net.forward(x), H, S, M)[0]
    W[0, 0, 0, 0] += e
    assert abs((lp - lm) / (2 * e) - g) < 5e-3
