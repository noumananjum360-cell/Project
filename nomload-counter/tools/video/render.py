"""NomLoad Counter - 3 minute introduction video (motion graphics renderer).

Renders 1920x1080 @ 30 fps with QPainter and pipes raw frames to ffmpeg.
Uses the real application screenshots, the official logo and live output of the
NomLoad counting engine on the sample videos.
"""
import json
import math
import os
import random
import subprocess
import sys
import wave

os.environ["QT_QPA_PLATFORM"] = "offscreen"
V = os.environ.get("NOMLOAD_VIDEO_WORK", os.path.dirname(os.path.abspath(__file__)))
SCR = os.environ.get("NOMLOAD_MANUAL_WORK", os.path.join(os.path.dirname(V), "mw")) + "/img"
R = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, R)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

app = QGuiApplication(sys.argv)
W, H, FPS = 1920, 1080, 30
NAVY = QColor("#1B2A4E")
NAVY_D = QColor("#121C36")
NAVY_L = QColor("#26386A")
AMBER = QColor("#E8A33D")
WHITE = QColor("#FFFFFF")
GREEN = QColor("#1F9D55")
RED = QColor("#D64545")
MUTED = QColor("#9AA5BC")
FONT = "Inter"


# ------------------------------------------------------------------ easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_back(t, s=1.70158):
    t = clamp(t)
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def prog(t, start, dur):
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


def font(px, weight=QFont.Weight.Normal, spacing=0.0):
    f = QFont(FONT)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


BOLD = QFont.Weight.Bold
XBOLD = QFont.Weight.ExtraBold
SEMI = QFont.Weight.DemiBold


# ------------------------------------------------------------------ assets
def load(name):
    img = QImage(os.path.join(SCR, name + ".png"))
    assert not img.isNull(), name
    return img


SHOT = {n: load(n) for n in ["03_dashboard", "04_live_bays", "05_live_single_bay", "06_gate_pass_picker",
                             "08_supervisor_approval", "09_result_cleared", "10_result_mismatch", "12_sessions_gate_passes",
                             "15_history", "16_session_summary", "17_session_snapshots", "18_session_evidence",
                             "19_session_audit", "20_reports", "22_cameras", "23_add_camera_rtsp", "24_calibration",
                             "26_training_annotate", "27_training_train", "29_users", "35_dark_live", "02_login",
                             "40_certificate_pdf", "41_daily_pdf"]}
LOGO_SVG = open(os.path.join(R, "nomload", "assets", "logo.svg")).read()

ICON_PATHS = {}
from nomload.ui.icons import PATHS as ICON_PATHS  # noqa: E402,F811


def svg_image(svg: str, size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return img


_icon_cache = {}


def icon(name, color="#FFFFFF", size=96):
    k = (name, color, size)
    if k not in _icon_cache:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
               f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICON_PATHS[name]}</svg>')
        _icon_cache[k] = svg_image(svg, size)
    return _icon_cache[k]


def bgr_qimage(fr):
    rgb = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


# ------------------------------------------------------------------ real engine footage
def engine_clip(video, calib_key, seconds, start_frame=0, out_w=1280):
    """Run the real NomLoad counting engine and return annotated frames + running totals."""
    from nomload.core.detector import ModelRegistry
    from nomload.core.geometry import CountGeometry
    from nomload.core.pipeline import CountingEngine, EngineConfig
    reg = ModelRegistry()
    reg.load(os.path.join(R, "models", "starter_detector.onnx"))
    calib = json.load(open(os.path.join(R, "samples", "calibration.json")))
    eng = CountingEngine(reg, CountGeometry.from_dict(calib[calib_key]), EngineConfig(max_width=out_w))
    cap = cv2.VideoCapture(os.path.join(R, "samples", video))
    frames, totals, total = [], [], 0
    i = 0
    need = int(seconds * 15) + start_frame
    while i < need:
        ok, fr = cap.read()
        if not ok:
            break
        fr = cv2.resize(fr, (out_w, out_w * 9 // 16), interpolation=cv2.INTER_CUBIC)
        res = eng.process(fr, ts=1_760_000_000 + i / 15)
        total += sum(e.direction for e in res.events)
        if i >= start_frame:
            frames.append(bgr_qimage(eng.annotate(res)))
            totals.append(total)
        i += 1
    return frames, totals


def plate_frames(seconds):
    cap = cv2.VideoCapture(os.path.join(R, "samples", "plate_cam_LES-4721.mp4"))
    out = []
    while len(out) < seconds * 15:
        ok, fr = cap.read()
        if not ok:
            break
        out.append(bgr_qimage(cv2.resize(fr, (1280, 720), interpolation=cv2.INTER_CUBIC)))
    return out


# ------------------------------------------------------------------ drawing helpers
class Pattern:
    """Slowly drifting carton-stack pattern (the NomLoad login background, animated)."""

    def __init__(self):
        self.rng = random.Random(4)
        self.highlights = [(self.rng.randint(0, 15), self.rng.randint(0, 17), self.rng.random() * 6) for _ in range(16)]

    def draw(self, p, t, dim=1.0):
        p.fillRect(0, 0, W, H, NAVY_D)
        bw, bh = 150, 76
        off_all = (t * 14) % bw
        for row in range(-1, H // bh + 2):
            off = (row % 2) * bw / 2 - off_all * (1 if row % 2 else 0.6)
            for col in range(-2, W // bw + 3):
                x, y = col * bw + off, row * bh
                c = NAVY if (row + col) % 3 else NAVY_L
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c.red(), c.green(), c.blue(), int(255 * dim)))
                p.drawRoundedRect(QRectF(x + 4, y + 4, bw - 8, bh - 8), 7, 7)
                p.setBrush(QColor(255, 255, 255, int(9 * dim)))
                p.drawRect(QRectF(x + bw / 2 - 5, y + 4, 10, bh - 8))
        # amber "counted" cartons that light up and fade
        for (cx, cy, ph) in self.highlights:
            a = 0.5 + 0.5 * math.sin(t * 1.1 + ph)
            x = cx * bw + (cy % 2) * bw / 2 - off_all * (1 if cy % 2 else 0.6)
            x = (x + 2 * bw) % (W + 3 * bw) - 2 * bw
            y = cy * bh
            p.setBrush(QColor(232, 163, 61, int(140 * a * dim)))
            p.drawRoundedRect(QRectF(x + 4, y + 4, bw - 8, bh - 8), 7, 7)
        g = QRadialGradient(W / 2, H / 2, W * 0.75)
        g.setColorAt(0, QColor(0, 0, 0, 0))
        g.setColorAt(1, QColor(0, 0, 0, 170))
        p.fillRect(0, 0, W, H, QBrush(g))


PATTERN = Pattern()


def soft_bg(p, t):
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0, QColor("#F4F6FA"))
    g.setColorAt(1, QColor("#E6EBF4"))
    p.fillRect(0, 0, W, H, QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(6):
        a = 0.5 + 0.5 * math.sin(t * 0.6 + i)
        p.setBrush(QColor(27, 42, 78, int(10 + 8 * a)))
        r = 260 + i * 60
        p.drawEllipse(QPointF(W * (0.15 + 0.15 * i) + 40 * math.sin(t * 0.3 + i), H * (0.2 + 0.12 * (i % 3))), r, r)


def text(p, x, y, s, f, color=WHITE, alpha=1.0, align="left", w=None):
    p.setFont(f)
    c = QColor(color)
    c.setAlphaF(clamp(alpha) * c.alphaF())
    p.setPen(c)
    fm = p.fontMetrics()
    tw = fm.horizontalAdvance(s)
    if align == "center":
        x -= tw / 2
    elif align == "right":
        x -= tw
    p.drawText(QPointF(x, y), s)
    return tw


def kinetic(p, x, y, s, f, t, start, color=WHITE, stagger=0.07, dur=0.55, align="left", rise=34):
    """Word-by-word rise + fade, like an After Effects text animator."""
    p.setFont(f)
    fm = p.fontMetrics()
    words = s.split(" ")
    space = fm.horizontalAdvance(" ")
    total = sum(fm.horizontalAdvance(w) for w in words) + space * (len(words) - 1)
    cx = x - total / 2 if align == "center" else x
    for i, wd in enumerate(words):
        k = ease_out(prog(t, start + i * stagger, dur))
        c = QColor(color)
        c.setAlphaF(k)
        p.setPen(c)
        p.drawText(QPointF(cx, y + rise * (1 - k)), wd)
        cx += fm.horizontalAdvance(wd) + space
    return total


def shadow_rect(p, r, radius=18, strength=1.0):
    for i in range(14, 0, -2):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(7 * strength)))
        p.drawRoundedRect(r.adjusted(-i, -i + 10, i, i + 10), radius + i, radius + i)


def window(p, img, r: QRectF, alpha=1.0, zoom=1.0, focus=(0.5, 0.5), radius=16, title=True):
    """App screenshot inside a clean window frame, with optional Ken-Burns zoom."""
    p.save()
    p.setOpacity(alpha)
    shadow_rect(p, r, radius, 1.4)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    p.setClipPath(path)
    p.fillRect(r, WHITE)
    bar = 34 if title else 0
    if title:
        p.fillRect(QRectF(r.x(), r.y(), r.width(), bar), QColor("#E9EDF4"))
        for i, col in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            p.setBrush(QColor(col))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(r.x() + 22 + i * 22, r.y() + bar / 2), 6, 6)
        f = font(15, SEMI)
        text(p, r.x() + r.width() / 2, r.y() + 23, "NomLoad Counter 1.0", f, QColor("#5A6475"), 1.0, "center")
    inner = QRectF(r.x(), r.y() + bar, r.width(), r.height() - bar)
    iw, ih = img.width(), img.height()
    s = max(inner.width() / iw, inner.height() / ih) * zoom
    sw, sh = iw * s, ih * s
    fx, fy = focus
    ox = inner.x() + inner.width() / 2 - sw * fx + (sw * fx - inner.width() / 2) * (1 - (zoom - 1) / max(zoom - 1, 1e-6)) \
        if zoom > 1.0001 else inner.x() + (inner.width() - sw) / 2
    oy = inner.y() + inner.height() / 2 - sh * fy if zoom > 1.0001 else inner.y() + (inner.height() - sh) / 2
    if zoom > 1.0001:
        ox = min(inner.x(), max(inner.right() - sw, inner.x() + inner.width() / 2 - sw * fx))
        oy = min(inner.y(), max(inner.bottom() - sh, inner.y() + inner.height() / 2 - sh * fy))
    p.setClipRect(inner, Qt.ClipOperation.IntersectClip)
    p.drawImage(QRectF(ox, oy, sw, sh), img)
    p.restore()


def card(p, r, alpha=1.0, color=WHITE, radius=18):
    p.save()
    p.setOpacity(alpha)
    shadow_rect(p, r, radius, 0.9)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(r, radius, radius)
    p.restore()


def pill(p, cx, cy, s, f, bg=AMBER, fg=NAVY, alpha=1.0, pad=22):
    p.save()
    p.setOpacity(alpha)
    p.setFont(f)
    tw = p.fontMetrics().horizontalAdvance(s)
    h = f.pixelSize() * 1.9
    r = QRectF(cx - tw / 2 - pad, cy - h / 2, tw + 2 * pad, h)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setPen(fg)
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, s)
    p.restore()
    return r


def callout(p, r: QRectF, t, start, label="", color=AMBER):
    """Animated highlight frame with pulsing glow and a label tag."""
    k = ease_out(prog(t, start, 0.5))
    if k <= 0:
        return
    p.save()
    grow = (1 - k) * 30
    rr = r.adjusted(-grow, -grow, grow, grow)
    pulse = 0.5 + 0.5 * math.sin((t - start) * 5)
    for i in range(3):
        c = QColor(color)
        c.setAlpha(int((60 - i * 18) * k * (0.6 + 0.4 * pulse)))
        p.setPen(QPen(c, 10 + i * 8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rr, 14, 14)
    c = QColor(color)
    c.setAlphaF(k)
    p.setPen(QPen(c, 4))
    p.drawRoundedRect(rr, 14, 14)
    if label:
        pill(p, rr.center().x(), rr.top() - 26, label, font(22, BOLD), color, NAVY if color == AMBER else WHITE, k)
    p.restore()


def draw_logo(p, cx, cy, size, t, start=0.0):
    """Official logo, built piece by piece: brackets draw in, cartons drop and stack."""
    s = size / 256.0
    p.save()
    p.translate(cx - size / 2, cy - size / 2)
    p.scale(s, s)
    navy = QColor("#1B2A4E")
    pen = QPen(navy, 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    k = ease_in_out(prog(t, start, 0.8))
    corners = [((36, 84), (36, 54), (54, 36), (84, 36)), ((172, 36), (202, 36), (220, 54), (220, 84)),
               ((220, 172), (220, 202), (202, 220), (172, 220)), ((84, 220), (54, 220), (36, 202), (36, 172))]
    for a, b, c, d in corners:
        path = QPainterPath(QPointF(*a))
        path.lineTo(QPointF(*b))
        corner = (a[0], d[1]) if a[0] == b[0] else (d[0], a[1])
        path.quadTo(QPointF(*corner), QPointF(*c))
        path.lineTo(QPointF(*d))
        n = 40
        pts = [path.pointAtPercent(i / n) for i in range(int(n * k) + 1)]
        if len(pts) > 1:
            p.setPen(pen)
            for i in range(len(pts) - 1):
                p.drawLine(pts[i], pts[i + 1])
    boxes = [(66, 148, False), (109, 148, False), (152, 148, False), (87.5, 113, False), (130.5, 113, False),
             (109, 78, True)]
    for i, (x, y, top) in enumerate(boxes):
        st = start + 0.6 + i * 0.14
        kb = prog(t, st, 0.45)
        if kb <= 0:
            continue
        e = ease_back(kb, 2.2)
        dy = (1 - e) * -120
        p.setOpacity(clamp(kb * 3))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E8A33D") if top else navy)
        p.drawRoundedRect(QRectF(x, y + dy, 38, 30), 5, 5)
        p.setBrush(QColor("#F6C878") if top else QColor("#3E5A94"))
        p.drawRect(QRectF(x + 16, y + dy, 6, 30))
    p.setOpacity(1.0)
    # glow on the counted (amber) carton
    kg = prog(t, start + 1.5, 0.6)
    if kg > 0:
        g = QRadialGradient(128, 93, 70)
        g.setColorAt(0, QColor(232, 163, 61, int(110 * (1 - abs(kg * 2 - 1)))))
        g.setColorAt(1, QColor(232, 163, 61, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(128, 93), 70, 70)
    p.restore()


def white_logo_tile(p, cx, cy, size, t, start, alpha=1.0):
    k = ease_back(prog(t, start, 0.6), 1.4)
    if k <= 0:
        return
    p.save()
    p.setOpacity(alpha * clamp(k))
    sz = size * (0.6 + 0.4 * k)
    r = QRectF(cx - sz / 2, cy - sz / 2, sz, sz)
    shadow_rect(p, r, sz * 0.18, 1.5)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawRoundedRect(r, sz * 0.18, sz * 0.18)
    p.restore()
    draw_logo(p, cx, cy, sz * 0.88, t, start + 0.2)


def caption(p, s, alpha):
    if not s or alpha <= 0:
        return
    f = font(30, SEMI)
    p.setFont(f)
    fm = p.fontMetrics()
    maxw = 1500
    words, lines, cur = s.split(), [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if fm.horizontalAdvance(trial) > maxw and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = trial
    lines.append(cur)
    lh = 42
    tot_h = lh * len(lines) + 24
    width = max(fm.horizontalAdvance(l) for l in lines) + 56
    r = QRectF(W / 2 - width / 2, H - 70 - tot_h, width, tot_h)
    p.save()
    p.setOpacity(alpha)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(10, 16, 32, 200))
    p.drawRoundedRect(r, 14, 14)
    p.setPen(WHITE)
    for i, l in enumerate(lines):
        p.drawText(QRectF(r.x(), r.y() + 12 + i * lh, r.width(), lh), Qt.AlignmentFlag.AlignCenter, l)
    p.restore()


def section_tag(p, t, label, number, light=False):
    k = ease_out(prog(t, 0.2, 0.6))
    if k <= 0:
        return
    col = NAVY if light else WHITE
    p.save()
    p.setOpacity(k)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(AMBER)
    p.drawRect(QRectF(90, 92, 6 + 54 * k, 6))
    text(p, 90, 80, f"{number:02d}", font(22, BOLD, 2), AMBER)
    text(p, 140, 80, label.upper(), font(22, SEMI, 5), col)
    p.restore()


# ------------------------------------------------------------------ scenes
class Scene:
    dark = True

    def __init__(self, name, vo_text, vo_dur, lead=0.7, tail=1.4, extra=0.0):
        self.name, self.vo_text, self.vo_dur = name, vo_text, vo_dur
        self.lead = lead
        self.dur = lead + vo_dur + tail + extra

    def draw(self, p, t):
        pass

    def captions(self, t):
        """Sentence of the voiceover being spoken at local time t."""
        if not self.vo_text:
            return "", 0
        vt = t - self.lead
        if vt < -0.2 or vt > self.vo_dur + 0.4:
            return "", 0
        sents = [s.strip() for s in self.vo_text.replace("! ", ". ").split(". ") if s.strip()]
        lens = [len(s) for s in sents]
        tot = sum(lens)
        acc = 0.0
        for s, l in zip(sents, lens):
            d = self.vo_dur * l / tot
            if vt < acc + d or s is sents[-1]:
                a = clamp(min((vt - acc + 0.2) / 0.25, (acc + d + 0.3 - vt) / 0.25))
                return (s if s.endswith(".") or s.endswith("?") else s + "."), a
            acc += d
        return "", 0


class Intro(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t)
        # falling bags counting up
        n = int(clamp(t / (self.dur - 1)) * 1240)
        k = ease_out(prog(t, 0.3, 1.0))
        text(p, W / 2, 470, f"{n:,}", font(190, XBOLD), WHITE, k, "center")
        text(p, W / 2, 545, "BAGS LEFT THE GATE TODAY", font(30, SEMI, 8), AMBER, k, "center")
        kinetic(p, W / 2, 720, "But how many went onto each truck?", font(62, BOLD), t, 2.6, WHITE, align="center")


class Problem(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.7)
        section_tag(p, t, "The problem", 1)
        items = [("sessions", "Manual tally sheets", "Slow, tiring and error-prone"),
                 ("truck", "Short loads", "A few bags missing on every truck"),
                 ("reports", "Disputes", "No proof for complaints")]
        for i, (ic, title, sub) in enumerate(items):
            st = 0.8 + i * 2.6
            k = ease_back(prog(t, st, 0.7), 1.2)
            if k <= 0:
                continue
            x = 160 + i * 560
            r = QRectF(x, 330 + (1 - k) * 80, 500, 420)
            card(p, r, clamp(k * 1.3), QColor(255, 255, 255, 245))
            p.save()
            p.setOpacity(clamp(k))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FBE6E6"))
            p.drawEllipse(QPointF(r.x() + 90, r.y() + 105), 56, 56)
            p.drawImage(QRectF(r.x() + 55, r.y() + 70, 70, 70), icon(ic, "#D64545", 140))
            text(p, r.x() + 44, r.y() + 250, title, font(44, XBOLD), NAVY)
            text(p, r.x() + 44, r.y() + 305, sub, font(26), QColor("#5A6475"))
            kx = ease_out(prog(t, st + 0.6, 0.4))
            p.setPen(QPen(RED, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            cx, cy = r.right() - 70, r.y() + 80
            p.drawLine(QPointF(cx - 24, cy - 24), QPointF(cx - 24 + 48 * kx, cy - 24 + 48 * kx))
            if kx > 0.5:
                k2 = (kx - 0.5) * 2
                p.drawLine(QPointF(cx + 24, cy - 24), QPointF(cx + 24 - 48 * k2, cy - 24 + 48 * k2))
            p.restore()
        kl = ease_out(prog(t, 8.6, 0.6))
        text(p, W / 2, 880, "Losses add up. Every single day.", font(46, BOLD), AMBER, kl, "center")


class Brand(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.85)
        white_logo_tile(p, W / 2, 400, 360, t, 0.1)
        k = ease_out(prog(t, 2.2, 0.8))
        p.save()
        p.setOpacity(k)
        f = font(120, XBOLD)
        text(p, W / 2, 720 + 30 * (1 - k), "NomLoad Counter", f, WHITE, 1, "center")
        p.restore()
        kb = ease_out(prog(t, 2.9, 0.6))
        text(p, W / 2, 790, "by DEVNOM", font(30, SEMI, 10), AMBER, kb, "center")
        kinetic(p, W / 2, 900, "Your CCTV cameras, turned into an automatic loading counter.", font(40), t, 4.0,
                QColor("#D7DDEA"), align="center", stagger=0.05)
        # light sweep across the title
        sw = prog(t, 2.6, 1.2)
        if 0 < sw < 1:
            g = QLinearGradient(W * (sw * 1.4 - 0.2), 0, W * (sw * 1.4 - 0.1), 0)
            g.setColorAt(0, QColor(255, 255, 255, 0))
            g.setColorAt(0.5, QColor(255, 255, 255, 70))
            g.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillRect(QRectF(0, 610, W, 140), QBrush(g))


class How(Scene):
    dark = False

    def draw(self, p, t):
        soft_bg(p, t)
        section_tag(p, t, "How it works", 2, light=True)
        steps = [("sessions", "Select the gate pass", "Clerk picks the truck's gate pass"),
                 ("live", "Count automatically", "+1 into the truck, -1 back out"),
                 ("check", "Verify & clear", "Compared with the invoice")]
        for i, (ic, title, sub) in enumerate(steps):
            st = 0.8 + i * 2.5
            k = ease_back(prog(t, st, 0.7), 1.3)
            x = 180 + i * 560
            if i > 0:
                kl = ease_in_out(prog(t, st - 0.6, 0.7))
                p.setPen(QPen(AMBER, 6, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(x - 150, 470), QPointF(x - 150 + 110 * kl, 470))
            if k <= 0:
                continue
            p.save()
            p.setOpacity(clamp(k))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(NAVY)
            rad = 110 * (0.5 + 0.5 * k)
            p.drawEllipse(QPointF(x + 200, 470), rad, rad)
            p.drawImage(QRectF(x + 150, 420, 100, 100), icon(ic, "#FFFFFF", 200))
            p.setBrush(AMBER)
            p.drawEllipse(QPointF(x + 280, 385), 34, 34)
            text(p, x + 280, 400, str(i + 1), font(38, XBOLD), NAVY, 1, "center")
            text(p, x + 200, 660, title, font(46, XBOLD), NAVY, 1, "center")
            text(p, x + 200, 712, sub, font(28), QColor("#5A6475"), 1, "center")
            p.restore()
        # +1 / -1 flourish under step 2
        for j in range(4):
            st = 4.2 + j * 0.9
            kk = prog(t, st, 1.0)
            if 0 < kk < 1:
                plus = j != 2
                text(p, 920 + (j - 1.5) * 60, 820 - 80 * ease_out(kk), "+1" if plus else "-1", font(52, XBOLD),
                     GREEN if plus else RED, 1 - kk, "center")


class Live(Scene):
    def __init__(self, *a, frames=None, totals=None, **k):
        super().__init__(*a, **k)
        self.frames, self.totals = frames, totals

    def draw(self, p, t):
        PATTERN.draw(p, t, 0.6)
        section_tag(p, t, "Live counting", 3)
        k = ease_out(prog(t, 0.2, 0.9))
        r = QRectF(90 + (1 - k) * -200, 150, 1200, 675 + 34)
        idx = min(len(self.frames) - 1, int(t * 15))
        img = self.frames[idx]
        window(p, img, r, clamp(k * 1.5), title=True)
        # live counter badge
        total = self.totals[idx]
        cr = QRectF(r.x() + 30, r.bottom() - 150, 280, 120)
        card(p, cr, clamp(k), QColor(18, 28, 54, 230))
        text(p, cr.x() + 26, cr.y() + 46, "COUNTED", font(20, SEMI, 4), AMBER, clamp(k))
        text(p, cr.x() + 26, cr.y() + 102, f"{total}", font(62, XBOLD), WHITE, clamp(k))
        text(p, cr.x() + 150, cr.y() + 102, "bags", font(30, SEMI), MUTED, clamp(k))
        # real-time pill
        pill(p, r.right() - 120, r.y() + 70, "● LIVE", font(22, BOLD), RED, WHITE, clamp(k) * (0.75 + 0.25 * math.sin(t * 6)))
        feats = ["Head & shoulder loads", "Stacked cartons", "Trolleys & conveyors", "Counted once - no doubles",
                 "Items carried back: -1"]
        for i, f_ in enumerate(feats):
            st = 1.2 + i * 1.6
            kf = ease_out(prog(t, st, 0.6))
            y = 270 + i * 120
            x = 1360 + (1 - kf) * 60
            p.save()
            p.setOpacity(kf)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(AMBER)
            p.drawEllipse(QPointF(x + 20, y - 12), 20, 20)
            p.drawImage(QRectF(x + 6, y - 26, 28, 28), icon("check", "#1B2A4E", 56))
            text(p, x + 60, y, f_, font(32, SEMI), WHITE)
            p.restore()


class Plate(Scene):
    def __init__(self, *a, frames=None, **k):
        super().__init__(*a, **k)
        self.frames = frames

    def draw(self, p, t):
        PATTERN.draw(p, t, 0.6)
        section_tag(p, t, "Number plate", 4)
        idx = min(len(self.frames) - 1, int((t + 1.6) * 15))
        k = ease_out(prog(t, 0.1, 0.8))
        r = QRectF(120, 170, 1000, 562 + 34)
        window(p, self.frames[idx], r, clamp(k * 1.4), title=True)
        # scanner box over the plate (plate sits around 50% x, 82% y of the frame)
        pr = QRectF(r.x() + 1000 * 0.33, r.y() + 34 + 562 * 0.70, 1000 * 0.34, 562 * 0.20)
        ks = prog(t, 1.0, 0.5)
        if ks > 0:
            p.save()
            p.setPen(QPen(AMBER, 4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            L = 30
            for (cx, cy, dx, dy) in ((pr.left(), pr.top(), 1, 1), (pr.right(), pr.top(), -1, 1),
                                     (pr.right(), pr.bottom(), -1, -1), (pr.left(), pr.bottom(), 1, -1)):
                p.drawLine(QPointF(cx, cy), QPointF(cx + dx * L, cy))
                p.drawLine(QPointF(cx, cy), QPointF(cx, cy + dy * L))
            sy = pr.top() + pr.height() * (0.5 + 0.5 * math.sin((t - 1) * 4))
            p.setPen(QPen(QColor(232, 163, 61, 180), 3))
            p.drawLine(QPointF(pr.left() + 6, sy), QPointF(pr.right() - 6, sy))
            p.restore()
        # read result
        kr = ease_back(prog(t, 2.0, 0.6), 1.3)
        if kr > 0:
            rr = QRectF(1200, 300, 600, 380)
            card(p, rr, clamp(kr), WHITE)
            p.save()
            p.setOpacity(clamp(kr))
            text(p, rr.x() + 40, rr.y() + 70, "PLATE READ", font(22, SEMI, 5), QColor("#5A6475"))
            s = "LES-4721"[: int(clamp((t - 2.2) / 0.8) * 8)]
            pr2 = QRectF(rr.x() + 40, rr.y() + 100, 520, 110)
            p.setPen(QPen(QColor("#111111"), 4))
            p.setBrush(WHITE)
            p.drawRoundedRect(pr2, 12, 12)
            text(p, pr2.center().x(), pr2.y() + 82, s, font(76, XBOLD), QColor("#111111"), 1, "center")
            km = ease_out(prog(t, 3.3, 0.5))
            p.setOpacity(clamp(kr) * km)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(GREEN)
            p.drawEllipse(QPointF(rr.x() + 70, rr.y() + 300), 28, 28)
            p.drawImage(QRectF(rr.x() + 50, rr.y() + 280, 40, 40), icon("check", "#FFFFFF", 80))
            text(p, rr.x() + 115, rr.y() + 290, "Matched gate pass", font(28, SEMI), NAVY)
            text(p, rr.x() + 115, rr.y() + 330, "GP-1005 · Al-Madina Traders", font(24), QColor("#5A6475"))
            p.restore()


class Result(Scene):
    dark = False

    def draw(self, p, t):
        soft_bg(p, t)
        section_tag(p, t, "Close & verify", 5, light=True)
        k1 = ease_out(prog(t, 0.5, 0.8))
        img = SHOT["09_result_cleared"]
        r1 = QRectF(120 + (1 - k1) * -300, 200, 760, 760 * img.height() / img.width() + 34)
        window(p, img, r1, clamp(k1 * 1.5))
        k2 = ease_out(prog(t, 4.5, 0.8))
        img2 = SHOT["10_result_mismatch"]
        r2 = QRectF(1040 + (1 - k2) * 300, 200, 760, 760 * img2.height() / img2.width() + 34)
        if k2 > 0:
            window(p, img2, r2, clamp(k2 * 1.5))
            # alarm pulse
            if t > 5.3:
                a = 0.5 + 0.5 * math.sin((t - 5.3) * 9)
                p.setPen(QPen(QColor(214, 69, 69, int(170 * a)), 10))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r2.adjusted(-12, -12, 12, 12), 22, 22)
        text(p, r1.center().x(), r1.bottom() + 70, "Truck may leave", font(40, XBOLD), GREEN, k1, "center")
        if k2 > 0:
            text(p, r2.center().x(), r2.bottom() + 70, "Held until supervisor release", font(40, XBOLD), RED, k2,
                 "center")
        k3 = ease_back(prog(t, 10.5, 0.7), 1.2)
        if k3 > 0:
            img3 = SHOT["08_supervisor_approval"]
            r3 = QRectF(W / 2 - 280, 330 + (1 - k3) * 120, 560, 560 * img3.height() / img3.width() + 34)
            p.fillRect(0, 0, W, H, QColor(18, 28, 54, int(120 * clamp(k3))))
            window(p, img3, r3, clamp(k3))
            pill(p, W / 2, r3.y() - 34, "PIN + written reason", font(26, BOLD), AMBER, NAVY, clamp(k3))


class Evidence(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.6)
        section_tag(p, t, "Evidence", 6)
        k = ease_out(prog(t, 0.3, 0.9))
        img = SHOT["17_session_snapshots"]
        r = QRectF(100, 160, 1150, 1150 * img.height() / img.width() + 34)
        z = 1.0 + 0.25 * ease_in_out(prog(t, 1.5, 6))
        window(p, img, r, clamp(k * 1.4), zoom=z, focus=(0.35, 0.45))
        k2 = ease_out(prog(t, 5.5, 0.8))
        if k2 > 0:
            img2 = SHOT["18_session_evidence"]
            r2 = QRectF(820 + (1 - k2) * 300, 420, 980, 980 * img2.height() / img2.width() + 34)
            window(p, img2, r2, clamp(k2 * 1.4), zoom=1.35, focus=(0.75, 0.3))
        items = [("film", "Full loading video"), ("cameras", "Photo of every item"), ("shield", "SHA-256 fingerprint"),
                 ("download", "One-click evidence pack")]
        for i, (ic, s) in enumerate(items):
            st = 1.0 + i * 1.3
            kk = ease_out(prog(t, st, 0.5))
            x, y = 1330, 220 + i * 70
            if t > 5.3:
                kk *= 1 - ease_out(prog(t, 5.3, 0.4))
            p.save()
            p.setOpacity(kk)
            p.drawImage(QRectF(x, y - 34, 44, 44), icon(ic, "#E8A33D", 88))
            text(p, x + 60, y, s, font(32, SEMI), WHITE)
            p.restore()


class Dash(Scene):
    dark = False

    def draw(self, p, t):
        soft_bg(p, t)
        section_tag(p, t, "Dashboard & reports", 8, light=True)
        k = ease_out(prog(t, 0.3, 0.9))
        img = SHOT["03_dashboard"]
        r = QRectF(100, 150, 1200, 1200 * img.height() / img.width() + 34)
        z = 1.0 + 0.18 * ease_in_out(prog(t, 0.8, 5))
        window(p, img, r, clamp(k * 1.4), zoom=z, focus=(0.6, 0.25))
        callout(p, QRectF(r.x() + 225, r.y() + 34 + 82 * (1 + 0.18 * ease_in_out(prog(t, 0.8, 5))) * r.width() / 1440 * 0.98,
                          900, 95), t, 1.6, "Today at a glance")
        for i, (nm, rot) in enumerate((("40_certificate_pdf", -6), ("41_daily_pdf", 5))):
            st = 4.6 + i * 1.2
            kk = ease_back(prog(t, st, 0.7), 1.2)
            if kk <= 0:
                continue
            im = SHOT[nm]
            w_ = 420
            h_ = w_ * im.height() / im.width()
            p.save()
            p.translate(1500 + i * 120, 560 + (1 - kk) * 500)
            p.rotate(rot * kk)
            rr = QRectF(-w_ / 2, -h_ / 2, w_, h_)
            shadow_rect(p, rr, 6, 1.6)
            p.drawImage(rr, im)
            p.restore()
        kx = ease_out(prog(t, 7.0, 0.5))
        pill(p, 1560, 100, "PDF  ·  Excel  ·  Company logo", font(26, BOLD), NAVY, WHITE, kx)


class History(Scene):
    dark = False

    def draw(self, p, t):
        soft_bg(p, t)
        section_tag(p, t, "History", 7, light=True)
        k = ease_out(prog(t, 0.3, 0.9))
        img = SHOT["15_history"]
        r = QRectF(100, 150, 1150, 1150 * img.height() / img.width() + 34)
        window(p, img, r, clamp(k * 1.4), zoom=1.0 + 0.15 * ease_in_out(prog(t, 0.8, 6)), focus=(0.4, 0.3))
        k2 = ease_back(prog(t, 3.2, 0.8), 1.2)
        if k2 > 0:
            img2 = SHOT["16_session_summary"]
            r2 = QRectF(1080 + (1 - k2) * 300, 330, 760, 760 * img2.height() / img2.width() + 34)
            window(p, img2, r2, clamp(k2 * 1.4))
        for i, s_ in enumerate(("Date", "Truck", "Gate pass")):
            kk = ease_out(prog(t, 1.2 + i * 0.5, 0.5))
            pill(p, 1240 + i * 200, 230, s_, font(26, BOLD), NAVY, WHITE, kk * (1 - ease_out(prog(t, 3.1, 0.3))))


class Setup(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.6)
        section_tag(p, t, "Easy setup", 10)
        k = ease_out(prog(t, 0.3, 0.9))
        img = SHOT["23_add_camera_rtsp"]
        r = QRectF(110 + (1 - k) * -200, 190, 760, min(760 * img.height() / img.width() + 34, 760))
        window(p, img, r, clamp(k * 1.4))
        k2 = ease_out(prog(t, 2.4, 0.8))
        if k2 > 0:
            img2 = SHOT["24_calibration"]
            r2 = QRectF(940 + (1 - k2) * 300, 190, 880, 880 * img2.height() / img2.width() + 34)
            window(p, img2, r2, clamp(k2 * 1.4))
            callout(p, r2.adjusted(30, 60, -30, -30), t, 3.4, "Draw the counting line")


class Train(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.6)
        section_tag(p, t, "Training", 9)
        k = ease_out(prog(t, 0.3, 0.9))
        img = SHOT["26_training_annotate"]
        r = QRectF(90, 160, 1180, 1180 * img.height() / img.width() + 34)
        window(p, img, r, clamp(k * 1.4), zoom=1.0 + 0.3 * ease_in_out(prog(t, 1.0, 5)), focus=(0.6, 0.55))
        k2 = ease_out(prog(t, 4.2, 0.8))
        if k2 > 0:
            img2 = SHOT["27_training_train"]
            r2 = QRectF(1000 + (1 - k2) * 300, 470, 840, 840 * img2.height() / img2.width() + 34)
            window(p, img2, r2, clamp(k2 * 1.4), zoom=1.3, focus=(0.6, 0.35))
        steps = ["1  Collect frames", "2  Annotate", "3  Train", "4  Activate"]
        for i, s in enumerate(steps):
            kk = ease_out(prog(t, 1.0 + i * 0.9, 0.5))
            pill(p, 1590, 230 + i * 62, s, font(26, BOLD), AMBER if i < 3 else GREEN, NAVY if i < 3 else WHITE,
                 kk * (1 - ease_out(prog(t, 4.0, 0.3))))


class Offline(Scene):
    dark = False

    def draw(self, p, t):
        soft_bg(p, t)
        section_tag(p, t, "Built for your factory", 11, light=True)
        tiles = [("shield", "100% offline", "No internet needed to count"),
                 ("dashboard", "Ordinary office PC", "Core i5 · 8 GB RAM"),
                 ("cameras", "Existing CCTV", "Hikvision · Dahua · ONVIF"),
                 ("bell", "Owner alerts", "WhatsApp · email · SMS"),
                 ("live", "Multiple bays", "Several trucks at once"),
                 ("key", "Licensed per PC", "Starter · Pro · Enterprise")]
        for i, (ic, a, b) in enumerate(tiles):
            st = 0.6 + i * 0.9
            kk = ease_back(prog(t, st, 0.6), 1.4)
            if kk <= 0:
                continue
            col, row = i % 3, i // 3
            r = QRectF(150 + col * 560, 230 + row * 330 + (1 - kk) * 60, 500, 280)
            card(p, r, clamp(kk))
            p.save()
            p.setOpacity(clamp(kk))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(NAVY)
            p.drawRoundedRect(QRectF(r.x() + 36, r.y() + 36, 96, 96), 22, 22)
            p.drawImage(QRectF(r.x() + 54, r.y() + 54, 60, 60), icon(ic, "#E8A33D", 120))
            text(p, r.x() + 36, r.y() + 195, a, font(40, XBOLD), NAVY)
            text(p, r.x() + 36, r.y() + 240, b, font(26), QColor("#5A6475"))
            p.restore()


class Secure(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.6)
        section_tag(p, t, "Security", 12)
        k = ease_out(prog(t, 0.3, 0.9))
        img = SHOT["19_session_audit"]
        r = QRectF(560, 200, 1260, 1260 * img.height() / img.width() + 34)
        window(p, img, r, clamp(k * 1.4), zoom=1.25, focus=(0.4, 0.3))
        roles = [("Clerk", "Run loading", "#3E5A94"), ("Supervisor", "Approve & review", "#E8A33D"),
                 ("Admin", "Full control", "#1F9D55")]
        for i, (a, b, c) in enumerate(roles):
            kk = ease_back(prog(t, 0.8 + i * 0.7, 0.6), 1.3)
            if kk <= 0:
                continue
            rr = QRectF(110 + (1 - kk) * -100, 260 + i * 190, 380, 150)
            card(p, rr, clamp(kk))
            p.save()
            p.setOpacity(clamp(kk))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c))
            p.drawEllipse(QPointF(rr.x() + 70, rr.center().y()), 40, 40)
            p.drawImage(QRectF(rr.x() + 46, rr.center().y() - 24, 48, 48), icon("users", "#FFFFFF", 96))
            text(p, rr.x() + 135, rr.y() + 68, a, font(36, XBOLD), NAVY)
            text(p, rr.x() + 135, rr.y() + 108, b, font(24), QColor("#5A6475"))
            p.restore()
        pill(p, 1190, 150, "Tamper-proof audit log", font(28, BOLD), AMBER, NAVY, ease_out(prog(t, 3.0, 0.5)))


class Outro(Scene):
    def draw(self, p, t):
        PATTERN.draw(p, t, 0.9)
        white_logo_tile(p, W / 2, 330, 300, t, 0.2)
        k = ease_out(prog(t, 1.6, 0.8))
        text(p, W / 2, 610 + 20 * (1 - k), "NomLoad Counter", font(104, XBOLD), WHITE, k, "center")
        kinetic(p, W / 2, 720, "Count every bag. Clear every truck.", font(52, BOLD), t, 2.6, AMBER, align="center")
        kc = ease_out(prog(t, 4.6, 0.7))
        pill(p, W / 2, 860, "Contact Devnom for a free demo", font(34, BOLD), WHITE, NAVY, kc, pad=40)
        text(p, W / 2, 990, "DEVNOM", font(26, SEMI, 12), MUTED, ease_out(prog(t, 5.5, 0.8)), "center")


# ------------------------------------------------------------------ transitions
def wipe(p, k):
    """Amber + navy diagonal wipe. k: 0..1 over the transition."""
    if k <= 0 or k >= 1:
        return
    for i, col in enumerate((AMBER, NAVY)):
        kk = ease_in_out(clamp((k - i * 0.12) / 0.88))
        x = -W * 0.6 + kk * (W * 2.2)
        path = QPainterPath()
        path.moveTo(x, 0)
        path.lineTo(x + W * 0.55, 0)
        path.lineTo(x + W * 0.35, H)
        path.lineTo(x - W * 0.2, H)
        path.closeSubpath()
        p.fillPath(path, col)


# ------------------------------------------------------------------ build timeline
def wav_dur(f):
    w = wave.open(f)
    return w.getnframes() / w.getframerate()


def build():
    script = dict(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "script.json"))))
    d = {k: wav_dur(os.path.join(V, "voice", k + ".wav")) for k in script}
    print("rendering engine footage...", flush=True)
    live_frames, live_totals = engine_clip("flour_mill_bay.mp4", "flour_mill_bay.mp4", d["live"] + 4, start_frame=60)
    plate = plate_frames(d["plate"] + 5)
    scenes = [
        Intro("intro", script["intro"], d["intro"], lead=2.8, tail=1.2),
        Problem("problem", script["problem"], d["problem"], tail=1.6),
        Brand("brand", script["brand"], d["brand"], lead=2.6, tail=2.0),
        How("how", script["how"], d["how"], tail=1.6),
        Live("live", script["live"], d["live"], tail=2.4, frames=live_frames, totals=live_totals),
        Plate("plate", script["plate"], d["plate"], tail=2.2, frames=plate),
        Result("result", script["result"], d["result"], tail=1.4),
        Evidence("evidence", script["evidence"], d["evidence"], tail=1.4),
        History("history", script["history"], d["history"], tail=1.6),
        Dash("dash", script["dash"], d["dash"], tail=1.6),
        Train("train", script["train"], d["train"], tail=1.4),
        Setup("setup", script["setup"], d["setup"], tail=1.8),
        Offline("offline", script["offline"], d["offline"], tail=1.4),
        Secure("secure", script["secure"], d["secure"], tail=1.4),
        Outro("outro", script["outro"], d["outro"], lead=1.2, tail=5.0),
    ]
    t0 = 0.0
    timeline = []
    for s in scenes:
        timeline.append((t0, s))
        t0 += s.dur
    return timeline, t0


TRANS = 0.7


def render():
    timeline, total = build()
    json.dump([{"name": s.name, "start": st, "lead": s.lead, "dur": s.dur} for st, s in timeline],
              open(os.path.join(V, "timeline.json"), "w"), indent=1)
    print(f"total {total:.1f}s", flush=True)
    n = int(total * FPS)
    out = os.path.join(V, "video_noaudio.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    for fi in range(n):
        T = fi / FPS
        idx = max(i for i, (st, _) in enumerate(timeline) if st <= T)
        st, sc = timeline[idx]
        lt = T - st
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        sc.draw(p, lt)
        cap, a = sc.captions(lt)
        caption(p, cap, a)
        # transition into the next scene
        end = st + sc.dur
        if idx + 1 < len(timeline) and T > end - TRANS / 2:
            wipe(p, (T - (end - TRANS / 2)) / TRANS)
        if idx > 0 and lt < TRANS / 2:
            wipe(p, (lt + TRANS / 2) / TRANS)
        # global fade in / out
        if T < 0.6:
            p.fillRect(0, 0, W, H, QColor(0, 0, 0, int(255 * (1 - T / 0.6))))
        if T > total - 1.2:
            p.fillRect(0, 0, W, H, QColor(0, 0, 0, int(255 * clamp((T - (total - 1.2)) / 1.2))))
        p.end()
        ff.stdin.write(img.constBits().tobytes() if hasattr(img.constBits(), "tobytes") else bytes(img.constBits()))
        if fi % 300 == 0:
            print(f"frame {fi}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("video done", out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "still":
        timeline, total = build()
        img = QImage(W, H, QImage.Format.Format_ARGB32)
        for spec in sys.argv[2:]:
            name, lt = spec.split("@")
            st, sc = next((st, s) for st, s in timeline if s.name == name)
            p = QPainter(img)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            sc.draw(p, float(lt))
            cap, a = sc.captions(float(lt))
            caption(p, cap, a)
            p.end()
            img.save(os.path.join(V, f"still_{name}_{lt}.png"))
            print("still", name, lt)
    else:
        render()
