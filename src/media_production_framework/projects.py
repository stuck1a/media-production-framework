"""
Project loading and validation.
"""

from __future__ import annotations

from pathlib import Path

from media_production_framework.configuration import ProjectConfiguration
from media_production_framework.domain import (
    AudioAsset,
    LyricsDocument,
    MediaMetadata,
    Project,
    ProjectAssets,
)


class ProjectValidationError(ValueError):
    """Raised when a project fails validation."""


class ProjectValidator:
    """Validate project configuration and assets."""

    def validate_configuration(
        self,
        configuration: ProjectConfiguration,
        strict: bool = True,
    ) -> None:
        """Validate project configuration before loading assets."""

        errors: list[str] = []
        if not configuration.project_root.exists():
            errors.append(f"Project root does not exist: {configuration.project_root}")

        if strict:
            self._require_existing_file(configuration.input.audio, "input.audio", errors)
            # PF9: lyrics are only needed for forced alignment. When an existing
            # SRT source is supplied, alignment is skipped, so lyrics become
            # optional.
            lyrics_optional = configuration.subtitles.source is not None
            self._require_existing_file(
                configuration.input.lyrics,
                "input.lyrics",
                errors,
                optional=lyrics_optional,
            )
            self._require_existing_file(
                configuration.input.metadata,
                "input.metadata",
                errors,
                optional=True,
            )

        if errors:
            raise ProjectValidationError("; ".join(errors))

    @staticmethod
    def _require_existing_file(
        path: Path | None,
        field_name: str,
        errors: list[str],
        optional: bool = False,
    ) -> None:
        if path is None:
            if not optional:
                errors.append(f"Missing required configuration value: {field_name}")
            return

        if not path.is_file():
            errors.append(f"Configured file does not exist for {field_name}: {path}")


class ProjectLoader:
    """Load projects from normalized configuration."""

    def __init__(self, validator: ProjectValidator | None = None) -> None:
        self._validator = validator or ProjectValidator()

    def load(self, configuration: ProjectConfiguration, strict: bool = True) -> Project:
        """Load a project from configuration."""

        self._validator.validate_configuration(configuration, strict=strict)
        assets = ProjectAssets(
            audio=self._load_audio(configuration),
            lyrics=self._load_lyrics(configuration),
            metadata=self._load_metadata(configuration),
        )
        return Project(
            root=configuration.project_root,
            configuration=configuration,
            assets=assets,
        )

    @staticmethod
    def _load_audio(configuration: ProjectConfiguration) -> AudioAsset | None:
        if configuration.input.audio is None:
            return None
        return AudioAsset(path=configuration.input.audio)

    @staticmethod
    def _load_lyrics(configuration: ProjectConfiguration) -> LyricsDocument | None:
        if configuration.input.lyrics is None:
            return None
        return LyricsDocument(
            path=configuration.input.lyrics,
            text=configuration.input.lyrics.read_text(encoding="utf-8"),
        )

    @staticmethod
    def _load_metadata(configuration: ProjectConfiguration) -> MediaMetadata | None:
        if configuration.input.metadata is None:
            return None
        return MediaMetadata(path=configuration.input.metadata)
