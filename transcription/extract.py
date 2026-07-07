"""ffmpeg audio extraction for ASR."""

from __future__ import annotations

import subprocess
from pathlib import Path


def extract_mono_wav(
    ffmpeg: str,
    in_path: Path,
    out_path: Path,
    *,
    sample_rate: int = 16000,
    max_duration_sec: int | None = None,
    timeout: int | None = None,
) -> float:
    """Extract mono 16 kHz WAV. Returns duration in seconds."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(in_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
    ]
    if max_duration_sec and max_duration_sec > 0:
        cmd.extend(["-t", str(max_duration_sec)])
    cmd.append(str(out_path))
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    return probe_duration(ffmpeg, out_path, timeout)


def probe_duration(ffmpeg: str, path: Path, timeout: int | None = None) -> float:
    ffprobe = Path(ffmpeg).with_name("ffprobe")
    probe = "ffprobe" if not ffprobe.exists() else str(ffprobe)
    import shutil

    if probe == "ffprobe" and not shutil.which("ffprobe"):
        return 0.0
    if probe != "ffprobe":
        pass
    else:
        probe = shutil.which("ffprobe") or probe

    cmd = [
        probe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout or 60)
        return max(0.0, float(proc.stdout.decode().strip()))
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return 0.0
