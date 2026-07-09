"""
Subtitle export.

Exporters transform the internal subtitle model into interchangeable output
formats without needing to know how the model was produced (FR-017). Adding a
new format requires implementing the :class:`SubtitleExporter` protocol rather
than modifying existing exporters (FR-018).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment
from media_production_framework.text_wrapping import wrap_text

DEFAULT_MAX_LINE_LENGTH = 42


class SubtitleExporter(Protocol):
    """Interface implemented by subtitle exporters."""

    def export(self, document: SubtitleDocument, path: Path) -> None:
        """Write the subtitle document to the given path."""


def _format_srt_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp (HH:MM:SS,mmm)."""

    clamped = max(seconds, 0.0)
    total_ms = round(clamped * 1000)
    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, millis = divmod(remainder_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class SrtExporter:
    """Export line-level subtitles in SubRip (.srt) format (FR-014, FR-016).

    Text is automatically wrapped without splitting words (FR-045) while
    preserving the original segment timing (FR-046).
    """

    def __init__(self, max_line_length: int = DEFAULT_MAX_LINE_LENGTH) -> None:
        self._max_line_length = max_line_length

    def export(self, document: SubtitleDocument, path: Path) -> None:
        """Write the document's segments to an SRT file."""

        blocks = [self._render_segment(segment) for segment in document.segments]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(blocks), encoding="utf-8")

    def _render_segment(self, segment: SubtitleSegment) -> str:
        lines = wrap_text(segment.text, self._max_line_length)
        rendered_text = "\n".join(lines)
        start = _format_srt_timestamp(segment.start)
        end = _format_srt_timestamp(segment.end)
        return f"{segment.index}\n{start} --> {end}\n{rendered_text}\n"


class JsonExporter:
    """Export the complete subtitle document as JSON.

    The JSON export preserves word-level timing and song metadata, allowing
    later pipeline stages (e.g. karaoke rendering) to reuse the alignment
    result without re-running alignment (FR-071).
    """

    def export(self, document: SubtitleDocument, path: Path) -> None:
        """Write the full document, including word timings, to a JSON file."""

        payload = {
            "language": document.language,
            "audio_duration": document.audio_duration,
            "metadata": dict(document.metadata.fields) if document.metadata else None,
            "segments": [
                {
                    "index": segment.index,
                    "text": segment.text,
                    "start": segment.start,
                    "end": segment.end,
                    "words": [
                        {"text": word.text, "start": word.start, "end": word.end}
                        for word in segment.words
                    ],
                }
                for segment in document.segments
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
