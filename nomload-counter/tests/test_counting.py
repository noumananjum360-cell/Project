"""Line crossing, direction handling and double-count prevention (tracker + counter)."""
import math

from helpers import det

from nomload.config import COUNTABLE_CLASSES
from nomload.core.counter import CounterConfig, LineCounter
from nomload.core.geometry import CountGeometry
from nomload.core.tracker import ByteTracker

W, H = 640, 360
LINE_X = 320


def make():
    geo = CountGeometry(p1=(LINE_X / W, 0.0), p2=(LINE_X / W, 1.0), in_side=1, band=0.02).to_pixels(W, H)
    return ByteTracker(COUNTABLE_CLASSES), LineCounter(geo, COUNTABLE_CLASSES, CounterConfig())


def run(frames):
    """frames: list of detection lists. Returns (events, counter)."""
    tr, c = make()
    events = []
    for i, dets in enumerate(frames):
        tracks = tr.update(dets)
        events += c.update(tracks, tr.lost_tracks, i + 1, i / 15)
    return events, c


def walk(x0, x1, y=200, step=6, **kw):
    n = int(abs(x1 - x0) / step)
    d = 1 if x1 > x0 else -1
    return [[det(x0 + d * step * i, y, **kw)] for i in range(n + 1)]


def test_single_item_loaded_counts_plus_one():
    ev, c = run(walk(100, 500))
    assert [e.direction for e in ev] == [1]
    assert c.net("bag") == 1
    assert not ev[0].flagged


def test_item_carried_back_out_counts_minus_one():
    ev, c = run(walk(500, 100))
    assert [e.direction for e in ev] == [-1]
    assert c.net() == -1


def test_in_then_back_out_nets_zero():
    ev, c = run(walk(100, 500) + walk(500, 100))
    assert c.net() == 0
    assert sorted(e.direction for e in ev) == [-1, 1]


def test_pause_and_sway_on_line_counts_once():
    frames = walk(100, LINE_X - 2)
    for k in range(60):  # labourer stands on the line for 4 seconds, swaying +-5 px
        frames.append([det(LINE_X + 5 * math.sin(k / 3), 200)])
    frames += walk(LINE_X + 2, 520)
    ev, c = run(frames)
    assert c.net() == 1 and len(ev) == 1


def test_step_back_and_forth_across_line_nets_one():
    frames = walk(100, 360) + walk(360, 280) + walk(280, 500)
    ev, c = run(frames)
    assert c.net() == 1


def test_occlusion_gap_does_not_double_count():
    frames = walk(100, 300)
    frames += [[] for _ in range(6)]      # hidden behind a labourer for 6 frames
    frames += walk(336, 520)
    ev, c = run(frames)
    assert c.net() == 1


def test_identity_switch_mid_crossing_recovered():
    tr, c = make()
    events = []
    f = 0
    for x in range(100, 340, 6):
        f += 1
        events += c.update(tr.update([det(x, 200)]), tr.lost_tracks, f, f / 15)
    # crossing already counted at this point
    assert c.net() == 1
    # tracker loses the item for longer than its buffer, a new ID appears nearby
    for _ in range(30):
        f += 1
        events += c.update(tr.update([]), tr.lost_tracks, f, f / 15)
    for x in range(345, 520, 6):
        f += 1
        events += c.update(tr.update([det(x, 200)]), tr.lost_tracks, f, f / 15)
    assert c.net() == 1


def test_several_labourers_crossing_together():
    frames = []
    for i in range(70):
        x = 100 + 6 * i
        frames.append([det(x, 120), det(x - 30, 200), det(x + 20, 290, cls="carton"), det(x + 20, 316, cls="carton")])
    ev, c = run(frames)
    assert c.net("bag") == 2 and c.net("carton") == 2


def test_people_are_never_counted():
    ev, c = run(walk(100, 500, w=40, h=120, cls="person"))
    assert ev == [] and c.net() == 0


def test_low_confidence_count_is_flagged():
    ev, _c = run(walk(100, 500, score=0.52))
    assert len(ev) == 1
    tr, c = make()
    c.cfg.review_threshold = 0.6
    events = []
    for i, d in enumerate(walk(100, 500, score=0.52)):
        events += c.update(tr.update(d), tr.lost_tracks, i + 1, 0)
    assert events[0].flagged and events[0].reason


def test_item_appearing_on_the_line_is_counted_but_flagged():
    frames = [[det(LINE_X + 2, 200)] for _ in range(3)] + walk(LINE_X + 4, 520)
    ev, c = run(frames)
    assert c.net() == 1 and ev[0].flagged


def test_outside_segment_not_counted():
    geo = CountGeometry(p1=(0.5, 0.0), p2=(0.5, 0.4), segment_margin=0.0).to_pixels(W, H)
    tr = ByteTracker(COUNTABLE_CLASSES)
    c = LineCounter(geo, COUNTABLE_CLASSES)
    for i, d in enumerate(walk(100, 500, y=320)):
        c.update(tr.update(d), tr.lost_tracks, i + 1, 0)
    assert c.net() == 0
