"""Transcript data model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SegmentType = Literal["sentence", "line", "paragraph"]
SectionType = Literal["verse", "chorus", "bridge", "intro", "outro", "unknown"]


@dataclass
class Word:
    text: str
    start: float
    end: float
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text, "start": self.start, "end": self.end}
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d


@dataclass
class Segment:
    text: str
    start: float
    end: float
    type: SegmentType = "sentence"
    section: SectionType | None = None
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "type": self.type,
        }
        if self.section:
            d["section"] = self.section
        if self.words:
            d["words"] = [w.to_dict() for w in self.words]
        return d


@dataclass
class TranscriptResult:
    mode: Literal["speech", "song"]
    language: str
    tier: Literal["full", "degraded"]
    duration_sec: float
    segments: list[Segment]
    source_title: str | None = None
    source_artist: str | None = None
    genius_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "language": self.language,
            "tier": self.tier,
            "duration_sec": self.duration_sec,
            "segments": [s.to_dict() for s in self.segments],
            "source_title": self.source_title,
            "source_artist": self.source_artist,
            "genius_used": self.genius_used,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranscriptResult:
        segments = []
        for s in data.get("segments", []):
            words = [Word(**w) for w in s.get("words", [])]
            segments.append(
                Segment(
                    text=s["text"],
                    start=float(s["start"]),
                    end=float(s["end"]),
                    type=s.get("type", "sentence"),
                    section=s.get("section"),
                    words=words,
                )
            )
        return cls(
            mode=data.get("mode", "speech"),
            language=data.get("language", "unknown"),
            tier=data.get("tier", "degraded"),
            duration_sec=float(data.get("duration_sec", 0)),
            segments=segments,
            source_title=data.get("source_title"),
            source_artist=data.get("source_artist"),
            genius_used=bool(data.get("genius_used", False)),
        )

    def full_text(self) -> str:
        return "\n".join(s.text for s in self.segments)
