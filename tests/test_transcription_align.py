"""Tests for word segmentation / align heuristics."""

from __future__ import annotations

from transcription.align import detect_song_sections, detect_speech_vs_song, words_to_segments
from transcription.schema import Word


def _words(tokens: list[tuple[str, float, float]]) -> list[Word]:
    return [Word(text=t, start=a, end=b) for t, a, b in tokens]


def test_speech_splits_on_punctuation() -> None:
    words = _words(
        [
            ("Hello", 0.0, 0.3),
            ("world.", 0.35, 0.7),
            ("Again", 1.5, 1.8),
            ("here!", 1.85, 2.1),
        ]
    )
    segs = words_to_segments(words, mode="speech")
    assert len(segs) == 2
    assert segs[0].text == "Hello world."
    assert segs[1].text == "Again here!"


def test_song_splits_by_gap() -> None:
    words = _words(
        [
            ("Line", 0.0, 0.2),
            ("one", 0.25, 0.5),
            ("Line", 1.0, 1.2),
            ("two", 1.25, 1.5),
        ]
    )
    segs = words_to_segments(words, mode="song", gap_line=0.35, max_words_line=8)
    assert len(segs) == 2
    assert segs[0].type == "line"


def test_detect_speech_vs_song() -> None:
    dense = _words([(f"w{i}", i * 0.2, i * 0.2 + 0.15) for i in range(40)])
    assert detect_speech_vs_song(dense, 10.0) == "speech"
    sparse = _words([(f"w{i}", i * 1.0, i * 1.0 + 0.3) for i in range(10)])
    assert detect_speech_vs_song(sparse, 20.0) == "song"


def test_chorus_detection() -> None:
    from transcription.schema import Segment

    segs = [
        Segment(text="Same chorus line here", start=0, end=2, type="line"),
        Segment(text="Verse unique text long", start=2.5, end=5, type="line"),
        Segment(text="Same chorus line here", start=6, end=8, type="line"),
        Segment(text="Another verse line now", start=8.5, end=11, type="line"),
    ]
    out = detect_song_sections(segs)
    assert out[0].section == "chorus"
    assert out[2].section == "chorus"
