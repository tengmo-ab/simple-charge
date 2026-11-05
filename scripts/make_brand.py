#!/usr/bin/env python3
"""Draw the Simple Charge brand images.

Icon: price bars where the cheapest bar carries a lightning bolt.
Writes custom_components/simple_charge/brand/{icon,icon@2x,logo,logo@2x}.png
(Home Assistant 2026.3+ serves brand images shipped inside a custom integration)
and docs/logo.png for the README.

    python3 scripts/make_brand.py      # needs Pillow
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "custom_components" / "simple_charge" / "brand"
DOCS = ROOT / "docs"
S = 2048  # draw large, downsample for smooth edges

TOP = (13, 148, 136)  # teal
BOTTOM = (21, 94, 117)  # deep blue-teal
BAR = (255, 255, 255, 235)
CHEAP = (250, 204, 21, 255)  # amber
BOLT = (21, 94, 117, 255)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def icon() -> Image.Image:
    gradient = Image.new("RGBA", (S, S))
    px = gradient.load()
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            px[x, y] = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(gradient, (0, 0), mask)

    d = ImageDraw.Draw(img)
    base = int(S * 0.80)
    width = int(S * 0.13)
    gap = int(S * 0.045)
    heights = [0.42, 0.30, 0.14, 0.24, 0.36]  # the middle one is the cheap quarter
    left = (S - (len(heights) * width + (len(heights) - 1) * gap)) // 2
    for i, h in enumerate(heights):
        x0 = left + i * (width + gap)
        top = base - int(S * h)
        d.rounded_rectangle((x0, top, x0 + width, base), radius=int(width * 0.28), fill=CHEAP if i == 2 else BAR)

    # Lightning bolt above the cheap bar.
    cx = left + 2 * (width + gap) + width // 2
    top = int(S * 0.14)
    h = int(S * 0.44)
    w = int(S * 0.30)
    bolt = [
        (cx + w * 0.10, top),
        (cx - w * 0.42, top + h * 0.56),
        (cx - w * 0.02, top + h * 0.56),
        (cx - w * 0.14, top + h),
        (cx + w * 0.42, top + h * 0.40),
        (cx + w * 0.02, top + h * 0.40),
        (cx + w * 0.18, top),
    ]
    shadow = [(x + S * 0.012, y + S * 0.012) for x, y in bolt]
    d.polygon(shadow, fill=(0, 0, 0, 60))
    d.polygon(bolt, fill=CHEAP)
    d.line(bolt + [bolt[0]], fill=BOLT, width=int(S * 0.012), joint="curve")
    return img


def logo(icon_img: Image.Image, height: int) -> Image.Image:
    ic = icon_img.resize((height, height), Image.LANCZOS)
    font = ImageFont.truetype(FONT, int(height * 0.42))
    text = "Simple Charge"
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad = int(height * 0.18)
    out = Image.new("RGBA", (height + pad + tw + 4, height), (0, 0, 0, 0))
    out.paste(ic, (0, 0), ic)
    ImageDraw.Draw(out).text(
        (height + pad - box[0], (height - th) // 2 - box[1]), text, font=font, fill=BOTTOM + (255,)
    )
    return out


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    DOCS.mkdir(parents=True, exist_ok=True)
    big = icon()
    big.resize((256, 256), Image.LANCZOS).save(BRAND / "icon.png", optimize=True)
    big.resize((512, 512), Image.LANCZOS).save(BRAND / "icon@2x.png", optimize=True)
    logo(big, 128).save(BRAND / "logo.png", optimize=True)
    logo(big, 256).save(BRAND / "logo@2x.png", optimize=True)
    logo(big, 160).save(DOCS / "logo.png", optimize=True)
    print("brand images written")


if __name__ == "__main__":
    main()
