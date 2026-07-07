"""In-memory job registry for async ffmpeg tasks with progress reporting."""

from __future__ import annotations

import subprocess
import threading
import time
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class JobPhase(str, Enum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class JobState:
    id: str
    kind: str
    phase: JobPhase = JobPhase.QUEUED
    percent: float = 0.0
    message: str = ""
    elapsed_sec: float = 0.0
    result_path: Path | None = None
    download_name: str | None = None
    media_type: str | None = None
    error: str | None = None
    stderr_tail: str | None = None
    result_meta: dict[str, Any] | None = None
    started_at: float = field(default_factory=time.monotonic)
    _process: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started_at
        with self._lock:
            eta_sec: float | None = None
            if (
                self.phase == JobPhase.PROCESSING
                and 0 < self.percent < 100
            ):
                eta_sec = round(elapsed * (100.0 - self.percent) / self.percent, 1)
            return {
                "id": self.id,
                "kind": self.kind,
                "phase": self.phase.value,
                "percent": round(self.percent, 1),
                "message": self.message,
                "elapsed_sec": round(elapsed, 1),
                "eta_sec": eta_sec,
                "done": self.phase in (JobPhase.DONE, JobPhase.ERROR, JobPhase.CANCELLED),
                "error": self.error,
                "result_meta": self.result_meta,
            }


class JobStore:
    def __init__(self, ttl_sec: float = 600.0) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._ttl_sec = ttl_sec

    def create(self, job_id: str, kind: str) -> JobState:
        job = JobState(id=job_id, kind=kind)
        with self._lock:
            self._purge_expired()
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        with job._lock:
            if job.phase in (JobPhase.DONE, JobPhase.ERROR, JobPhase.CANCELLED):
                return False
            proc = job._process
            if proc and proc.poll() is None:
                proc.kill()
            job.phase = JobPhase.CANCELLED
            job.message = "Отменено пользователем"
            job.percent = 0.0
        return True

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [
            jid
            for jid, j in self._jobs.items()
            if j.phase in (JobPhase.DONE, JobPhase.ERROR, JobPhase.CANCELLED)
            and now - j.started_at > self._ttl_sec
        ]
        for jid in expired:
            job = self._jobs.pop(jid, None)
            if job and job.result_path:
                try:
                    job.result_path.unlink(missing_ok=True)
                except OSError:
                    pass


def _probe_duration_us(ffmpeg: str, in_path: Path, timeout: int | None) -> int | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        ffprobe_bin = Path(ffmpeg).with_name("ffprobe")
        ffprobe = str(ffprobe_bin) if ffprobe_bin.exists() else None
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(in_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout or 60)
        text = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
        sec = float(text)
        if sec > 0:
            return int(sec * 1_000_000)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None
    return None


def _parse_ffmpeg_progress_line(line: str, duration_us: int | None) -> float | None:
    line = line.strip()
    if line.startswith("out_time_ms="):
        try:
            out_us = int(line.split("=", 1)[1])
        except ValueError:
            return None
        if duration_us and duration_us > 0:
            return min(99.0, max(0.0, (out_us / duration_us) * 100))
    if line.startswith("progress=") and line.endswith("end"):
        return 100.0
    return None


def run_ffmpeg_with_progress(
    job: JobState,
    cmd: list[str],
    *,
    in_path: Path | None = None,
    timeout: int | None = None,
) -> None:
    """Run ffmpeg, updating job progress. Raises on failure."""
    duration_us: int | None = None
    if in_path and in_path.exists():
        ffmpeg_bin = cmd[0]
        duration_us = _probe_duration_us(ffmpeg_bin, in_path, timeout)

    progress_cmd = list(cmd)
    if "-progress" not in progress_cmd:
        progress_cmd += ["-progress", "pipe:1", "-nostats"]

    with job._lock:
        job.phase = JobPhase.PROCESSING
        job.message = "Кодирование…"
        job.percent = max(job.percent, 5.0)

    proc = subprocess.Popen(
        progress_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    with job._lock:
        job._process = proc

    assert proc.stdout is not None
    deadline = time.monotonic() + timeout if timeout else None

    try:
        for raw_line in proc.stdout:
            if deadline and time.monotonic() > deadline:
                proc.kill()
                raise subprocess.TimeoutExpired(progress_cmd, timeout)
            with job._lock:
                if job.phase == JobPhase.CANCELLED:
                    proc.kill()
                    raise subprocess.CalledProcessError(-1, progress_cmd)
            line = raw_line.decode("utf-8", errors="replace")
            pct = _parse_ffmpeg_progress_line(line, duration_us)
            if pct is not None:
                with job._lock:
                    job.percent = max(job.percent, pct)
                    if duration_us:
                        job.message = f"Кодирование: {pct:.0f}%"
                    else:
                        job.message = "Кодирование…"

        stderr = proc.communicate(timeout=30)[1] if proc.poll() is None else proc.stderr.read()
        rc = proc.wait()
        if rc != 0:
            tail = (stderr or b"").decode("utf-8", errors="replace")[-4000:]
            with job._lock:
                job.stderr_tail = tail
            raise subprocess.CalledProcessError(rc, progress_cmd, stderr=stderr)

        with job._lock:
            job.percent = 100.0
            job.message = "Готово"
    finally:
        with job._lock:
            job._process = None


def run_transcription_job(
    job: JobState,
    worker: Any,
) -> None:
    """Run a transcription worker that updates job.percent/message."""
    with job._lock:
        job.phase = JobPhase.PROCESSING
        job.message = "Подготовка…"
        job.percent = max(job.percent, 2.0)

    def _on_progress(pct: float, msg: str) -> None:
        with job._lock:
            if job.phase == JobPhase.CANCELLED:
                raise InterruptedError("cancelled")
            job.percent = max(job.percent, min(99.0, pct))
            job.message = msg

    def _cancel_check() -> bool:
        with job._lock:
            return job.phase == JobPhase.CANCELLED

    try:
        worker(on_progress=_on_progress, cancel_check=_cancel_check)
        with job._lock:
            if job.phase == JobPhase.CANCELLED:
                return
            job.percent = 100.0
            job.message = "Готово"
    except InterruptedError:
        with job._lock:
            if job.phase != JobPhase.CANCELLED:
                job.phase = JobPhase.CANCELLED
                job.message = "Отменено пользователем"
        raise
    except Exception:
        raise


job_store = JobStore()
