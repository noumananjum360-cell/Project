from nomload.core.geometry import CountGeometry, iou, point_in_polygon, polygon_signed_distance


def test_vertical_line_inside_is_right_by_default():
    g = CountGeometry(p1=(0.5, 0.0), p2=(0.5, 1.0), in_side=1).to_pixels(640, 360)
    assert g.signed_distance((400, 180)) > 0
    assert g.signed_distance((200, 180)) < 0
    assert abs(g.signed_distance((320, 100))) < 1e-6


def test_flip_direction():
    g = CountGeometry(p1=(0.5, 0.0), p2=(0.5, 1.0), in_side=-1).to_pixels(640, 360)
    assert g.signed_distance((400, 180)) < 0


def test_line_segment_extent():
    g = CountGeometry(p1=(0.5, 0.4), p2=(0.5, 0.6), segment_margin=0.0).to_pixels(1000, 1000)
    assert g.within_segment((500, 500))
    assert not g.within_segment((500, 900))


def test_zone_mode_and_ignore():
    geo = CountGeometry(mode="zone", zone=[(0.6, 0.1), (0.9, 0.1), (0.9, 0.9), (0.6, 0.9)],
                        ignore_zones=[[(0, 0), (0.2, 0), (0.2, 0.2), (0, 0.2)]])
    g = geo.to_pixels(100, 100)
    assert g.signed_distance((75, 50)) > 0
    assert g.signed_distance((30, 50)) < 0
    assert g.ignored((10, 10)) and not g.ignored((50, 50))


def test_roundtrip_dict():
    geo = CountGeometry(mode="line", p1=(0.1, 0.2), p2=(0.3, 0.4), in_side=-1, plate_roi=(0.1, 0.1, 0.5, 0.5))
    assert CountGeometry.from_dict(geo.to_dict()) == geo


def test_polygon_helpers():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert point_in_polygon((5, 5), sq) and not point_in_polygon((15, 5), sq)
    assert polygon_signed_distance((5, 5), sq) == 5
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == 50 / 150
