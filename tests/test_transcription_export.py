"""Tests for transcript export formats."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from transcription.export import export_lrc, export_srt, export_txt, export_vtt, write_zip
from transcription.schema import Segment, TranscriptResult


def _sample_speech() -> TranscriptResult:
    return TranscriptResult(
        mode="speech",
        language="ru",
        tier="full",
        duration_sec=10.0,
        segments=[
            Segment(text="Первое предложение.", start=0.0, end=2.5, type="sentence"),
            Segment(text="Второе предложение!", start=4.0, end=6.0, type="sentence"),
        ],
    )


def _sample_song() -> TranscriptResult:
    return TranscriptResult(
        mode="song",
        language="en",
        tier="degraded",
        duration_sec=20.0,
        segments=[
            Segment(text="Walking down the street", start=1.0, end=4.0, type="line", section="verse"),
            Segment(text="Stars are shining bright", start=4.5, end=7.0, type="line", section="verse"),
            Segment(text="This is our song", start=8.0, end=11.0, type="line", section="chorus"),
        ],
        genius_used=False,
    )


def test_export_txt_paragraph_gap() -> None:
    txt = export_txt(_sample_speech(), paragraph_gap_sec=1.5)
    assert "Первое предложение." in txt
    assert "\n\n" in txt


def test_export_srt_format() -> None:
    srt = export_srt(_sample_speech())
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "1\n" in srt or srt.startswith("1\n")


def test_export_vtt_header() -> None:
    vtt = export_vtt(_sample_speech())
    assert vtt.startswith("WEBVTT")
    assert "Первое предложение." in vtt


def test_export_lrc_song() -> None:
    lrc = export_lrc(_sample_song())
    assert "[Куплет]" in lrc
    assert "[01:00.00]" not in lrc
    assert "[00:01.00]" in lrc
    assert "Walking down the street" in lrc


def test_write_zip(tmp_path: Path) -> None:
    zp = tmp_path / "out.zip"
    write_zip(_sample_song(), zp)
    assert zp.exists()
    with zipfile.ZipFile(zp) as zf:
        names = set(zf.namelist())
        assert "transcript.json" in names
        assert "lyrics.lrc" in names
        data = json.loads(zf.read("transcript.json"))
        assert data["mode"] == "song"
        assert len(data["segments"]) == 3
