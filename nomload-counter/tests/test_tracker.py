import numpy as np
from helpers import det

from nomload.config import COUNTABLE_CLASSES
from nomload.core.tracker import ByteTracker, _hungarian, linear_assignment


def test_hungarian_optimal():
    c = np.array([[4, 1, 3], [2, 0, 5], [3, 2, 2]], float)
    pairs = sorted(_hungarian(c))
    assert sum(c[i, j] for i, j in pairs) == 5


def test_hungarian_rectangular():
    c = np.array([[1, 9], [9, 1], [5, 5]], float)
    pairs = dict(_hungarian(c))
    assert pairs[0] == 0 and pairs[1] == 1


def test_linear_assignment_threshold():
    m, ur, uc = linear_assignment(np.array([[0.1, 0.95], [0.97, 0.99]]), 0.9)
    assert m == [(0, 0)] and ur == [1] and uc == [1]


def test_track_keeps_id_with_low_score_detection():
    t = ByteTracker(COUNTABLE_CLASSES)
    ids = set()
    for i in range(20):
        score = 0.25 if 8 <= i <= 11 else 0.9   # partly occluded -> weak detection
        tracks = t.update([det(100 + 5 * i, 100, score=score)])
        ids |= {tr.track_id for tr in tracks}
    assert len(ids) == 1


def test_goods_and_people_do_not_swap():
    t = ByteTracker(COUNTABLE_CLASSES)
    for i in range(10):
        tracks = t.update([det(100 + 5 * i, 100, cls="bag"), det(100 + 5 * i, 104, w=44, h=30, cls="person")])
    classes = {tr.track_id: tr.cls for tr in tracks}
    assert sorted(classes.values()) == ["bag", "person"]
