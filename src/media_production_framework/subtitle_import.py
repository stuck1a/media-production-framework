"""
Subtitle import.

Importers turn an existing subtitle file back into the internal subtitle model,
allowing a project to bypass forced alignment entirely and reuse timings that
were produced elsewhere (PF9). The imported document is the counterpart of the
:class:`~media_production_framework.subtitle_export.SrtExporter` output and can
be validated, exported and rendered like any aligned document.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

from media_production_framework.domain import SongMetadata
from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment

_LOGGER = logging.getLogger(__name__)

# HH:MM:SS,mmm (or with a '.' separator, as some tools emit).
_TIMESTAMP_PATTERN = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")
_ARROW = "-->"

# Nominal on-screen duration applied when repairing a zero/negative-length cue
# (e.g. an SRT exported from a failed alignment whose final segment collapsed to
# start == end). Only used when the following cue does not already bound it.
_MIN_IMPORTED_CUE_DURATION = 0.5


class SrtImportError(ValueError):
    """Raised when an SRT file cannot be parsed into a subtitle document."""


def _parse_timestamp(value: str) -> float:
    """Parse an SRT timestamp (``HH:MM:SS,mmm``) into seconds."""

    match = _TIMESTAMP_PATTERN.fullmatch(value.strip())
    if match is None:
        raise SrtImportError(f"Invalid SRT timestamp: {value!r}")
    hours, minutes, seconds, millis = match.groups()
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis.ljust(3, "0")) / 1000.0
    )


@dataclass
class SrtImporter:
    """Parse a SubRip (``.srt``) file into a :class:`SubtitleDocument`.

    Segments are renumbered sequentially so that a re-exported document is
    always cleanly ordered. Wrapped display lines within a cue are rejoined into
    a single segment text, reversing the line wrapping applied on export.
    """

    def import_file(
        self,
        path: Path,
        *,
        language: str | None = None,
        audio_duration: float | None = None,
        metadata: SongMetadata | None = None,
    ) -> SubtitleDocument:
        """Read and parse an SRT file from disk."""

        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise SrtImportError(f"Could not read subtitle source: {path}") from exc
        return self.parse(
            text,
            language=language,
            audio_duration=audio_duration,
            metadata=metadata,
        )

    def parse(
        self,
        text: str,
        *,
        language: str | None = None,
        audio_duration: float | None = None,
        metadata: SongMetadata | None = None,
    ) -> SubtitleDocument:
        """Parse SRT text into a subtitle document."""

        parsed = [
            self._parse_block(block, index)
            for index, block in enumerate(_iter_blocks(text), start=1)
        ]
        if not parsed:
            raise SrtImportError("Subtitle source contains no cues.")
        return SubtitleDocument(
            segments=self._repair_zero_length_cues(parsed),
            language=language,
            audio_duration=audio_duration,
            metadata=metadata,
        )

    @staticmethod
    def _repair_zero_length_cues(
        segments: list[SubtitleSegment],
    ) -> tuple[SubtitleSegment, ...]:
        """Extend any zero/negative-length cue so it stays visible.

        The end is pushed to the next cue's start when that leaves a positive
        duration, otherwise to a fixed minimum. This tolerates SRT files whose
        final cue collapsed to ``start == end`` (a symptom of a failed alignment
        fallback) without discarding the text.
        """

        repaired: list[SubtitleSegment] = []
        for position, segment in enumerate(segments):
            if segment.end > segment.start:
                repaired.append(segment)
                continue

            next_start = segments[position + 1].start if position + 1 < len(segments) else None
            if next_start is not None and next_start > segment.start:
                new_end = next_start
            else:
                new_end = segment.start + _MIN_IMPORTED_CUE_DURATION
            _LOGGER.warning(
                "Subtitle cue %d had a non-positive duration (%.3f -> %.3f); "
                "extending its end to %.3f.",
                segment.index,
                segment.start,
                segment.end,
                new_end,
            )
            repaired.append(replace(segment, end=new_end))
        return tuple(repaired)

    @staticmethod
    def _parse_block(lines: list[str], index: int) -> SubtitleSegment:
        arrow_position = next(
            (position for position, line in enumerate(lines) if _ARROW in line),
            None,
        )
        if arrow_position is None:
            raise SrtImportError(f"Subtitle cue {index} is missing a timing line.")

        start_text, _, end_text = lines[arrow_position].partition(_ARROW)
        start = _parse_timestamp(start_text)
        end = _parse_timestamp(end_text)

        text = " ".join(line.strip() for line in lines[arrow_position + 1 :]).strip()
        if not text:
            raise SrtImportError(f"Subtitle cue {index} has no text.")

        return SubtitleSegment(index=index, text=text, start=start, end=end)


def _iter_blocks(text: str) -> list[list[str]]:
    """Split SRT text into cue blocks, each a list of non-empty lines."""

    blocks: list[list[str]] = []
    current: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.strip():
            current.append(raw_line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks
