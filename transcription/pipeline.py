"""Main transcription orchestrator."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Literal

from transcription.align import detect_speech_vs_song, words_to_segments
from transcription.asr import transcribe_words
from transcription.config import TranscribeConfig, load_config
from transcription.export import write_zip
from transcription.extract import extract_mono_wav
from transcription.schema import TranscriptResult
from transcription.song import separate_vocals, transcribe_song
from transcription.speech import transcribe_speech

TranscribeMode = Literal["speech", "song", "auto"]


def run_transcription(
    ffmpeg: str,
    in_path: Path,
    *,
    mode: TranscribeMode = "auto",
    language: str = "auto",
    artist: str | None = None,
    title: str | None = None,
    cfg: TranscribeConfig | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[TranscriptResult, Path]:
    """Run full pipeline; returns result and path to ZIP archive."""
    cfg = cfg or load_config()
    tmp = Path(tempfile.gettempdir()) / f"mc-transcribe-{uuid.uuid4().hex}"
    tmp.mkdir(parents=True, exist_ok=True)

    wav_path = tmp / "audio.wav"
    vocals_path = tmp / "vocals.wav"
    zip_path = tmp / "transcript.zip"

    try:
        if on_progress:
            on_progress(2.0, "Подготовка аудио…")
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")

        duration = extract_mono_wav(
            ffmpeg,
            in_path,
            wav_path,
            max_duration_sec=cfg.max_duration_sec,
            timeout=cfg.max_duration_sec + 120 if cfg.max_duration_sec else None,
        )

        vocals_ready: Path | None = None
        if mode in ("song", "auto") and cfg.demucs_enabled:
            try:
                separate_vocals(
                    wav_path,
                    vocals_path,
                    on_progress=on_progress,
                    cancel_check=cancel_check,
                )
                vocals_ready = vocals_path
            except (RuntimeError, InterruptedError):
                if mode == "song":
                    raise

        asr_input = vocals_ready or wav_path

        if mode == "speech":
            result = transcribe_speech(
                asr_input,
                cfg,
                language=language,
                on_progress=on_progress,
                cancel_check=cancel_check,
            )
        elif mode == "song":
            result = transcribe_song(
                wav_path,
                cfg,
                language=language,
                artist=artist,
                title=title,
                vocals_path=vocals_ready,
                on_progress=on_progress,
                cancel_check=cancel_check,
            )
        else:
            words, detected_lang, dur = transcribe_words(
                asr_input,
                cfg,
                language=language,
                on_progress=on_progress,
                cancel_check=cancel_check,
            )
            resolved = detect_speech_vs_song(words, dur or duration)
            if resolved == "speech":
                segments = words_to_segments(words, mode="speech")
                result = TranscriptResult(
                    mode="speech",
                    language=detected_lang,
                    tier=cfg.tier,
                    duration_sec=dur or duration,
                    segments=segments,
                )
            else:
                result = transcribe_song(
                    wav_path,
                    cfg,
                    language=language,
                    artist=artist,
                    title=title,
                    vocals_path=vocals_ready,
                    on_progress=on_progress,
                    cancel_check=cancel_check,
                )

        if on_progress:
            on_progress(95.0, "Экспорт файлов…")
        write_zip(result, zip_path)
        if on_progress:
            on_progress(100.0, "Готово")
        return result, zip_path
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
