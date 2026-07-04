"""Image optimization: progressive JPEG, optimized PNG, WebP; EXIF handling; safe limits."""

from __future__ import annotations

import io
import os
from typing import Literal

from PIL import Image, ImageOps

OutputFormat = Literal["auto", "jpeg", "png", "webp"]
PngStrategy = Literal["lossless", "smart"]
UpscaleMode = Literal["none", "2k", "4k"]

# Длинная сторона «как у 2K/4K» для фото (без внешних API — только Lanczos в Pillow).
_UPSCALE_LONG_SIDE = {"2k": 2048, "4k": 3840}

# Pillow decompression bomb guard (configurable via env in caller)
_DEFAULT_MAX_PIXELS = 50_000_000


def _max_pixels() -> int:
    try:
        v = int(os.environ.get("MAX_IMAGE_MEGAPIXELS", "50"))
        return max(4, v) * 1_000_000
    except ValueError:
        return _DEFAULT_MAX_PIXELS


def _auto_format_from_suffix(suffix: str) -> Literal["jpeg", "png", "webp"]:
    s = suffix.lower()
    if s in (".jpg", ".jpeg", ".jfif"):
        return "jpeg"
    if s == ".png":
        return "png"
    if s == ".webp":
        return "webp"
    return "webp"


def _resolve_output_format(output: OutputFormat, input_suffix: str) -> Literal["jpeg", "png", "webp"]:
    if output == "auto":
        return _auto_format_from_suffix(input_suffix)
    if output == "jpeg":
        return "jpeg"
    if output == "png":
        return "png"
    return "webp"


def _flatten_rgba_for_jpeg(im: Image.Image, bg: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    if im.mode in ("RGBA", "LA"):
        base = Image.new("RGB", im.size, bg)
        base.paste(im, mask=im.split()[-1])
        return base
    if im.mode == "P":
        im = im.convert("RGBA")
        return _flatten_rgba_for_jpeg(im, bg)
    return im.convert("RGB")


def _resize_max_side(im: Image.Image, max_side: int) -> Image.Image:
    if max_side <= 0:
        return im
    w, h = im.size
    m = max(w, h)
    if m <= max_side:
        return im
    scale = max_side / m
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def _upscale_long_side_if_smaller(
    im: Image.Image,
    mode: UpscaleMode,
    *,
    max_pixels: int,
) -> Image.Image:
    """
    Увеличивает изображение так, чтобы длинная сторона стала target, если она меньше target.
    Классическая интерполяция (Lanczos), без нейросетей — не «дорисовывает» детали.
    """
    if mode == "none":
        return im
    target = _UPSCALE_LONG_SIDE.get(mode)
    if not target or target <= 0:
        return im
    w, h = im.size
    m = max(w, h)
    if m >= target:
        return im
    scale = target / m
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    if nw * nh > max_pixels:
        raise ValueError(
            f"После увеличения получится слишком много пикселей ({nw}×{nh}). "
            "Уменьшите исходник, поднимите MAX_IMAGE_MEGAPIXELS или отключите увеличение."
        )
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def _strip_exif(im: Image.Image) -> Image.Image:
    """Return a copy without EXIF payload (keeps pixels)."""
    out = im.copy()
    if hasattr(out, "getexif"):
        try:
            ex = out.getexif()
            if ex is not None:
                ex.clear()
        except Exception:
            pass
    out.info.pop("exif", None)
    return out


def optimize_image(
    data: bytes,
    *,
    input_suffix: str,
    output: OutputFormat,
    quality: int,
    max_side: int,
    strip_metadata: bool,
    png_strategy: PngStrategy,
    webp_lossless: bool,
    upscale: UpscaleMode = "none",
) -> tuple[bytes, str, str]:
    """
    Returns (payload, media_type, download_suffix including dot).
    Raises ValueError with user-facing message on invalid input.
    """
    max_px = _max_pixels()
    buf_in = io.BytesIO(data)
    try:
        im = Image.open(buf_in)
        im.load()
    except Exception as e:
        raise ValueError("Не удалось прочитать изображение. Проверьте формат и целостность файла.") from e

    n_frames = getattr(im, "n_frames", 1)
    if n_frames > 1:
        im.seek(0)
        if im.format == "GIF":
            im = Image.alpha_composite(
                Image.new("RGBA", im.size, (255, 255, 255, 255)),
                im.convert("RGBA"),
            )
        else:
            im = im.copy()

    w, h = im.size
    if w * h > max_px:
        raise ValueError(
            f"Слишком большое изображение ({w}×{h} px). Лимит: ~{max_px // 1_000_000} мегапикселей (MAX_IMAGE_MEGAPIXELS)."
        )

    im = ImageOps.exif_transpose(im)
    if strip_metadata:
        im = _strip_exif(im)

    im = _upscale_long_side_if_smaller(im, upscale, max_pixels=max_px)
    im = _resize_max_side(im, max_side)

    target = _resolve_output_format(output, input_suffix)
    q = max(1, min(100, quality))

    out_buf = io.BytesIO()

    if target == "jpeg":
        base = _flatten_rgba_for_jpeg(im)
        base.save(
            out_buf,
            format="JPEG",
            quality=q,
            optimize=True,
            progressive=True,
            subsampling=2,
        )
        return out_buf.getvalue(), "image/jpeg", ".jpg"

    if target == "webp":
        if webp_lossless:
            im.save(out_buf, format="WEBP", lossless=True, method=6)
        else:
            im.save(out_buf, format="WEBP", quality=q, method=6, lossless=False)
        return out_buf.getvalue(), "image/webp", ".webp"

    # PNG
    if png_strategy == "smart":
        if im.mode == "LA":
            im = im.convert("RGBA")
        if im.mode == "RGBA":
            rgb = Image.new("RGB", im.size, (255, 255, 255))
            rgb.paste(im, mask=im.split()[-1])
            qimg = rgb
        elif im.mode != "RGB":
            qimg = im.convert("RGB")
        else:
            qimg = im
        pal = qimg.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        pal.save(out_buf, format="PNG", optimize=True, compress_level=9)
    else:
        if im.mode == "P":
            im = im.convert("RGBA")
        im.save(out_buf, format="PNG", optimize=True, compress_level=9)
    return out_buf.getvalue(), "image/png", ".png"
