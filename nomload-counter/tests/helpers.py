from nomload.core.detector import Detection


def det(cx, cy, w=40, h=24, score=0.9, cls="bag"):
    return Detection(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, score, cls)
