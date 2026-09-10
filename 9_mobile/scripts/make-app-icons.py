"""
Generate TUNE launcher / splash assets from the canonical brand wordmark.

Source of truth: 5_frontend/public/favicon.svg (white TU / NE stacked on Hot
Fuchsia #FF0061). apple-touch-icon.png is only 180x180, so the paths are
rasterised here rather than upscaled.

    python scripts/make-app-icons.py

Outputs (all under 9_mobile/assets):
  icon.png                      1024 opaque  iOS marketing icon (Apple rejects alpha)
  android-icon-foreground.png    512 alpha   adaptive foreground, circular-mask safe
  android-icon-background.png    512 opaque  solid fuchsia
  android-icon-monochrome.png    432 alpha   themed-icon layer
  splash-icon.png               1024 alpha   wordmark for the fuchsia splash

Apple applies its own corner rounding, so the square is written flat.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw

FUCHSIA = (255, 0, 97)
WHITE = (255, 255, 255)

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT.parent / "5_frontend" / "public" / "favicon.svg"
ASSETS = ROOT / "assets"

# Supersampling factor for the polygon fill; output is LANCZOS-downsampled.
SS = 4
# Cubic segments per bezier. The U bowl is the only curved glyph.
BEZIER_STEPS = 48

# Share of the canvas taken by the wordmark block.
# 0.6625 reproduces the favicon/apple-touch-icon framing.
IOS_MARK_FRACTION = 0.6625
# Adaptive icons mask the centre 72 of 108dp; a circle mask leaves an inscribed
# square of 72/sqrt(2) = 50.9dp, i.e. 0.471 of the layer. Letter corners are
# solid, so anything larger gets visibly clipped on circular launchers.
ADAPTIVE_MARK_FRACTION = 0.471


def parse_svg() -> tuple[list[list[tuple[float, float]]], tuple[float, float]]:
    """Return wordmark subpaths in SVG user units plus the viewBox size."""
    text = SVG.read_text(encoding="utf-8")

    vb = re.search(r'viewBox="([\d.\s-]+)"', text)
    if not vb:
        raise SystemExit(f"no viewBox in {SVG}")
    _, _, vb_w, vb_h = (float(v) for v in vb.group(1).split())

    tx, ty = 0.0, 0.0
    transform = re.search(r'transform="translate\(([-\d.]+)[,\s]+([-\d.]+)\)"', text)
    if transform:
        tx, ty = float(transform.group(1)), float(transform.group(2))

    polygons = [
        [(x + tx, y + ty) for x, y in flatten_path(d)]
        for d in re.findall(r'<path[^>]*\sd="([^"]+)"', text)
    ]
    if not polygons:
        raise SystemExit(f"no <path d=...> in {SVG}")
    return polygons, (vb_w, vb_h)


def flatten_path(d: str) -> list[tuple[float, float]]:
    """Flatten one absolute M/L/C/Z subpath into a point list."""
    tokens = re.findall(r"[MLCZmlcz]|-?\d*\.?\d+(?:e-?\d+)?", d)
    pts: list[tuple[float, float]] = []
    i = 0
    cmd = ""
    cur = (0.0, 0.0)

    def nums(count: int) -> list[float]:
        nonlocal i
        vals = [float(tokens[i + k]) for k in range(count)]
        i += count
        return vals

    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            cmd = token
            i += 1
            if cmd in "Zz":
                continue
        if cmd in "Mm":
            x, y = nums(2)
            cur = (x, y)
            pts.append(cur)
        elif cmd in "Ll":
            x, y = nums(2)
            cur = (x, y)
            pts.append(cur)
        elif cmd in "Cc":
            x1, y1, x2, y2, x, y = nums(6)
            p0 = cur
            for step in range(1, BEZIER_STEPS + 1):
                t = step / BEZIER_STEPS
                u = 1.0 - t
                pts.append((
                    u ** 3 * p0[0] + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x,
                    u ** 3 * p0[1] + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y,
                ))
            cur = (x, y)
        else:
            raise SystemExit(f"unsupported path command {token!r} in {SVG.name}")
    return pts


def wordmark_mask(size: int, fraction: float) -> Image.Image:
    """Anti-aliased alpha mask of the wordmark, centred and scaled to `fraction`."""
    polygons, _ = parse_svg()
    xs = [x for poly in polygons for x, _ in poly]
    ys = [y for poly in polygons for _, y in poly]
    mark_w, mark_h = max(xs) - min(xs), max(ys) - min(ys)

    hi = size * SS
    scale = (hi * fraction) / max(mark_w, mark_h)
    off_x = (hi - mark_w * scale) / 2 - min(xs) * scale
    off_y = (hi - mark_h * scale) / 2 - min(ys) * scale

    mask = Image.new("L", (hi, hi), 0)
    draw = ImageDraw.Draw(mask)
    for poly in polygons:
        draw.polygon([(x * scale + off_x, y * scale + off_y) for x, y in poly], fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def write(path: Path, image: Image.Image) -> None:
    image.save(path, "PNG", optimize=True)
    print(f"  {path.relative_to(ROOT)}  {image.size[0]}x{image.size[1]} {image.mode}")


def main() -> None:
    print(f"wordmark source: {SVG}")

    # iOS marketing icon — flattened onto fuchsia, no alpha channel at all.
    ios = Image.new("RGB", (1024, 1024), FUCHSIA)
    ios.paste(WHITE, (0, 0), wordmark_mask(1024, IOS_MARK_FRACTION))
    write(ASSETS / "icon.png", ios)

    # Android adaptive foreground — wordmark only, inside the circular safe zone.
    fg = Image.new("RGBA", (512, 512), (255, 255, 255, 0))
    fg.putalpha(wordmark_mask(512, ADAPTIVE_MARK_FRACTION))
    write(ASSETS / "android-icon-foreground.png", fg)

    write(ASSETS / "android-icon-background.png", Image.new("RGBA", (512, 512), (*FUCHSIA, 255)))

    mono = Image.new("RGBA", (432, 432), (255, 255, 255, 0))
    mono.putalpha(wordmark_mask(432, ADAPTIVE_MARK_FRACTION))
    write(ASSETS / "android-icon-monochrome.png", mono)

    # Splash — expo-splash-screen paints backgroundColor #FF0061 behind this.
    splash = Image.new("RGBA", (1024, 1024), (255, 255, 255, 0))
    splash.putalpha(wordmark_mask(1024, 1.0))
    write(ASSETS / "splash-icon.png", splash)

    if any(band.getextrema()[0] < 255 for band in [ios.convert("RGBA").getchannel("A")]):
        raise SystemExit("iOS icon must be fully opaque")


if __name__ == "__main__":
    main()
