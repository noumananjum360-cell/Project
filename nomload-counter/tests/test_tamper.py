import cv2
import numpy as np

from nomload.core.tamper import TamperDetector


def scene():
    rng = np.random.default_rng(0)
    img = (rng.random((360, 640, 3)) * 60 + 90).astype(np.uint8)
    for i in range(0, 640, 40):
        cv2.line(img, (i, 0), (i + 100, 360), (30, 30, 30), 3)
    cv2.rectangle(img, (400, 50), (600, 300), (20, 40, 160), -1)
    return img


def settle(td, frame, n=80):
    r = None
    for _ in range(n):
        r = td.evaluate(frame)
    return r


def test_normal_view_ok():
    ref = scene()
    assert settle(TamperDetector(ref), ref).status == "ok"


def test_covered():
    assert TamperDetector(scene()).evaluate(np.full((360, 640, 3), 5, np.uint8)).status == "covered"


def test_blurred():
    ref = scene()
    assert settle(TamperDetector(ref), cv2.GaussianBlur(ref, (31, 31), 12)).status == "blurred"


def test_moved():
    ref = scene()
    m = np.float32([[1, 0, 90], [0, 1, 40]])
    moved = cv2.warpAffine(ref, m, (640, 360), borderMode=cv2.BORDER_REFLECT)
    assert settle(TamperDetector(ref), moved).status in ("moved", "changed")


def test_alert_needs_persistence():
    ref = scene()
    td = TamperDetector(ref, persist_s=4)
    dark = np.full((360, 640, 3), 5, np.uint8)
    assert td.update(dark, now=0) is None
    assert td.update(dark, now=2) is None
    assert td.update(dark, now=4.5).status == "covered"
    assert td.update(dark, now=5) is None          # edge triggered, no repeats
