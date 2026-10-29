import pytest

from nomload.core import plate_formats as pf


@pytest.mark.parametrize("raw,expected,prov", [
    ("LES 4721", "LES-4721", "Punjab"),
    ("LE5-4721", "LES-4721", "Punjab"),     # 5 read in the letter part -> S
    ("LESA721", "LES-4721", "Punjab"),      # A read in the digit part -> 4
    ("BKF-456", "BKF-456", "Sindh"),
    ("TLA 552", "TLA-552", "Sindh"),
    ("ICT-1234", "ICT-1234", "ICT"),
    ("QAA 123", "QAA-123", "Balochistan"),
    ("lea-1O2", "LEA-102", "Punjab"),
])
def test_parse_and_fix(raw, expected, prov):
    p = pf.parse(raw)
    assert p.text == expected and p.province == prov


def test_commercial_flag():
    assert pf.parse("TLB-990").commercial
    assert not pf.parse("LEA-1234").commercial


def test_garbage():
    assert pf.parse("").text == "" and pf.parse("-- ..").plausibility == 0


def test_plate_matching_tolerates_one_error():
    assert pf.plates_match("LES-4721", "les 4721")
    assert pf.plates_match("LES-4721", "LES-4727")
    assert not pf.plates_match("LES-4721", "LEA-1234")


def test_ocr_reads_rendered_plates():
    from nomload.core.plates import CharOCR, PlateReader
    from nomload.config import bundled_models_dir
    from nomload.training.qt_render import render_plate
    reader = PlateReader(CharOCR(bundled_models_dir() / "plate_ocr.onnx"))
    ok = 0
    cases = [("LES-4721", "Punjab", "white"), ("BKF-456", "Sindh", "yellow"), ("ICT-1234", "ICT", "green"),
             ("TLA-552", "Sindh", "white"), ("RIK-908", "Punjab", "white")]
    for text, prov, style in cases:
        img = render_plate(text, prov, style)
        r = reader.read_frame(img)
        ok += int(r is not None and r.text == text)
    assert ok >= 4
