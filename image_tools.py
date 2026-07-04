"""Восстановление фона по маске (OpenCV inpaint)."""

from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image, ImageOps


def assert_pixel_budget(data: bytes, max_megapixels: int) -> None:
    im = Image.open(io.BytesIO(data))
    im.load()
    w, h = im.size
    lim = max(4, int(max_megapixels)) * 1_000_000
    if w * h > lim:
        raise ValueError(
            f"Изображение слишком большое ({w}×{h} px). Лимит ~{max_megapixels} Мпикселей.",
        )


def _to_rgb_array(im: Image.Image) -> np.ndarray[Any, Any]:
    """BGR для OpenCV, без альфы (прозрачность на белый)."""
    im = im.convert("RGBA")
    arr = np.array(im)
    rgb = arr[:, :, :3].astype(np.float32)
    a = arr[:, :, 3:4].astype(np.float32) / 255.0
    bg = np.ones_like(rgb) * 255.0
    out = rgb * a + bg * (1.0 - a)
    bgr = out[..., ::-1].astype(np.uint8)
    return bgr


def inpaint_with_mask(
    image_bytes: bytes,
    mask_bytes: bytes,
    *,
    radius: int = 7,
    method: str = "telea",
) -> bytes:
    """
    mask: белое = зона для дорисовки (удалить объект / закрасить фон кистью).
    Размер маски приводится к размеру изображения.
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError("OpenCV не установлен.") from e

    try:
        im = Image.open(io.BytesIO(image_bytes))
        im.load()
    except Exception as e:
        raise ValueError("Не удалось прочитать изображение.") from e

    im = ImageOps.exif_transpose(im)
    w, h = im.size

    try:
        m_im = Image.open(io.BytesIO(mask_bytes))
        m_im.load()
    except Exception as e:
        raise ValueError("Не удалось прочитать маску.") from e

    mask = m_im.convert("L")
    if mask.size != (w, h):
        mask = mask.resize((w, h), Image.Resampling.NEAREST)

    mask_arr = np.array(mask)
    # белое = инпейнт
    bin_mask = (mask_arr > 127).astype(np.uint8) * 255
    if int(np.sum(bin_mask > 0)) < 80:
        raise ValueError("Маска слишком мала: закрасьте область кистью (белым) заметнее.")

    bgr = _to_rgb_array(im)
    r = max(1, min(32, int(radius)))
    flags = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    result_bgr = cv2.inpaint(bgr, bin_mask, r, flags)
    result_rgb = cv2.cvtColor(result_bgr, cv2.COLOR_BGR2RGB)
    out_im = Image.fromarray(result_rgb, mode="RGB")

    buf = io.BytesIO()
    out_im.save(buf, format="PNG", optimize=True, compress_level=6)
    return buf.getvalue()
