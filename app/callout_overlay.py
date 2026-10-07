from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font(size: int):
    for path in _FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fit(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def create_callout_overlay(path: Path, callouts: list[str], vertical: bool = False) -> None:
    # Always materialize a transparent layer so temporal muxing has a deterministic input.
    # The layer is reusable by both still-image QA and the final temporal MP4.
    with Image.new("RGBA", (1920, 1080) if not vertical else (1080, 1920), (0, 0, 0, 0)) as image:
        w, h = image.size
        scale = max(1.0, w / 1920.0)
        font_size = int((29 if vertical else 31) * scale)
        small_size = int((17 if vertical else 18) * scale)
        font = _font(font_size)
        small = _font(small_size)
        chosen = [_fit(x, 34 if vertical else 42) for x in callouts[:2] if str(x).strip()]
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        if not chosen:
            overlay.save(path, format="PNG", optimize=False, compress_level=1)
            return
        pad = int(24 * scale)
        line_h = int(font_size * 1.35)
        box_w = int(w * (0.48 if vertical else 0.34))
        box_h = pad * 2 + line_h * len(chosen) + int(24 * scale)
        x0 = pad
        y0 = int(h * (0.08 if vertical else 0.075))
        d = ImageDraw.Draw(overlay)
        d.rounded_rectangle(
            (x0, y0, x0 + box_w, y0 + box_h),
            radius=int(18 * scale),
            fill=(7, 12, 18, 214),
            outline=(182, 145, 78, 190),
            width=max(2, int(2 * scale)),
        )
        d.text((x0 + pad, y0 + int(8 * scale)), "DETAIL", font=small, fill=(206, 173, 104, 255))
        for idx, text in enumerate(chosen):
            d.text(
                (x0 + pad, y0 + int(27 * scale) + idx * line_h),
                text,
                font=font,
                fill=(242, 245, 248, 255),
                stroke_width=max(1, int(scale)),
                stroke_fill=(0, 0, 0, 220),
                direction="rtl" if hasattr(d, "textbbox") else None,
            )
        overlay.save(path, format="PNG", optimize=False, compress_level=1)


def apply_callout_overlay(path: Path, callouts: list[str], vertical: bool = False) -> None:
    if not callouts:
        return
    overlay_path = path.with_name(path.stem + ".callouts.png")
    create_callout_overlay(overlay_path, callouts, vertical=vertical)
    with Image.open(path).convert("RGBA") as image, Image.open(overlay_path).convert("RGBA") as overlay:
        image = Image.alpha_composite(image, overlay)
        image.convert("RGB").save(path, format="PNG", optimize=False, compress_level=1)
    overlay_path.unlink(missing_ok=True)
