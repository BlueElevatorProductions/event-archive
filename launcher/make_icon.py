# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=10"]
# ///
"""Draw the Event Archive app icon (a ticket stub) -> launcher/icon-1024.png.
Run:  uv run launcher/make_icon.py"""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 4                     # supersample
N = 1024 * S
OUT = Path(__file__).resolve().parent / "icon-1024.png"


def font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial Black.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def background():
    # macOS icon grid: 824px rounded square centred on a 1024 canvas
    g = Image.new("RGB", (N, N))
    d = ImageDraw.Draw(g)
    top, bot = (58, 28, 94), (16, 14, 40)
    for y in range(N):
        t = y / N
        d.line([(0, y), (N, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)))
    glow = Image.new("L", (N, N), 0)
    ImageDraw.Draw(glow).ellipse([N * .1, -N * .25, N * .9, N * .5], fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(N * .09))
    g = Image.composite(Image.new("RGB", (N, N), (214, 92, 150)), g, glow)
    mask = Image.new("L", (N, N), 0)
    m = 100 * S
    ImageDraw.Draw(mask).rounded_rectangle([m, m, N - m, N - m], radius=185 * S, fill=255)
    out = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    out.paste(g, (0, 0), mask)
    return out, mask


def ticket():
    w, h = 640 * S, 330 * S
    pad = 60 * S
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = pad, pad, pad + w, pad + h
    cream, ink, accent = (250, 240, 215), (40, 26, 60), (214, 72, 96)
    d.rounded_rectangle([x0, y0, x1, y1], radius=26 * S, fill=cream)
    perf = x0 + int(w * .70)
    r = 26 * S
    for cy in (y0, y1):                       # notches where the stub tears off
        d.ellipse([perf - r, cy - r, perf + r, cy + r], fill=(0, 0, 0, 0))
    for i in range(9):                        # perforation
        cy = y0 + r + 14 * S + i * (h - 2 * r - 28 * S) / 8
        d.ellipse([perf - 5 * S, cy - 5 * S, perf + 5 * S, cy + 5 * S], fill=(0, 0, 0, 0))
    d.rounded_rectangle([x0 + 18 * S, y0 + 18 * S, perf - 26 * S, y1 - 18 * S], radius=14 * S, outline=accent, width=5 * S)
    # star
    cx, cy, ro, ri = x0 + 92 * S, (y0 + y1) // 2, 46 * S, 19 * S
    pts = [(cx + (ro if k % 2 == 0 else ri) * math.sin(k * math.pi / 5), cy - (ro if k % 2 == 0 else ri) * math.cos(k * math.pi / 5)) for k in range(10)]
    d.polygon(pts, fill=accent)
    f1, f2 = font(64 * S), font(27 * S)
    tx = x0 + 158 * S
    d.text((tx, cy - 74 * S), "ADMIT", font=f1, fill=ink)
    d.text((tx, cy - 6 * S), "ONE", font=f1, fill=ink)
    d.text((tx + 172 * S, cy + 22 * S), "LIVE", font=f2, fill=accent)
    # barcode on the stub
    bx, widths = perf + 34 * S, [6, 3, 9, 3, 5, 10, 3, 6, 4, 9, 3, 6, 8, 3]
    for i, bw in enumerate(widths):
        if i % 2 == 0:
            d.rectangle([bx, y0 + 46 * S, bx + bw * S, y1 - 46 * S], fill=ink)
        bx += (bw + 4) * S
    return im.rotate(13, resample=Image.BICUBIC, expand=True)


def main():
    icon, mask = background()
    t = ticket()
    pos = ((N - t.width) // 2, (N - t.height) // 2 + 6 * S)
    shadow = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    sh = Image.new("RGBA", t.size, (10, 6, 24, 150))
    shadow.paste(sh, (pos[0], pos[1] + 22 * S), t.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(20 * S))
    icon = Image.alpha_composite(icon, shadow)
    layer = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    layer.paste(t, pos, t)
    icon = Image.alpha_composite(icon, layer)
    clipped = Image.new("RGBA", (N, N), (0, 0, 0, 0))   # keep everything inside the rounded square
    clipped.paste(icon, (0, 0), mask)
    clipped.resize((1024, 1024), Image.LANCZOS).save(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
