"""Genius lyrics lookup and optional alignment."""

from __future__ import annotations

import re
from typing import Callable

from transcription.schema import Segment, Word

_GENIUS_SEARCH = "https://api.genius.com/search"
_GENIUS_TIMEOUT = 15.0


def _http_client():
    try:
        import httpx
    except ImportError as e:
        raise RuntimeError("httpx не установлен (pip install httpx)") from e
    return httpx


def _strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def fetch_genius_lyrics(
    token: str,
    *,
    artist: str | None = None,
    title: str | None = None,
    query: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return (lyrics_text, artist, title) or (None, None, None)."""
    q = query or " ".join(x for x in [artist, title] if x).strip()
    if not q:
        return None, None, None

    headers = {"Authorization": f"Bearer {token}"}
    try:
        httpx = _http_client()
        with httpx.Client(timeout=_GENIUS_TIMEOUT) as client:
            r = client.get(_GENIUS_SEARCH, params={"q": q}, headers=headers)
            r.raise_for_status()
            hits = r.json().get("response", {}).get("hits", [])
            if not hits:
                return None, None, None
            hit = hits[0]["result"]
            found_artist = hit.get("primary_artist", {}).get("name")
            found_title = hit.get("title")
            url = hit.get("url")
            if not url:
                return None, found_artist, found_title
            page = client.get(url, follow_redirects=True)
            page.raise_for_status()
            html = page.text
    except (httpx.HTTPError, KeyError, ValueError):
        return None, None, None

    # Genius embeds lyrics in JSON-LD or data-lyrics-container; fallback scrape
    m = re.search(r'<div[^>]+data-lyrics-container="true"[^>]*>(.*?)</div>', html, re.S | re.I)
    if m:
        lyrics = _strip_html(m.group(1))
        if lyrics:
            return lyrics, found_artist, found_title

    m = re.search(r'"lyricsData"\s*:\s*\{"html"\s*:\s*"(.*?)"\s*,', html, re.S)
    if m:
        import json

        try:
            raw = json.loads(f'"{m.group(1)}"')
            lyrics = _strip_html(raw)
            if lyrics:
                return lyrics, found_artist, found_title
        except json.JSONDecodeError:
            pass

    return None, found_artist, found_title


def _norm_token(s: str) -> str:
    return re.sub(r"[^\w]+", "", s.lower(), flags=re.UNICODE)


def align_lyrics_to_words(
    lyrics_text: str,
    asr_words: list[Word],
    *,
    on_progress: Callable[[float, str], None] | None = None,
) -> list[Segment]:
    """Map reference lyric lines to ASR word timings."""
    lines = [ln.strip() for ln in lyrics_text.splitlines() if ln.strip()]
    lyric_lines = [ln for ln in lines if not re.match(r"^\[.+\]$", ln)]
    if not lyric_lines or not asr_words:
        return []

    if on_progress:
        on_progress(90.0, "Выравнивание текста песни…")

    segments: list[Segment] = []
    wi = 0
    for line in lyric_lines:
        line_tokens = [_norm_token(t) for t in line.split() if _norm_token(t)]
        if not line_tokens:
            continue
        matched: list[Word] = []
        while wi < len(asr_words) and len(matched) < len(line_tokens):
            aw = _norm_token(asr_words[wi].text)
            if aw and (aw == line_tokens[len(matched)] or aw.startswith(line_tokens[len(matched)][:3])):
                matched.append(asr_words[wi])
                wi += 1
            elif not matched:
                wi += 1
            else:
                break
        if matched:
            segments.append(
                Segment(
                    text=line,
                    start=matched[0].start,
                    end=matched[-1].end,
                    type="line",
                    words=matched,
                )
            )
    return segments
