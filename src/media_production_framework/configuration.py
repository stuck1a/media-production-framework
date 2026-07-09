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


DEFAULT_SUBTITLE_PROVIDER = "heuristic"
DEFAULT_SUBTITLE_MAX_LINE_LENGTH = 42


@dataclass(frozen=True)
class SubtitleConfiguration:
    """Subtitle generation settings (FR-014 - FR-018, capability CAP-002/CAP-003).

    ``provider`` and ``model`` identify the alignment backend; interpreting
    them belongs to the Alignment Engine rather than this configuration
    object, which only carries the validated values.
    """

    enabled: bool = False
    provider: str = DEFAULT_SUBTITLE_PROVIDER
    model: str | None = None
    language: str | None = None
    file: Path | None = None
    max_line_length: int = DEFAULT_SUBTITLE_MAX_LINE_LENGTH
    audio_duration_seconds: float | None = None


@dataclass(frozen=True)
class ProjectConfiguration:
    """Normalized project configuration loaded from YAML."""

    project_root: Path
    input: InputConfiguration = field(default_factory=InputConfiguration)
    output: OutputConfiguration = field(default_factory=OutputConfiguration)
    subtitles: SubtitleConfiguration = field(default_factory=SubtitleConfiguration)
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
        subtitles_data = self._mapping_section(loaded_data, "subtitles")

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
            subtitles=self._subtitle_configuration(subtitles_data, project_root),
            raw=loaded_data,
        )

    @classmethod
    def _subtitle_configuration(
        cls,
        data: Mapping[str, Any],
        project_root: Path,
    ) -> SubtitleConfiguration:
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ConfigurationError("Configuration value 'subtitles.enabled' must be a boolean.")

        provider = data.get("provider", DEFAULT_SUBTITLE_PROVIDER)
        if not isinstance(provider, str) or not provider:
            raise ConfigurationError("Configuration value 'subtitles.provider' must be a string.")

        model = cls._optional_string(data, "model")
        language = cls._optional_string(data, "language")
        max_line_length = data.get("max_line_length", DEFAULT_SUBTITLE_MAX_LINE_LENGTH)
        if not isinstance(max_line_length, int) or isinstance(max_line_length, bool):
            raise ConfigurationError(
                "Configuration value 'subtitles.max_line_length' must be an integer."
            )

        duration = data.get("audio_duration_seconds")
        if duration is not None and not isinstance(duration, (int, float)):
            raise ConfigurationError(
                "Configuration value 'subtitles.audio_duration_seconds' must be a number."
            )

        return SubtitleConfiguration(
            enabled=enabled,
            provider=provider,
            model=model,
            language=language,
            file=cls._optional_path(data, "file", project_root),
            max_line_length=max_line_length,
            audio_duration_seconds=float(duration) if duration is not None else None,
        )

    @staticmethod
    def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ConfigurationError(f"Configuration value '{key}' must be a string.")
        return value

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
