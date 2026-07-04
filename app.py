from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

import image_tools as image_tools_mod
import images as images_mod
from jobs import JobPhase, job_store, run_ffmpeg_with_progress

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

PRESETS: tuple[str, ...] = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)

ALLOWED_SUFFIXES: frozenset[str] = frozenset(
    {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".mpg"}
)

ALLOWED_IMAGE_SUFFIXES: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
)

ALLOWED_AUDIO_ONLY_SUFFIXES: frozenset[str] = frozenset(
    {
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".m4a",
        ".ogg",
        ".opus",
        ".wma",
        ".aiff",
        ".aif",
        ".mp2",
        ".mka",
        ".webm",  # может быть только аудио
    }
)

ALLOWED_AUDIO_INPUT_SUFFIXES: frozenset[str] = ALLOWED_AUDIO_ONLY_SUFFIXES | ALLOWED_SUFFIXES

ScaleMode = Literal["none", "1080", "720", "480"]
ImageOutput = Literal["auto", "jpeg", "png", "webp"]
PngStrategy = Literal["lossless", "smart"]
ImageUpscale = Literal["none", "2k", "4k"]
AudioOutput = Literal["mp3", "aac_m4a", "opus", "flac"]
AudioBitrateMode = Literal["cbr", "vbr"]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _tmpdir() -> Path:
    """Temp directory for uploads and ffmpeg output."""
    raw = os.environ.get("MEDIA_COMPRESS_TMPDIR") or os.environ.get("VIDEO_COMPRESS_TMPDIR")
    return Path(raw if raw and raw.strip() else tempfile.gettempdir())


def _deployment_mode() -> Literal["local", "cloud"]:
    explicit = os.environ.get("DEPLOYMENT_MODE", "").strip().lower()
    if explicit in ("local", "cloud"):
        return explicit  # type: ignore[return-value]
    if (
        os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("RAILWAY_SERVICE_NAME")
        or os.environ.get("RENDER")
        or os.environ.get("RENDER_SERVICE_NAME")
    ):
        return "cloud"
    return "local"


def _max_upload_bytes() -> int:
    default_mb = 512 if _deployment_mode() == "cloud" else 2048
    return max(1 * 1024 * 1024, _env_int("MAX_UPLOAD_MB", default_mb) * 1024 * 1024)


def _ffmpeg_timeout_sec() -> int | None:
    t = _env_int("FFMPEG_TIMEOUT_SEC", 0)
    return t if t > 0 else None


def _image_max_megapixels() -> int:
    return max(4, _env_int("MAX_IMAGE_MEGAPIXELS", 50))


def _max_image_batch() -> int:
    return max(1, min(100, _env_int("MAX_IMAGE_BATCH", 40)))


def _run_ffmpeg_subprocess(cmd: list[str], timeout: int | None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def _zip_image_arcname(index: int, stem: str, out_suffix: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", stem, flags=re.UNICODE).strip("._ ") or "image"
    s = s[:120]
    return f"{index:03d}_{s}{out_suffix}"


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
                "message": f"Формат {suffix!r} не поддерживается. Допустимо: {', '.join(sorted(allowed_suffixes))}.",
            },
        )
    return stem, suffix


def _scale_filter(mode: ScaleMode) -> str | None:
    if mode == "none":
        return None
    caps = {"1080": 1920, "720": 1280, "480": 854}
    wmax = caps[mode]
    return f"scale=w=min({wmax}\\,iw):h=-2"


def _audio_media_type_and_suffix(output: AudioOutput) -> tuple[str, str]:
    if output == "mp3":
        return "audio/mpeg", ".mp3"
    if output == "aac_m4a":
        return "audio/mp4", ".m4a"
    if output == "opus":
        return "audio/opus", ".opus"
    return "audio/flac", ".flac"


def _build_optimize_audio_cmd(
    ffmpeg: str,
    in_path: Path,
    out_path: Path,
    *,
    output: AudioOutput,
    bitrate_mode: AudioBitrateMode,
    bitrate_k: int,
    vbr_quality: int,
    mono: bool,
    sample_rate: int,
    normalize: bool,
    strip_metadata: bool,
) -> list[str]:
    cmd: list[str] = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        os.environ.get("FFMPEG_LOGLEVEL", "error"),
        "-y",
        "-i",
        str(in_path),
    ]
    if strip_metadata:
        cmd += ["-map_metadata", "-1"]
    cmd += ["-vn", "-map", "0:a:0"]
    af: list[str] = []
    if normalize:
        af.append("dynaudnorm=f=150:g=15")
    if af:
        cmd += ["-af", ",".join(af)]
    if mono:
        cmd += ["-ac", "1"]
    if sample_rate > 0:
        cmd += ["-ar", str(sample_rate)]

    if output == "mp3":
        cmd += ["-c:a", "libmp3lame"]
        if bitrate_mode == "vbr":
            vq = max(0, min(9, vbr_quality))
            cmd += ["-q:a", str(vq)]
        else:
            br = max(64, min(320, bitrate_k))
            cmd += ["-b:a", f"{br}k"]
    elif output == "aac_m4a":
        br = max(64, min(320, bitrate_k))
        cmd += ["-c:a", "aac", "-b:a", f"{br}k"]
    elif output == "opus":
        br = max(32, min(510, bitrate_k))
        cmd += ["-c:a", "libopus", "-b:a", f"{br}k", "-vbr", "1"]
    else:
        cmd += ["-c:a", "flac", "-compression_level", "8"]

    cmd.append(str(out_path))
    return cmd


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
    app.state.deployment_mode = _deployment_mode()
    app.state.ffmpeg_path = shutil.which("ffmpeg")
    app.state.max_upload_bytes = _max_upload_bytes()
    try:
        __import__("PIL.Image")
        app.state.pillow_available = True
    except Exception:
        app.state.pillow_available = False
    try:
        __import__("cv2")
        app.state.opencv_available = True
    except Exception:
        app.state.opencv_available = False
    yield


app = FastAPI(title="Media Compressor", version="0.6.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    mode = getattr(request.app.state, "deployment_mode", "local")
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "max_upload_human": _fmt_bytes(app.state.max_upload_bytes),
            "deployment": mode,
            "local_repo_url": "https://github.com/Lucem-afferens/media-compressor",
        },
    )


@app.get("/health")
def health() -> dict[str, Any]:
    ffmpeg_ok = bool(getattr(app.state, "ffmpeg_path", None))
    pillow_ok = bool(getattr(app.state, "pillow_available", False))
    core_ok = ffmpeg_ok or pillow_ok
    return {
        "status": "ok" if core_ok else "degraded",
        "deployment": getattr(app.state, "deployment_mode", "local"),
        "ffmpeg": ffmpeg_ok,
        "pillow": pillow_ok,
        "opencv": bool(getattr(app.state, "opencv_available", False)),
        "max_upload_bytes": getattr(app.state, "max_upload_bytes", _max_upload_bytes()),
    }


@app.get("/jobs/{job_id}/progress")
def job_progress(job_id: str) -> dict[str, Any]:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Задача не найдена."})
    snap = job.snapshot()
    if job.phase == JobPhase.ERROR:
        snap["error"] = job.error
    return snap


@app.delete("/jobs/{job_id}")
def job_cancel(job_id: str) -> dict[str, bool]:
    if not job_store.cancel(job_id):
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Задача не найдена."})
    return {"cancelled": True}


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str) -> FileResponse:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Задача не найдена."})
    if job.phase == JobPhase.ERROR:
        raise HTTPException(
            status_code=422,
            detail={"code": "job_failed", "message": job.error or "Ошибка обработки.", "stderr_tail": job.stderr_tail},
        )
    if job.phase != JobPhase.DONE or not job.result_path or not job.result_path.exists():
        raise HTTPException(status_code=409, detail={"code": "job_not_ready", "message": "Результат ещё не готов."})

    result_path = job.result_path
    download_name = job.download_name or "download.bin"
    media_type = job.media_type or "application/octet-stream"

    def _cleanup() -> None:
        try:
            result_path.unlink(missing_ok=True)
        except OSError:
            pass
        job_store.remove(job_id)

    return FileResponse(
        path=str(result_path),
        media_type=media_type,
        filename=download_name,
        background=BackgroundTask(_cleanup),
    )


def _start_ffmpeg_job(
    job_id: str,
    kind: str,
    cmd: list[str],
    *,
    in_path: Path,
    out_path: Path,
    download_name: str,
    media_type: str,
    timeout: int | None,
    cleanup_paths: list[Path],
) -> None:
    job = job_store.create(job_id, kind)

    def _run() -> None:
        try:
            run_ffmpeg_with_progress(job, cmd, in_path=in_path, timeout=timeout)
            if not out_path.exists() or out_path.stat().st_size == 0:
                with job._lock:
                    job.phase = JobPhase.ERROR
                    job.error = "На выходе получился пустой файл."
                return
            with job._lock:
                job.result_path = out_path
                job.download_name = download_name
                job.media_type = media_type
                job.phase = JobPhase.DONE
                job.percent = 100.0
                job.message = "Готово"
        except subprocess.TimeoutExpired:
            with job._lock:
                job.phase = JobPhase.ERROR
                job.error = "Превышено время кодирования."
        except subprocess.CalledProcessError:
            with job._lock:
                if job.phase == JobPhase.CANCELLED:
                    return
                job.phase = JobPhase.ERROR
                job.error = "Не удалось перекодировать."
        except Exception as exc:
            with job._lock:
                job.phase = JobPhase.ERROR
                job.error = str(exc)
        finally:
            for p in cleanup_paths:
                if p != out_path:
                    try:
                        p.unlink(missing_ok=True)
                    except OSError:
                        pass

    threading.Thread(target=_run, daemon=True).start()


@app.get("/api/settings")
def api_settings() -> dict[str, Any]:
    max_b = getattr(app.state, "max_upload_bytes", _max_upload_bytes())
    pillow_ok = bool(getattr(app.state, "pillow_available", False))
    return {
        "deployment": getattr(app.state, "deployment_mode", "local"),
        "max_upload_bytes": max_b,
        "max_upload_human": _fmt_bytes(max_b),
        "ffmpeg_available": bool(getattr(app.state, "ffmpeg_path", None)),
        "allowed_suffixes": sorted(ALLOWED_SUFFIXES),
        "presets": list(PRESETS),
        "codecs": [
            {"id": "h264", "label": "H.264", "hint": "Максимальная совместимость"},
            {"id": "h265", "label": "H.265", "hint": "Меньше размер, дольше кодирование"},
        ],
        "scale_modes": [
            {"id": "none", "label": "Исходное разрешение"},
            {"id": "1080", "label": "До 1080p (длинная сторона ≤ 1920)"},
            {"id": "720", "label": "До 720p (≤ 1280)"},
            {"id": "480", "label": "До 480p (≤ 854)"},
        ],
        "image_optimization": {
            "available": pillow_ok,
            "allowed_suffixes": sorted(ALLOWED_IMAGE_SUFFIXES),
            "max_megapixels": _image_max_megapixels(),
            "endpoint": "/optimize-image",
            "output_modes": [
                {"id": "auto", "label": "Авто (как исходник / WebP для прочих)"},
                {"id": "jpeg", "label": "JPEG"},
                {"id": "png", "label": "PNG"},
                {"id": "webp", "label": "WebP"},
            ],
            "png_strategies": [
                {"id": "smart", "label": "Умный PNG (палитра + dither) — как у сервисов вроде TinyPNG"},
                {"id": "lossless", "label": "PNG без потерь (медленнее и крупнее, без артефактов)"},
            ],
            "batch_endpoint": "/optimize-images",
            "max_batch_files": _max_image_batch(),
            "upscale_modes": [
                {
                    "id": "none",
                    "label": "Без увеличения",
                    "hint": "Только оптимизация и при необходимости уменьшение по «макс. сторона».",
                },
                {
                    "id": "2k",
                    "label": "До ~2K (длинная сторона до 2048 px)",
                    "hint": "Локально, Lanczos — сглаженное увеличение, без нейросети и без облака.",
                },
                {
                    "id": "4k",
                    "label": "До ~4K UHD (длинная сторона до 3840 px)",
                    "hint": "То же: интерполяция, не «магическое» восстановление деталей.",
                },
            ],
            "inpaint_remove": {
                "available": bool(getattr(app.state, "opencv_available", False))
                and bool(getattr(app.state, "pillow_available", False)),
                "endpoint": "/inpaint-remove",
                "hint": "Белая маска = зона дорисовки (удаление объекта).",
            },
        },
        "audio_optimization": {
            "available": bool(getattr(app.state, "ffmpeg_path", None)),
            "endpoint": "/optimize-audio",
            "allowed_suffixes": sorted(ALLOWED_AUDIO_INPUT_SUFFIXES),
            "outputs": [
                {"id": "mp3", "label": "MP3 (libmp3lame)", "hint": "Универсально; CBR или VBR"},
                {"id": "aac_m4a", "label": "AAC в M4A", "hint": "Хорошо для Apple / стриминга"},
                {"id": "opus", "label": "Opus", "hint": "Низкий битрейт при хорошем качестве речи"},
                {"id": "flac", "label": "FLAC", "hint": "Архив без потерь"},
            ],
        },
    }


@app.post("/compress")
async def compress(
    request: Request,
    file: UploadFile = File(..., description="Входное видео"),
    codec: Literal["h264", "h265"] = "h264",
    crf: int = 23,
    preset: Literal[
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    ] = "medium",
    audio_bitrate_k: int = 128,
    scale: ScaleMode = "none",
    async_mode: bool = Query(False, description="Асинхронный режим с polling прогресса"),
) -> Response:
    ffmpeg_bin = getattr(request.app.state, "ffmpeg_path", None) or shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ffmpeg_missing",
                "message": "ffmpeg не найден. Установите ffmpeg или запустите через Docker.",
            },
        )

    stem, suffix = _safe_filename_parts(
        file.filename,
        default_suffix=".mp4",
        allowed_suffixes=ALLOWED_SUFFIXES,
        default_stem="video",
    )
    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())

    if crf < 0 or crf > 51:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_crf", "message": "CRF должен быть в диапазоне 0…51."},
        )
    if audio_bitrate_k < 16 or audio_bitrate_k > 512:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_audio_bitrate",
                "message": "audio_bitrate_k должен быть в диапазоне 16…512.",
            },
        )

    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex

    in_path = tmp_root / f"media-compressor-{job_id}-in{suffix}"
    out_path = tmp_root / f"media-compressor-{job_id}-out.mp4"

    def _unlink_best_effort(p: Path) -> None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    vf = _scale_filter(scale)
    vcodec = "libx264" if codec == "h264" else "libx265"
    cmd: list[str] = [
        ffmpeg_bin,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        os.environ.get("FFMPEG_LOGLEVEL", "error"),
        "-i",
        str(in_path),
    ]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-c:v",
        vcodec,
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        f"{audio_bitrate_k}k",
        str(out_path),
    ]

    timeout = _ffmpeg_timeout_sec()

    try:
        await _write_upload_to_path(file, in_path, max_bytes)

        if async_mode:
            _start_ffmpeg_job(
                job_id,
                "video",
                cmd,
                in_path=in_path,
                out_path=out_path,
                download_name=f"{stem}.compressed.mp4",
                media_type="video/mp4",
                timeout=timeout,
                cleanup_paths=[in_path],
            )
            return JSONResponse({"job_id": job_id}, status_code=202)

        try:
            await asyncio.to_thread(_run_ffmpeg_subprocess, cmd, timeout)
        except subprocess.TimeoutExpired:
            _unlink_best_effort(in_path)
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=504,
                detail={
                    "code": "ffmpeg_timeout",
                    "message": "Превышено время кодирования. Попробуйте меньший файл, другой preset или включите FFMPEG_TIMEOUT_SEC.",
                },
            ) from None
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or b"").decode("utf-8", errors="replace")[-4000:]
            _unlink_best_effort(in_path)
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "ffmpeg_failed",
                    "message": "Не удалось перекодировать видео.",
                    "stderr_tail": detail,
                },
            ) from e

        if not out_path.exists() or out_path.stat().st_size == 0:
            _unlink_best_effort(in_path)
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=500,
                detail={"code": "empty_output", "message": "На выходе получился пустой файл."},
            )

        download_name = f"{stem}.compressed.mp4"
        _unlink_best_effort(in_path)

        return FileResponse(
            path=str(out_path),
            media_type="video/mp4",
            filename=download_name,
            background=BackgroundTask(_unlink_best_effort, out_path),
        )
    except HTTPException:
        raise
    except Exception as exc:
        _unlink_best_effort(in_path)
        _unlink_best_effort(out_path)
        raise HTTPException(
            status_code=500,
            detail={"code": "internal_error", "message": f"Внутренняя ошибка: {exc}"},
        ) from exc


@app.post("/inpaint-remove")
async def inpaint_remove(
    request: Request,
    file: UploadFile = File(..., description="Исходное изображение"),
    mask: UploadFile = File(..., description="Маска: белое = удалить и дорисовать"),
    radius: int = Query(7, ge=1, le=32),
    method: Literal["telea", "ns"] = "telea",
) -> FileResponse:
    if not getattr(request.app.state, "opencv_available", False):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "opencv_missing",
                "message": "OpenCV не установлен. Выполните: pip install opencv-python-headless",
            },
        )
    if not getattr(request.app.state, "pillow_available", False):
        raise HTTPException(
            status_code=503,
            detail={"code": "pillow_missing", "message": "Pillow недоступен."},
        )

    stem, suffix = _safe_filename_parts(
        file.filename,
        default_suffix=".jpg",
        allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
        default_stem="image",
    )
    _safe_filename_parts(
        mask.filename,
        default_suffix=".png",
        allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
        default_stem="mask",
    )

    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())
    max_mp = _image_max_megapixels()
    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    in_img = tmp_root / f"img-inpaint-{job_id}-in{suffix}"
    in_mask = tmp_root / f"img-inpaint-{job_id}-mask.png"
    out_path = tmp_root / f"img-inpaint-{job_id}-out.png"

    def _unlink_best_effort(p: Path) -> None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        await _write_upload_to_path(file, in_img, max_bytes)
        await _write_upload_to_path(mask, in_mask, max_bytes)
        raw_img = in_img.read_bytes()
        raw_mask = in_mask.read_bytes()
        _unlink_best_effort(in_img)
        _unlink_best_effort(in_mask)

        try:
            await asyncio.to_thread(image_tools_mod.assert_pixel_budget, raw_img, max_mp)
            out_bytes = await asyncio.to_thread(
                image_tools_mod.inpaint_with_mask,
                raw_img,
                raw_mask,
                radius=radius,
                method=method,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail={"code": "inpaint_failed", "message": str(e)},
            ) from e
        except RuntimeError as e:
            raise HTTPException(
                status_code=503,
                detail={"code": "opencv_error", "message": str(e)},
            ) from e

        out_path.write_bytes(out_bytes)
        if out_path.stat().st_size == 0:
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=500,
                detail={"code": "empty_output", "message": "Пустой результат."},
            )

        download_name = f"{stem}.inpainted.png"
        return FileResponse(
            path=str(out_path),
            media_type="image/png",
            filename=download_name,
            background=BackgroundTask(_unlink_best_effort, out_path),
        )
    except HTTPException:
        raise
    except Exception:
        _unlink_best_effort(in_img)
        _unlink_best_effort(in_mask)
        _unlink_best_effort(out_path)
        raise


@app.post("/optimize-image")
async def optimize_image(
    request: Request,
    file: UploadFile = File(..., description="Изображение"),
    output: ImageOutput = "auto",
    quality: int = 85,
    max_side: int = 0,
    strip_metadata: bool = True,
    png_strategy: PngStrategy = "smart",
    webp_lossless: bool = False,
    upscale: ImageUpscale = "none",
) -> FileResponse:
    if not getattr(request.app.state, "pillow_available", False):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "pillow_missing",
                "message": "Pillow не установлен. Добавьте pillow в зависимости.",
            },
        )

    stem, suffix = _safe_filename_parts(
        file.filename,
        default_suffix=".jpg",
        allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
        default_stem="image",
    )
    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())

    if quality < 40 or quality > 100:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_quality", "message": "Качество должно быть в диапазоне 40…100."},
        )
    if max_side != 0 and (max_side < 64 or max_side > 16384):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_max_side",
                "message": "max_side: 0 (не менять) или 64…16384.",
            },
        )

    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    in_path = tmp_root / f"img-opt-{job_id}-in{suffix}"
    out_path = tmp_root / f"img-opt-{job_id}-out.bin"

    def _unlink_best_effort(p: Path) -> None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        await _write_upload_to_path(file, in_path, max_bytes)
        raw = in_path.read_bytes()
        _unlink_best_effort(in_path)

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
            raise HTTPException(
                status_code=422,
                detail={"code": "image_optimize_failed", "message": str(e)},
            ) from e

        out_path = out_path.with_suffix(out_suffix)
        out_path.write_bytes(out_bytes)

        if out_path.stat().st_size == 0:
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=500,
                detail={"code": "empty_output", "message": "Пустой результат оптимизации."},
            )

        download_name = f"{stem}.optimized{out_suffix}"
        return FileResponse(
            path=str(out_path),
            media_type=media_type,
            filename=download_name,
            background=BackgroundTask(_unlink_best_effort, out_path),
        )
    except HTTPException:
        raise
    except Exception:
        _unlink_best_effort(in_path)
        _unlink_best_effort(out_path)
        raise


@app.post("/optimize-images")
async def optimize_images_batch(
    request: Request,
    files: list[UploadFile] = File(..., description="Одно или несколько изображений"),
    output: ImageOutput = "auto",
    quality: int = 85,
    max_side: int = 0,
    strip_metadata: bool = True,
    png_strategy: PngStrategy = "smart",
    webp_lossless: bool = False,
    upscale: ImageUpscale = "none",
) -> FileResponse:
    if not getattr(request.app.state, "pillow_available", False):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "pillow_missing",
                "message": "Pillow не установлен. Добавьте pillow в зависимости.",
            },
        )

    max_batch = _max_image_batch()
    if len(files) < 1:
        raise HTTPException(
            status_code=400,
            detail={"code": "no_files", "message": "Добавьте хотя бы один файл."},
        )
    if len(files) > max_batch:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "too_many_files",
                "message": f"Не больше {max_batch} файлов за раз (лимит MAX_IMAGE_BATCH).",
            },
        )

    if quality < 40 or quality > 100:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_quality", "message": "Качество должно быть в диапазоне 40…100."},
        )
    if max_side != 0 and (max_side < 64 or max_side > 16384):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_max_side",
                "message": "max_side: 0 (не менять) или 64…16384.",
            },
        )

    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())
    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    zip_path = tmp_root / f"img-batch-{job_id}.zip"

    def _unlink_best_effort(p: Path) -> None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        async def _process_upload(i: int, upload: UploadFile) -> tuple[int, str, str, bytes]:
            label = upload.filename or f"файл {i + 1}"
            stem, suffix = _safe_filename_parts(
                upload.filename,
                default_suffix=".jpg",
                allowed_suffixes=ALLOWED_IMAGE_SUFFIXES,
                default_stem="image",
            )
            in_path = tmp_root / f"img-batch-{job_id}-{i:04d}-in{suffix}"
            try:
                await _write_upload_to_path(upload, in_path, max_bytes)
            except HTTPException as e:
                detail: Any = e.detail
                if isinstance(detail, dict):
                    detail = {**detail, "file_index": i + 1, "filename": label}
                else:
                    detail = {
                        "code": "upload_error",
                        "message": str(detail),
                        "file_index": i + 1,
                        "filename": label,
                    }
                raise HTTPException(status_code=e.status_code, detail=detail) from e

            raw = in_path.read_bytes()
            _unlink_best_effort(in_path)

            try:
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
            except ValueError as e:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "image_optimize_failed",
                        "message": f"Файл {i + 1} ({label}): {e}",
                        "file_index": i + 1,
                        "filename": label,
                    },
                ) from e

            arc = _zip_image_arcname(i + 1, stem, out_suffix)
            return i, arc, stem, out_bytes

        sem = asyncio.Semaphore(4)

        async def _bounded(i: int, upload: UploadFile) -> tuple[int, str, str, bytes]:
            async with sem:
                return await _process_upload(i, upload)

        results = await asyncio.gather(*[_bounded(i, u) for i, u in enumerate(files)])

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for _i, arc, _stem, out_bytes in sorted(results, key=lambda x: x[0]):
                zf.writestr(arc, out_bytes, compress_type=zipfile.ZIP_STORED)

        if not zip_path.exists() or zip_path.stat().st_size == 0:
            _unlink_best_effort(zip_path)
            raise HTTPException(
                status_code=500,
                detail={"code": "empty_output", "message": "Пустой архив."},
            )

        download_name = f"images-optimized-{job_id[:8]}.zip"
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=download_name,
            background=BackgroundTask(_unlink_best_effort, zip_path),
        )
    except HTTPException:
        _unlink_best_effort(zip_path)
        raise
    except Exception:
        _unlink_best_effort(zip_path)
        raise


@app.post("/optimize-audio")
async def optimize_audio_media(
    request: Request,
    file: UploadFile = File(..., description="Аудио или видео с дорожкой звука"),
    output: AudioOutput = "mp3",
    bitrate_mode: AudioBitrateMode = "cbr",
    bitrate_k: int = 192,
    vbr_quality: int = 4,
    mono: bool = False,
    sample_rate: int = Query(0, description="0 = без изменений, иначе 44100 или 48000"),
    normalize: bool = False,
    strip_metadata: bool = True,
    async_mode: bool = Query(False, description="Асинхронный режим с polling прогресса"),
) -> Response:
    if sample_rate not in (0, 44100, 48000):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_sample_rate",
                "message": "sample_rate: 0, 44100 или 48000.",
            },
        )

    ffmpeg_bin = getattr(request.app.state, "ffmpeg_path", None) or shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ffmpeg_missing",
                "message": "ffmpeg не найден. Аудио-режим требует ffmpeg.",
            },
        )

    stem, suffix = _safe_filename_parts(
        file.filename,
        default_suffix=".mp3",
        allowed_suffixes=ALLOWED_AUDIO_INPUT_SUFFIXES,
        default_stem="audio",
    )
    max_bytes = getattr(request.app.state, "max_upload_bytes", _max_upload_bytes())

    if vbr_quality < 0 or vbr_quality > 9:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_vbr", "message": "vbr_quality: 0 (лучше) … 9 (компактнее)."},
        )

    tmp_root = _tmpdir()
    tmp_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    in_path = tmp_root / f"aud-opt-{job_id}-in{suffix}"
    media_type, out_suffix = _audio_media_type_and_suffix(output)
    out_path = tmp_root / f"aud-opt-{job_id}-out{out_suffix}"

    def _unlink_best_effort(p: Path) -> None:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    timeout = _ffmpeg_timeout_sec()
    cmd = _build_optimize_audio_cmd(
        ffmpeg_bin,
        in_path,
        out_path,
        output=output,
        bitrate_mode=bitrate_mode,
        bitrate_k=bitrate_k,
        vbr_quality=vbr_quality,
        mono=mono,
        sample_rate=sample_rate,
        normalize=normalize,
        strip_metadata=strip_metadata,
    )

    try:
        await _write_upload_to_path(file, in_path, max_bytes)

        if async_mode:
            _start_ffmpeg_job(
                job_id,
                "audio",
                cmd,
                in_path=in_path,
                out_path=out_path,
                download_name=f"{stem}.audio{out_suffix}",
                media_type=media_type,
                timeout=timeout,
                cleanup_paths=[in_path],
            )
            return JSONResponse({"job_id": job_id}, status_code=202)

        try:
            await asyncio.to_thread(_run_ffmpeg_subprocess, cmd, timeout)
        except subprocess.TimeoutExpired:
            _unlink_best_effort(in_path)
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=504,
                detail={
                    "code": "ffmpeg_timeout",
                    "message": "Превышено время обработки. Увеличьте FFMPEG_TIMEOUT_SEC или упростите параметры.",
                },
            ) from None
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or b"").decode("utf-8", errors="replace")[-4000:]
            _unlink_best_effort(in_path)
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "audio_transcode_failed",
                    "message": "Не удалось извлечь или перекодировать аудио (нет дорожки, неподдерживаемый кодек?).",
                    "stderr_tail": detail,
                },
            ) from e

        if not out_path.exists() or out_path.stat().st_size == 0:
            _unlink_best_effort(in_path)
            _unlink_best_effort(out_path)
            raise HTTPException(
                status_code=500,
                detail={"code": "empty_output", "message": "Пустой выходной файл."},
            )

        download_name = f"{stem}.audio{out_suffix}"
        _unlink_best_effort(in_path)

        return FileResponse(
            path=str(out_path),
            media_type=media_type,
            filename=download_name,
            background=BackgroundTask(_unlink_best_effort, out_path),
        )
    except HTTPException:
        raise
    except Exception:
        _unlink_best_effort(in_path)
        _unlink_best_effort(out_path)
        raise
