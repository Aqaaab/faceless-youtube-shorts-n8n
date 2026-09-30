from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .arabic_font import discover
from .core import RUN, Story

SIZE = (1280, 720)


def generate_thumbnail(story: Story, out: Path = RUN / "thumbnail.jpg") -> Path:
    source = RUN / "scenes" / "scene_01.png"
    if not source.is_file():
        raise FileNotFoundError(source)
    font_info = discover()
    try:
        title_font = ImageFont.truetype(font_info["file"], size=54)
    except OSError as exc:
        raise RuntimeError(f"Thumbnail font load failed: {exc}") from exc
    with Image.open(source).convert("RGB") as image:
        image = ImageOps.fit(image, SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
        canvas = image.copy().convert("RGBA")
        overlay = Image.new("RGBA", SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for y in range(SIZE[1]):
            alpha = int(175 * max(0.0, 1.0 - y / SIZE[1]))
            draw.line((0, y, SIZE[0], y), fill=(0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)
        title = " ".join(str(story.title).split()) or story.topic
        lines = textwrap.wrap(title, width=24, break_long_words=False, break_on_hyphens=False)[:3]
        y = 74
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = SIZE[0] - (bbox[2] - bbox[0]) - 54
            draw.text((x + 3, y + 3), line, font=title_font, fill=(0, 0, 0, 210))
            draw.text((x, y), line, font=title_font, fill=(250, 250, 250, 255))
            y += 68
        out.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    return out
