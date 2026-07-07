"""Speech transcription pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from transcription.align import detect_speech_vs_song, words_to_segments
from transcription.asr import transcribe_words
from transcription.config import TranscribeConfig
from transcription.schema import TranscriptResult


def transcribe_speech(
    wav_path: Path,
    cfg: TranscribeConfig,
    *,
    language: str = "auto",
    on_progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> TranscriptResult:
    words, detected_lang, duration = transcribe_words(
        wav_path,
        cfg,
        language=language,
        on_progress=on_progress,
        cancel_check=cancel_check,
    )
    segments = words_to_segments(words, mode="speech", max_chars=220, gap_sentence=0.5)
    return TranscriptResult(
        mode="speech",
        language=detected_lang,
        tier=cfg.tier,
        duration_sec=duration,
        segments=segments,
    )
