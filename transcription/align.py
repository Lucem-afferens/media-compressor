"""Segmentation: regroup words into sentences or song lines."""

from __future__ import annotations

import re

from transcription.schema import Segment, SegmentType, Word

_SENT_END = re.compile(r"[.!?…]+[\"')\]]*$")
_PUNCT_BREAK = re.compile(r"^[,;:\-—–]+|[,;:\-—–]+$")


def _clean_word(text: str) -> str:
    return _PUNCT_BREAK.sub("", text).strip()


def words_to_segments(
    words: list[Word],
    *,
    mode: str,
    max_chars: int = 200,
    max_words_line: int = 10,
    gap_sentence: float = 0.5,
    gap_line: float = 0.4,
    gap_paragraph: float = 1.5,
) -> list[Segment]:
    if not words:
        return []

    seg_type: SegmentType = "line" if mode == "song" else "sentence"
    gap_break = gap_line if mode == "song" else gap_sentence
    chunks: list[list[Word]] = []
    buf: list[Word] = []

    def flush() -> None:
        nonlocal buf
        if buf:
            chunks.append(buf)
            buf = []

    for i, w in enumerate(words):
        if buf and w.start - buf[-1].end >= gap_break:
            flush()
        buf.append(w)
        text_so_far = " ".join(_clean_word(x.text) for x in buf).strip()
        word_count = len([x for x in buf if _clean_word(x.text)])

        if mode == "speech":
            if _SENT_END.search(w.text) or len(text_so_far) >= max_chars:
                flush()
        else:
            if word_count >= max_words_line or len(text_so_far) >= max_chars:
                flush()
            elif _SENT_END.search(w.text):
                flush()

    flush()

    segments: list[Segment] = []
    for chunk in chunks:
        text = " ".join(_clean_word(w.text) for w in chunk).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        segments.append(
            Segment(
                text=text,
                start=chunk[0].start,
                end=chunk[-1].end,
                type=seg_type,
                words=list(chunk),
            )
        )

    return segments


def detect_song_sections(segments: list[Segment]) -> list[Segment]:
    """Label repeating line blocks as chorus via simple text fingerprinting."""
    if len(segments) < 4:
        return segments

    norm = [re.sub(r"\W+", " ", s.text.lower()).strip() for s in segments]
    counts: dict[str, int] = {}
    for n in norm:
        if len(n) > 8:
            counts[n] = counts.get(n, 0) + 1

    chorus_keys = {k for k, v in counts.items() if v >= 2}
    verse_idx = 0
    for seg, n in zip(segments, norm):
        if n in chorus_keys:
            seg.section = "chorus"
        else:
            verse_idx += 1
            seg.section = "verse" if verse_idx % 2 == 1 else "verse"
    return segments


def detect_speech_vs_song(words: list[Word], duration_sec: float) -> str:
    """Heuristic: high word density + short gaps → speech; else song."""
    if not words or duration_sec <= 0:
        return "speech"
    gaps = [words[i + 1].start - words[i].end for i in range(len(words) - 1)]
    if not gaps:
        return "speech"
    avg_gap = sum(gaps) / len(gaps)
    wpm = len(words) / (duration_sec / 60.0)
    if wpm > 100 and avg_gap < 0.35:
        return "speech"
    if avg_gap > 0.45 or wpm < 80:
        return "song"
    return "speech"
