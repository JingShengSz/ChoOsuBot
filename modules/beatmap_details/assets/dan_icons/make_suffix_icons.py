"""Draw high/low suffix marks using the palette and bevel of ln8.webp.

The source archive's icons use 1920×1080 transparent canvases. Keep that
canvas size so a renderer can place these marks by the same image convention.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
SCALE = 3
LOCAL_SIZE = (560, 540)
CANVAS_SIZE = (1920, 1080)


def shape(kind: str, inset: int) -> Image.Image:
    size = tuple(v * SCALE for v in LOCAL_SIZE)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    radius = max(7, 22 - inset // 2) * SCALE
    left, right = 60 + inset, 500 - inset
    top, bottom = 230 + inset, 310 - inset
    draw.rounded_rectangle(
        (left * SCALE, top * SCALE, right * SCALE, bottom * SCALE),
        radius=radius,
        fill=255,
    )
    if kind == "plus":
        left, right = 240 + inset, 320 - inset
        top, bottom = 60 + inset, 480 - inset
        draw.rounded_rectangle(
            (left * SCALE, top * SCALE, right * SCALE, bottom * SCALE),
            radius=radius,
            fill=255,
        )
    return mask


def layer(color: tuple[int, int, int], mask: Image.Image) -> Image.Image:
    image = Image.new("RGBA", mask.size, color + (0,))
    image.putalpha(mask)
    return image


def gradient(mask: Image.Image) -> Image.Image:
    width, height = mask.size
    image = Image.new("RGBA", mask.size)
    draw = ImageDraw.Draw(image)
    upper, lower = (255, 197, 87), (247, 162, 43)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(round(a * (1 - t) + b * t) for a, b in zip(upper, lower))
        draw.line((0, y, width, y), fill=color + (255,))
    image.putalpha(mask)
    return image


def make_icon(kind: str) -> Image.Image:
    outer = shape(kind, 0)
    bevel = shape(kind, 10)
    core = shape(kind, 17)
    image = Image.new("RGBA", outer.size, (0, 0, 0, 0))

    shadow = ImageChops.offset(outer, 4 * SCALE, 6 * SCALE)
    shadow = shadow.point(lambda a: round(a * 0.55))
    image.alpha_composite(layer((48, 31, 24), shadow))
    image.alpha_composite(layer((102, 65, 31), outer))
    image.alpha_composite(layer((166, 110, 41), bevel))
    image.alpha_composite(gradient(core))

    # Subtle inner light on the top and left, shade on the lower edge.
    light = ImageChops.subtract(core, ImageChops.offset(core, 4 * SCALE, 5 * SCALE))
    light = light.filter(ImageFilter.GaussianBlur(2 * SCALE))
    light = light.point(lambda a: round(a * 0.48))
    image.alpha_composite(layer((255, 223, 132), light))
    shade = ImageChops.subtract(core, ImageChops.offset(core, -4 * SCALE, -5 * SCALE))
    shade = shade.filter(ImageFilter.GaussianBlur(2 * SCALE))
    shade = shade.point(lambda a: round(a * 0.35))
    image.alpha_composite(layer((180, 110, 35), shade))

    image = image.resize(LOCAL_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(image, ((CANVAS_SIZE[0] - LOCAL_SIZE[0]) // 2,
                                   (CANVAS_SIZE[1] - LOCAL_SIZE[1]) // 2))
    return canvas


def preview(images: list[tuple[str, Image.Image]]) -> None:
    background = Image.new("RGB", (1740, 600), (15, 25, 42))
    draw = ImageDraw.Draw(background)
    for index, (label, icon) in enumerate(images):
        left = 20 + 580 * index
        crop = icon.crop((680, 270, 1240, 810))
        background.paste(crop, (left, 10), crop)
        draw.text((left + 12, 565), label, fill=(206, 225, 243))
    background.save(HERE / "suffix_preview.png")


def main() -> None:
    plus = make_icon("plus")
    minus = make_icon("minus")
    plus.save(HERE / "plus.webp", lossless=True, method=6)
    minus.save(HERE / "minus.webp", lossless=True, method=6)
    preview([("ln8.webp / reference", Image.open(HERE / "ln8.webp").convert("RGBA")),
             ("plus.webp / high", plus), ("minus.webp / low", minus)])
    for name in ("plus.webp", "minus.webp"):
        image = Image.open(HERE / name)
        print(name, image.size, image.mode, image.getbbox())


if __name__ == "__main__":
    main()
