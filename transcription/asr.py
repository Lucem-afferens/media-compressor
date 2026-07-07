"""faster-whisper ASR wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from transcription.config import TranscribeConfig
from transcription.schema import Word

_model_cache: dict[tuple[str, str, str], object] = {}


def _get_model(cfg: TranscribeConfig):
    key = (cfg.model_name, cfg.compute_type, cfg.device)
    if key not in _model_cache:
        from faster_whisper import WhisperModel

        _model_cache[key] = WhisperModel(
            cfg.model_name,
            device=cfg.device,
            compute_type=cfg.compute_type,
        )
    return _model_cache[key]


def transcribe_words(
    wav_path: Path,
    cfg: TranscribeConfig,
    *,
    language: str | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[list[Word], str, float]:
    model = _get_model(cfg)
    lang = None if not language or language == "auto" else language

    if on_progress:
        on_progress(5.0, "Распознавание речи…")

    segments, info = model.transcribe(
        str(wav_path),
        language=lang,
        beam_size=cfg.beam_size,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=True,
    )

    words: list[Word] = []
    seg_list = list(segments)
    total = max(len(seg_list), 1)

    for i, seg in enumerate(seg_list):
        if cancel_check and cancel_check():
            raise InterruptedError("cancelled")
        if seg.words:
            for w in seg.words:
                token = (w.word or "").strip()
                if not token:
                    continue
                words.append(
                    Word(
                        text=token,
                        start=float(w.start or seg.start),
                        end=float(w.end or seg.end),
                        confidence=float(w.probability) if w.probability is not None else None,
                    )
                )
        elif seg.text.strip():
            words.append(
                Word(
                    text=seg.text.strip(),
                    start=float(seg.start),
                    end=float(seg.end),
                )
            )
        if on_progress:
            on_progress(10.0 + (i + 1) / total * 70.0, f"Распознавание: {i + 1}/{total}")

    detected = info.language or lang or "unknown"
    duration = float(info.duration or 0.0)
    if on_progress:
        on_progress(85.0, "Сегментация текста…")
    return words, detected, duration
