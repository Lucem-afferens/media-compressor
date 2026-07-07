"""Transcription tier and environment configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

TranscribeTier = Literal["full", "degraded"]
TranscribeMode = Literal["speech", "song", "auto"]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _deployment_mode() -> str:
    explicit = os.environ.get("DEPLOYMENT_MODE", "").strip().lower()
    if explicit in ("local", "cloud"):
        return explicit
    if (
        os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("RAILWAY_SERVICE_NAME")
        or os.environ.get("RENDER")
        or os.environ.get("RENDER_SERVICE_NAME")
    ):
        return "cloud"
    return "local"


def resolve_tier() -> TranscribeTier:
    raw = os.environ.get("TRANSCRIBE_TIER", "auto").strip().lower()
    if raw == "full":
        return "full"
    if raw == "degraded":
        return "degraded"
    return "degraded" if _deployment_mode() == "cloud" else "full"


@dataclass(frozen=True)
class TranscribeConfig:
    tier: TranscribeTier
    model_name: str
    compute_type: str
    max_duration_sec: int
    max_concurrent: int
    demucs_enabled: bool
    genius_token: str | None
    device: str
    beam_size: int

    @property
    def genius_configured(self) -> bool:
        return bool(self.genius_token)


def load_config() -> TranscribeConfig:
    tier = resolve_tier()
    if tier == "degraded":
        model = os.environ.get("WHISPER_MODEL", "base")
        compute = os.environ.get("WHISPER_COMPUTE", "int8")
        max_dur = _env_int("MAX_TRANSCRIBE_SEC", 180)
        demucs = False
        concurrent = 1
    else:
        model = os.environ.get("WHISPER_MODEL", "large-v3")
        compute = os.environ.get("WHISPER_COMPUTE", "int8")
        max_dur = _env_int("MAX_TRANSCRIBE_SEC", 3600)
        demucs = os.environ.get("TRANSCRIBE_DEMUCS", "1").strip().lower() not in ("0", "false", "no")
        concurrent = max(1, _env_int("MAX_TRANSCRIBE_CONCURRENT", 1))

    device = os.environ.get("WHISPER_DEVICE", "cpu")
    return TranscribeConfig(
        tier=tier,
        model_name=model,
        compute_type=compute,
        max_duration_sec=max_dur,
        max_concurrent=concurrent,
        demucs_enabled=demucs,
        genius_token=os.environ.get("GENIUS_API_TOKEN") or None,
        device=device,
        beam_size=max(1, _env_int("WHISPER_BEAM_SIZE", 5 if tier == "full" else 1)),
    )


def transcription_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False
