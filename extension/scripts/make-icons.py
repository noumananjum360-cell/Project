"""Generate the extension PNG icons (run once; output is committed)."""
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(__file__).resolve().parents[1] / "public" / "icons"
out.mkdir(parents=True, exist_ok=True)
for size in (16, 32, 48, 128):
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s // 4, fill=(79, 70, 229, 255))
    w = max(2, int(s * 0.075))
    d.line([(s * 0.31, s * 0.69), (s * 0.5, s * 0.31), (s * 0.69, s * 0.69)], fill="white", width=w, joint="curve")
    d.line([(s * 0.39, s * 0.53), (s * 0.61, s * 0.53)], fill="white", width=w)
    img.resize((size, size), Image.LANCZOS).save(out / f"icon-{size}.png")
print("icons written to", out)
