"""
Core domain objects for the Media Production Framework.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from media_production_framework.configuration import ProjectConfiguration


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
