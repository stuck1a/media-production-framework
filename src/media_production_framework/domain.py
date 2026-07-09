"""
Core domain objects for the Media Production Framework.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from media_production_framework.configuration import ProjectConfiguration


@dataclass(frozen=True)
class SongMetadata:
    """Song metadata associated with a project.

    Metadata is treated as a first-class project asset (FR-056) so it can be
    preserved throughout the production pipeline. Values are kept in a generic
    field mapping to stay independent of any particular metadata container
    format, with convenience accessors for the most common fields.
    """

    fields: Mapping[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str | None:
        """Return the song title if present."""

        value = self.fields.get("title")
        return str(value) if value is not None else None

    @property
    def artist(self) -> str | None:
        """Return the song artist if present."""

        value = self.fields.get("artist")
        return str(value) if value is not None else None


@dataclass(frozen=True)
class AudioAsset:
    """Audio source asset used by a project."""

    path: Path


@dataclass(frozen=True)
class LyricsDocument:
    """Lyrics source document used for alignment."""

    path: Path
    text: str

    @property
    def lines(self) -> Sequence[str]:
        """Return non-empty lyric lines."""

        return tuple(line.strip() for line in self.text.splitlines() if line.strip())


@dataclass(frozen=True)
class MediaMetadata:
    """Optional metadata file associated with a project."""

    path: Path


@dataclass(frozen=True)
class ProjectAssets:
    """Collection of assets discovered for a project."""

    audio: AudioAsset | None = None
    lyrics: LyricsDocument | None = None
    metadata: MediaMetadata | None = None


@dataclass(frozen=True)
class Project:
    """A complete media production project."""

    root: Path
    configuration: ProjectConfiguration
    assets: ProjectAssets = field(default_factory=ProjectAssets)
    project_id: str = field(default_factory=lambda: str(uuid4()))
