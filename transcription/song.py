"""Song transcription: vocal separation, line breaks, optional Genius."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

from transcription.align import detect_song_sections, words_to_segments
from transcription.asr import transcribe_words
from transcription.config import TranscribeConfig
from transcription.lyrics import align_lyrics_to_words, fetch_genius_lyrics
from transcription.schema import Segment, TranscriptResult, Word


def separate_vocals(
    in_wav: Path,
    out_vocals: Path,
    *,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    if on_progress:
        on_progress(8.0, "Отделение вокала (Demucs)…")
    try:
        import demucs.separate  # noqa: F401
    except ImportError as e:
        raise RuntimeError("Demucs не установлен. Установите requirements-transcribe.txt") from e

    out_dir = out_vocals.parent / "demucs_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python",
        "-m",
        "demucs",
        "--two-stems",
        "vocals",
        "-o",
        str(out_dir),
        str(in_wav),
    ]
    if cancel_check and cancel_check():
        raise InterruptedError("cancelled")

    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"Demucs failed: {err}")

    candidates = list(out_dir.rglob("vocals.wav"))
    if not candidates:
        raise RuntimeError("Demucs не создал vocals.wav")
    out_vocals.parent.mkdir(parents=True, exist_ok=True)
    out_vocals.write_bytes(candidates[0].read_bytes())
    if on_progress:
        on_progress(15.0, "Вокал выделен")
    return out_vocals


def _rms_line_gaps(wav_path: Path, *, frame_ms: int = 25, hop_ms: int = 10, threshold: float = 0.02) -> list[tuple[float, float]]:
    """Return silent intervals (start, end) from vocal RMS envelope."""
    try:
        import wave

        with wave.open(str(wav_path), "rb") as wf:
            rate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            sampwidth = wf.getsampwidth()
        if sampwidth != 2:
            return []
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        frame = max(1, int(rate * frame_ms / 1000))
        hop = max(1, int(rate * hop_ms / 1000))
        if len(audio) < frame:
            return []
        rms = []
        times = []
        for i in range(0, len(audio) - frame, hop):
            chunk = audio[i : i + frame]
            rms.append(float(np.sqrt(np.mean(chunk**2))))
            times.append(i / rate)
        if not rms:
            return []
        mx = max(rms) or 1.0
        norm = [v / mx for v in rms]
        gaps: list[tuple[float, float]] = []
        in_gap = False
        gap_start = 0.0
        for t, v in zip(times, norm):
            if v < threshold and not in_gap:
                in_gap = True
                gap_start = t
            elif v >= threshold and in_gap:
                in_gap = False
                if t - gap_start >= 0.2:
                    gaps.append((gap_start, t))
        return gaps
    except (OSError, ValueError, ImportError):
        return []


def _refine_lines_with_rms(segments: list[Segment], wav_path: Path) -> list[Segment]:
    """Split long lines at RMS silence gaps (full tier)."""
    gaps = _rms_line_gaps(wav_path)
    if not gaps:
        return segments
    out: list[Segment] = []
    for seg in segments:
        if not seg.words or len(seg.words) <= 6:
            out.append(seg)
            continue
        split_at: list[int] = []
        for gi, (gs, ge) in enumerate(gaps):
            for wi, w in enumerate(seg.words[:-1]):
                if gs <= w.end <= ge or (w.end <= gs and seg.words[wi + 1].start >= ge):
                    split_at.append(wi + 1)
        if not split_at:
            out.append(seg)
            continue
        idx = 0
        for sp in sorted(set(split_at)):
            chunk = seg.words[idx:sp]
            if chunk:
                text = " ".join(w.text for w in chunk).strip()
                out.append(Segment(text=text, start=chunk[0].start, end=chunk[-1].end, type="line", words=chunk))
            idx = sp
        tail = seg.words[idx:]
        if tail:
            text = " ".join(w.text for w in tail).strip()
            out.append(Segment(text=text, start=tail[0].start, end=tail[-1].end, type="line", words=tail))
    return out if out else segments


def transcribe_song(
    wav_path: Path,
    cfg: TranscribeConfig,
    *,
    language: str = "auto",
    artist: str | None = None,
    title: str | None = None,
    vocals_path: Path | None = None,
    on_progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> TranscriptResult:
    asr_input = vocals_path or wav_path
    words, detected_lang, duration = transcribe_words(
        asr_input,
        cfg,
        language=language,
        on_progress=on_progress,
        cancel_check=cancel_check,
    )

    genius_used = False
    segments: list[Segment] = []
    if cfg.genius_token and (artist or title):
        lyrics, ga, gt = fetch_genius_lyrics(cfg.genius_token, artist=artist, title=title)
        if lyrics:
            segments = align_lyrics_to_words(lyrics, words, on_progress=on_progress)
            if segments:
                genius_used = True
                artist = ga or artist
                title = gt or title

    if not segments:
        segments = words_to_segments(
            words,
            mode="song",
            max_words_line=8 if cfg.tier == "degraded" else 12,
            gap_line=0.35 if cfg.tier == "degraded" else 0.45,
        )
        if cfg.tier == "full" and vocals_path and vocals_path.exists():
            segments = _refine_lines_with_rms(segments, vocals_path)
        segments = detect_song_sections(segments)

    return TranscriptResult(
        mode="song",
        language=detected_lang,
        tier=cfg.tier,
        duration_sec=duration,
        segments=segments,
        source_artist=artist,
        source_title=title,
        genius_used=genius_used,
    )
