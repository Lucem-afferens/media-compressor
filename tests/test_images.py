"""Tests for Media Compressor."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app import _safe_filename_parts, ALLOWED_IMAGE_SUFFIXES, ALLOWED_SUFFIXES
from images import _auto_format_from_suffix, _resolve_output_format, optimize_image


class TestAutoFormat:
    def test_jpg_to_jpeg(self):
        assert _auto_format_from_suffix(".jpg") == "jpeg"

    def test_jfif_to_jpeg(self):
        assert _auto_format_from_suffix(".jfif") == "jpeg"

    def test_png_stays_png(self):
        assert _auto_format_from_suffix(".png") == "png"

    def test_unknown_to_webp(self):
        assert _auto_format_from_suffix(".gif") == "webp"

    def test_auto_mode_respects_suffix(self):
        assert _resolve_output_format("auto", ".jfif") == "jpeg"
        assert _resolve_output_format("auto", ".png") == "png"


class TestSafeFilename:
    def test_valid_mp4(self):
        stem, suffix = _safe_filename_parts(
            "my video.mp4",
            default_suffix=".mp4",
            allowed_suffixes=ALLOWED_SUFFIXES,
            default_stem="video",
        )
        assert stem == "my video"
        assert suffix == ".mp4"

    def test_unsupported_raises(self):
        with pytest.raises(HTTPException) as exc:
            _safe_filename_parts(
                "file.xyz",
                default_suffix=".jpg",
                allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
                default_stem="image",
            )
        assert exc.value.status_code == 415

    def test_empty_raises(self):
        with pytest.raises(HTTPException) as exc:
            _safe_filename_parts(
                "",
                default_suffix=".mp4",
                allowed_suffixes=ALLOWED_SUFFIXES,
                default_stem="video",
            )
        assert exc.value.status_code == 400


def _tiny_png() -> bytes:
    im = Image.new("RGB", (8, 8), color=(128, 64, 32))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestOptimizeImage:
    def test_png_to_jpeg(self):
        raw = _tiny_png()
        out, media_type, suffix = optimize_image(
            raw,
            input_suffix=".png",
            output="jpeg",
            quality=85,
            max_side=0,
            strip_metadata=True,
            png_strategy="smart",
            webp_lossless=False,
        )
        assert suffix == ".jpg"
        assert media_type == "image/jpeg"
        assert len(out) > 0

    def test_auto_jfif(self):
        raw = _tiny_png()
        _, _, suffix = optimize_image(
            raw,
            input_suffix=".jfif",
            output="auto",
            quality=85,
            max_side=0,
            strip_metadata=True,
            png_strategy="smart",
            webp_lossless=False,
        )
        assert suffix == ".jpg"
