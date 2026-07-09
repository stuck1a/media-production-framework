"""
Song metadata parsing.

Supports the FFMETADATA1 text format used by FFmpeg
(https://ffmpeg.org/ffmpeg-formats.html#Metadata-1). Parsing this format
without an external dependency keeps metadata preservation (FR-056) fully
offline and dependency-free.
"""

from __future__ import annotations

from pathlib import Path

from media_production_framework.domain import SongMetadata

_HEADER = ";FFMETADATA1"


class MetadataError(ValueError):
    """Raised when a metadata file cannot be parsed."""


class MetadataParser:
    """Parse FFMETADATA1 metadata files into :class:`SongMetadata` objects."""

    def parse(self, text: str) -> SongMetadata:
        """Parse FFMETADATA1 text into a :class:`SongMetadata` object."""

        lines = text.splitlines()
        if not lines or lines[0].strip() != _HEADER:
            raise MetadataError(f"Metadata file must start with '{_HEADER}'.")

        fields: dict[str, str] = {}
        for line in lines[1:]:
            stripped = line.strip()
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                raise MetadataError(f"Invalid metadata line (expected key=value): {stripped}")
            key, _, value = stripped.partition("=")
            fields[key.strip().lower()] = value.strip()

        return SongMetadata(fields=fields)

    def parse_file(self, path: Path) -> SongMetadata:
        """Parse a FFMETADATA1 file from disk."""

        return self.parse(path.read_text(encoding="utf-8"))
