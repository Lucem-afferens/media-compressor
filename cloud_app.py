"""Vercel/cloud deployment: image optimization only (no ffmpeg, no local privacy claims)."""

from __future__ import annotations

import asyncio
import io
import os
import re
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

import images as images_mod

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ALLOWED_IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
)

ImageOutput = Literal["auto", "jpeg", "png", "webp"]
PngStrategy = Literal["lossless", "smart"]
ImageUpscale = Literal["none", "2k", "4k"]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _max_upload_bytes() -> int:
    # Vercel request body ~4.5 MB; default cloud cap is conservative.
    return max(256 * 1024, _env_int("MAX_UPLOAD_MB", 4) * 1024 * 1024)


def _image_max_megapixels() -> int:
    return max(4, _env_int("MAX_IMAGE_MEGAPIXELS", 20))


def _max_image_batch() -> int:
    return max(1, min(20, _env_int("MAX_IMAGE_BATCH", 8)))


def _tmpdir() -> Path:
    raw = os.environ.get("MEDIA_COMPRESS_TMPDIR") or os.environ.get("VIDEO_COMPRESS_TMPDIR")
    return Path(raw if raw and raw.strip() else tempfile.gettempdir())


def _fmt_bytes(n: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    if i == 0:
        return f"{int(v)} {units[i]}"
    return f"{v:.2f} {units[i]}"


def _zip_image_arcname(index: int, stem: str, out_suffix: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", stem, flags=re.UNICODE).strip("._ ") or "image"
    s = s[:120]
    return f"{index:03d}_{s}{out_suffix}"


def _safe_filename_parts(
    raw: str | None,
    *,
    default_suffix: str,
    allowed_suffixes: frozenset[str],
    default_stem: str,
) -> tuple[str, str]:
    if not raw or not str(raw).strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "missing_filename", "message": "Не указано имя файла."},
        )
    name = Path(str(raw)).name
    if not name or name in {".", ".."}:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_filename", "message": "Некорректное имя файла."},
        )
    stem = Path(name).stem
    suffix = (Path(name).suffix or default_suffix).lower()
    stem = re.sub(r"[^\w\-. ]+", "_", stem, flags=re.UNICODE).strip("._ ") or default_stem
    stem = stem[:160]
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "unsupported_format",
                "message": f"Формат {suffix!r} не поддерживается.",
            },
        )
    return stem, suffix


async def _write_upload_to_path(file: UploadFile, dest: Path, max_bytes: int) -> None:
    total = 0

    def _unlink() -> None:
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        with dest.open("wb") as out_f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    _unlink()
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "file_too_large",
                            "message": f"Файл больше лимита {_fmt_bytes(max_bytes)}.",
                        },
                    )
                out_f.write(chunk)
    finally:
        await file.close()

    if total == 0:
        _unlink()
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_file", "message": "Пустой файл."},
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.max_upload_bytes = _max_upload_bytes()
    try:
        __import__("PIL.Image")
        app.state.pillow_available = True
    except Exception:
        app.state.pillow_available = False
    yield


app = FastAPI(title="Media Compressor Cloud", version="0.6.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request=request,
        name="cloud.html",
        context={
            "max_upload_human": _fmt_bytes(app.state.max_upload_bytes),
            "local_repo_url": "https://github.com/Lucem-afferens/media-compressor",
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    pillow_ok = bool(getattr(app.state, "pillow_available", False))
    return {
        "status": "ok" if pillow_ok else "degraded",
        "deployment": "cloud",
        "ffmpeg": False,
        "pillow": pillow_ok,
        "opencv": False,
        "max_upload_bytes": getattr(app.state, "max_upload_bytes", _max_upload_bytes()),
    }


@app.get("/api/settings")
def api_settings() -> dict[str, Any]:
    max_b = getattr(app.state, "max_upload_bytes", _max_upload_bytes())
    pillow_ok = bool(getattr(app.state, "pillow_available", False))
    return {
        "deployment": "cloud",
        "max_upload_bytes": max_b,
        "max_upload_human": _fmt_bytes(max_b),
        "ffmpeg_available": False,
        "image_optimization": {
            "available": pillow_ok,
            "allowed_suffixes": sorted(ALLOWED_IMAGE_SUFFIXES),
            "max_megapixels": _image_max_megapixels(),
            "endpoint": "/optimize-image",
            "output_modes": [
                {"id": "auto", "label": "Авто"},
                {"id": "jpeg", "label": "JPEG"},
                {"id": "png", "label": "PNG"},
                {"id": "webp", "label": "WebP"},
            ],
            "png_strategies": [
                {"id": "smart", "label": "Умный PNG"},
                {"id": "lossless", "label": "PNG без потерь"},
            ],
            "batch_endpoint": "/optimize-images",
            "max_batch_files": _max_image_batch(),
            "upscale_modes": [
                {"id": "none", "label": "Без увеличения"},
                {"id": "2k", "label": "До ~2K"},
                {"id": "4k", "label": "До ~4K"},
            ],
            "inpaint_remove": {"available": False},
        },
        "audio_optimization": {"available": False, "outputs": []},
    }


@app.post("/optimize-image")
async def optimize_image(
    request: Request,
    file: UploadFile = File(...),
    output: ImageOutput = "auto",
    quality: int = 85,
    max_side: int = 0,
    strip_metadata: bool = True,
    png_strategy: PngStrategy = "smart",
    webp_lossless: bool = False,
    upscale: ImageUpscale = "none",
) -> Response:
    if not getattr(request.app.state, "pillow_available", False):
        raise HTTPException(status_code=503, detail={"code": "pillow_missing", "message": "Pillow недоступен."})

    stem, suffix = _safe_filename_parts(
        file.filename,
        default_suffix=".jpg",
        allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
        default_stem="image",
    )
    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())

    if quality < 40 or quality > 100:
        raise HTTPException(status_code=400, detail={"code": "invalid_quality", "message": "Качество 40…100."})
    if max_side != 0 and (max_side < 64 or max_side > 16384):
        raise HTTPException(status_code=400, detail={"code": "invalid_max_side", "message": "max_side: 0 или 64…16384."})

    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    in_path = tmp_root / f"cloud-img-{uuid.uuid4().hex}-in{suffix}"

    try:
        await _write_upload_to_path(file, in_path, max_bytes)
        raw = in_path.read_bytes()
        in_path.unlink(missing_ok=True)

        try:
            out_bytes, media_type, out_suffix = await asyncio.to_thread(
                images_mod.optimize_image,
                raw,
                input_suffix=suffix,
                output=output,
                quality=quality,
                max_side=max_side,
                strip_metadata=strip_metadata,
                png_strategy=png_strategy,
                webp_lossless=webp_lossless,
                upscale=upscale,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail={"code": "image_optimize_failed", "message": str(e)}) from e

        download_name = f"{stem}.optimized{out_suffix}"
        return Response(
            content=out_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
        )
    except HTTPException:
        raise
    finally:
        in_path.unlink(missing_ok=True)


@app.post("/optimize-images")
async def optimize_images_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    output: ImageOutput = "auto",
    quality: int = 85,
    max_side: int = 0,
    strip_metadata: bool = True,
    png_strategy: PngStrategy = "smart",
    webp_lossless: bool = False,
    upscale: ImageUpscale = "none",
) -> FileResponse:
    if not getattr(request.app.state, "pillow_available", False):
        raise HTTPException(status_code=503, detail={"code": "pillow_missing", "message": "Pillow недоступен."})

    max_batch = _max_image_batch()
    if len(files) < 1:
        raise HTTPException(status_code=400, detail={"code": "no_files", "message": "Добавьте хотя бы один файл."})
    if len(files) > max_batch:
        raise HTTPException(
            status_code=400,
            detail={"code": "too_many_files", "message": f"Не больше {max_batch} файлов за раз."},
        )

    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())
    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    zip_path = tmp_root / f"cloud-batch-{job_id}.zip"

    def _unlink_best_effort(p: Path) -> None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        async def _process_upload(i: int, upload: UploadFile) -> tuple[int, str, bytes]:
            stem, suffix = _safe_filename_parts(
                upload.filename,
                default_suffix=".jpg",
                allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
                default_stem="image",
            )
            in_path = tmp_root / f"cloud-batch-{job_id}-{i:04d}-in{suffix}"
            await _write_upload_to_path(upload, in_path, max_bytes)
            raw = in_path.read_bytes()
            _unlink_best_effort(in_path)

            out_bytes, _media_type, out_suffix = await asyncio.to_thread(
                images_mod.optimize_image,
                raw,
                input_suffix=suffix,
                output=output,
                quality=quality,
                max_side=max_side,
                strip_metadata=strip_metadata,
                png_strategy=png_strategy,
                webp_lossless=webp_lossless,
                upscale=upscale,
            )
            arc = _zip_image_arcname(i + 1, stem, out_suffix)
            return i, arc, out_bytes

        results = await asyncio.gather(*[_process_upload(i, u) for i, u in enumerate(files)])

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for _i, arc, out_bytes in sorted(results, key=lambda x: x[0]):
                zf.writestr(arc, out_bytes, compress_type=zipfile.ZIP_STORED)

        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=f"images-optimized-{job_id[:8]}.zip",
            background=BackgroundTask(_unlink_best_effort, zip_path),
        )
    except HTTPException:
        _unlink_best_effort(zip_path)
        raise
    except Exception:
        _unlink_best_effort(zip_path)
        raise
