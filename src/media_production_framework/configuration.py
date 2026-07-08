"""
Configuration loading for the Media Production Framework.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be loaded or validated."""


@dataclass(frozen=True)
class InputConfiguration:
    """Input files used by a media production project."""

    audio: Path | None = None
    lyrics: Path | None = None
    metadata: Path | None = None


@dataclass(frozen=True)
class OutputConfiguration:
    """Output files produced by a media production project."""

    video: Path | None = None


@dataclass(frozen=True)
class ProjectConfiguration:
    """Normalized project configuration loaded from YAML."""

    project_root: Path
    input: InputConfiguration = field(default_factory=InputConfiguration)
    output: OutputConfiguration = field(default_factory=OutputConfiguration)
    raw: Mapping[str, Any] = field(default_factory=dict)


class ConfigurationLoader:
    """Load and normalize YAML project configuration files."""

    def load(self, path: Path) -> ProjectConfiguration:
        """Load a configuration file from disk."""

        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_file():
            raise ConfigurationError(f"Configuration file does not exist: {resolved_path}")

        try:
            loaded_data = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML configuration: {resolved_path}") from exc

        if loaded_data is None:
            loaded_data = {}

        if not isinstance(loaded_data, Mapping):
            raise ConfigurationError("Configuration root must be a mapping.")

        project_root = resolved_path.parent
        input_data = self._mapping_section(loaded_data, "input")
        output_data = self._mapping_section(loaded_data, "output")

        return ProjectConfiguration(
            project_root=project_root,
            input=InputConfiguration(
                audio=self._optional_path(input_data, "audio", project_root),
                lyrics=self._optional_path(input_data, "lyrics", project_root),
                metadata=self._optional_path(input_data, "metadata", project_root),
            ),
            output=OutputConfiguration(
                video=self._optional_path(output_data, "video", project_root),
            ),
            raw=loaded_data,
        )

    @staticmethod
    def empty(project_root: Path) -> ProjectConfiguration:
        """Create an empty configuration rooted at the given directory."""

        return ProjectConfiguration(project_root=project_root.expanduser().resolve())

    @staticmethod
    def _mapping_section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        section = data.get(key, {})
        if section is None:
            return {}
        if not isinstance(section, Mapping):
            raise ConfigurationError(f"Configuration section '{key}' must be a mapping.")
        return section

    @staticmethod
    def _optional_path(data: Mapping[str, Any], key: str, project_root: Path) -> Path | None:
        value = data.get(key)
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ConfigurationError(f"Configuration value '{key}' must be a path string.")

        path = Path(value).expanduser()
        if not path.is_absolute():
            path = project_root / path
        return path.resolve()
