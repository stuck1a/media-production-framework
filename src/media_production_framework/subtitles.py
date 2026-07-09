"""
Subtitle domain objects.

These objects form the internal subtitle model produced by the Alignment Engine
and consumed by exporters and, in future milestones, the Rendering Engine. They
are strongly typed and immutable so they remain easy to validate and serialize.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from media_production_framework.domain import SongMetadata


@dataclass(frozen=True)
class SubtitleWord:
    """Word-level timing information within a subtitle segment."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class SubtitleSegment:
    """A single subtitle segment corresponding to one lyric line."""

    index: int
    text: str
    start: float
    end: float
    words: Sequence[SubtitleWord] = field(default_factory=tuple)


@dataclass(frozen=True)
class SubtitleDocument:
    """The complete subtitle model for a project."""

    segments: Sequence[SubtitleSegment] = field(default_factory=tuple)
    language: str | None = None
    audio_duration: float | None = None
    metadata: SongMetadata | None = None

    @property
    def is_empty(self) -> bool:
        """Return whether the document contains no segments."""

        return len(self.segments) == 0
