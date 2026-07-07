"""Export transcript to TXT, SRT, VTT, LRC, JSON."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from transcription.schema import Segment, TranscriptResult

_SECTION_LABELS = {
    "verse": "[Куплет]",
    "chorus": "[Припев]",
    "bridge": "[Бридж]",
    "intro": "[Интро]",
    "outro": "[Аутро]",
}


def _fmt_srt_time(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    if ms >= 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _fmt_lrc_time(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    m = int(sec // 60)
    s = sec % 60
    return f"[{m:02d}:{s:05.2f}]"


def export_txt(result: TranscriptResult, *, paragraph_gap_sec: float = 1.5) -> str:
    lines: list[str] = []
    prev_end: float | None = None
    last_section = None
    for seg in result.segments:
        if seg.section and seg.section != last_section:
            label = _SECTION_LABELS.get(seg.section, f"[{seg.section}]")
            if lines:
                lines.append("")
            lines.append(label)
            last_section = seg.section
        if prev_end is not None and seg.start - prev_end >= paragraph_gap_sec and result.mode == "speech":
            lines.append("")
        lines.append(seg.text.strip())
        prev_end = seg.end
    return "\n".join(lines).strip() + "\n"


def export_srt(result: TranscriptResult) -> str:
    blocks: list[str] = []
    for i, seg in enumerate(result.segments, start=1):
        text = seg.text.strip()
        if not text:
            continue
        blocks.append(
            f"{i}\n{_fmt_srt_time(seg.start)} --> {_fmt_srt_time(seg.end)}\n{text}\n"
        )
    return "\n".join(blocks)


def export_vtt(result: TranscriptResult) -> str:
    lines = ["WEBVTT", ""]
    for seg in result.segments:
        text = seg.text.strip()
        if not text:
            continue
        lines.append(f"{_fmt_vtt_time(seg.start)} --> {_fmt_vtt_time(seg.end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def export_lrc(result: TranscriptResult) -> str:
    lines: list[str] = []
    last_section = None
    for seg in result.segments:
        if seg.section and seg.section != last_section:
            label = _SECTION_LABELS.get(seg.section, f"[{seg.section}]")
            lines.append(label)
            last_section = seg.section
        text = seg.text.strip()
        if text:
            lines.append(f"{_fmt_lrc_time(seg.start)}{text}")
    return "\n".join(lines).strip() + "\n"


def export_json(result: TranscriptResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n"


def write_zip(result: TranscriptResult, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("transcript.json", export_json(result))
        zf.writestr("transcript.txt", export_txt(result))
        zf.writestr("subtitles.srt", export_srt(result))
        zf.writestr("subtitles.vtt", export_vtt(result))
        if result.mode == "song":
            zf.writestr("lyrics.lrc", export_lrc(result))


def merge_short_segments(segments: list[Segment], min_gap: float = 0.25) -> list[Segment]:
    if not segments:
        return []
    out: list[Segment] = [segments[0]]
    for seg in segments[1:]:
        prev = out[-1]
        if seg.start - prev.end < min_gap and prev.type == seg.type:
            prev.text = f"{prev.text} {seg.text}".strip()
            prev.end = seg.end
            prev.words.extend(seg.words)
        else:
            out.append(seg)
    return out
