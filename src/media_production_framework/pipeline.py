"""
Processing pipeline infrastructure.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from media_production_framework.alignment import AlignmentRequest, AlignmentService
from media_production_framework.audio import AudioError, get_audio_duration
from media_production_framework.configuration import (
    ConfigurationLoader,
    ProjectConfiguration,
    SubtitleConfiguration,
)
from media_production_framework.domain import Project
from media_production_framework.events import (
    AlignmentCompletedEvent,
    AlignmentStartedEvent,
    ConfigurationLoadedEvent,
    EventBus,
    PipelineCompletedEvent,
    PipelineStageCompletedEvent,
    PipelineStartedEvent,
    ProjectLoadedEvent,
    SubtitleExportCompletedEvent,
)
from media_production_framework.lyrics import LyricsParser
from media_production_framework.metadata import MetadataParser
from media_production_framework.projects import ProjectLoader
from media_production_framework.providers import ProviderRegistry
from media_production_framework.subtitle_export import JsonExporter, SrtExporter
from media_production_framework.subtitle_validation import SubtitleValidator
from media_production_framework.subtitles import SubtitleDocument


@dataclass
class PipelineContext:
    """Shared runtime state passed between pipeline stages."""

    project_root: Path
    configuration_path: Path | None = None
    strict_validation: bool = True
    configuration: ProjectConfiguration | None = None
    project: Project | None = None
    subtitle_document: SubtitleDocument | None = None
    event_bus: EventBus = field(default_factory=EventBus)
    provider_registry: ProviderRegistry = field(default_factory=ProviderRegistry)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    artifacts: dict[str, Any] = field(default_factory=dict)


class PipelineStage(Protocol):
    """Protocol implemented by processing pipeline stages."""

    name: str

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute the stage and return the updated context."""


class ProcessingPipeline:
    """Execute a sequence of pipeline stages."""

    def __init__(self, stages: Sequence[PipelineStage]) -> None:
        if not stages:
            raise ValueError("A pipeline requires at least one stage.")
        self._stages = tuple(stages)

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Execute all stages in order."""

        context.event_bus.publish(PipelineStartedEvent())
        for stage in self._stages:
            context.logger.debug("Executing pipeline stage: %s", stage.name)
            context = stage.execute(context)
            context.event_bus.publish(PipelineStageCompletedEvent(stage_name=stage.name))
        context.event_bus.publish(PipelineCompletedEvent())
        return context


class ConfigurationStage:
    """Load project configuration or create an empty one."""

    name = "configuration"

    def __init__(self, loader: ConfigurationLoader | None = None) -> None:
        self._loader = loader or ConfigurationLoader()

    def execute(self, context: PipelineContext) -> PipelineContext:
        if context.configuration_path is None:
            context.configuration = self._loader.empty(context.project_root)
            context.strict_validation = False
            context.event_bus.publish(ConfigurationLoadedEvent(path=""))
            return context

        context.configuration = self._loader.load(context.configuration_path)
        context.event_bus.publish(ConfigurationLoadedEvent(path=str(context.configuration_path)))
        return context


class ProjectLoadingStage:
    """Load project assets from configuration."""

    name = "project-loading"

    def __init__(self, loader: ProjectLoader | None = None) -> None:
        self._loader = loader or ProjectLoader()

    def execute(self, context: PipelineContext) -> PipelineContext:
        if context.configuration is None:
            raise RuntimeError("Configuration must be loaded before project loading.")

        context.project = self._loader.load(
            context.configuration,
            strict=context.strict_validation,
        )
        context.event_bus.publish(ProjectLoadedEvent(project_root=str(context.project.root)))
        return context


class ProviderInitializationStage:
    """Initialize provider infrastructure for the current run."""

    name = "provider-initialization"

    def execute(self, context: PipelineContext) -> PipelineContext:
        context.artifacts["provider_count"] = len(context.provider_registry.all())
        return context


def _subtitle_configuration(context: PipelineContext) -> SubtitleConfiguration:
    """Return the effective subtitle configuration for the current context."""

    if context.configuration is None:
        return SubtitleConfiguration()
    return context.configuration.subtitles


class SubtitleAlignmentStage:
    """Align lyrics with audio and produce the internal subtitle model.

    The stage is skipped whenever subtitle generation is disabled or the
    required audio/lyrics assets are missing, so it remains a no-op for
    projects that do not use this capability yet (CAP-002).
    """

    name = "subtitle-alignment"

    def __init__(
        self,
        service: AlignmentService | None = None,
        validator: SubtitleValidator | None = None,
        metadata_parser: MetadataParser | None = None,
    ) -> None:
        self._service = service or AlignmentService()
        self._validator = validator or SubtitleValidator()
        self._metadata_parser = metadata_parser or MetadataParser()

    def execute(self, context: PipelineContext) -> PipelineContext:
        if context.project is None:
            raise RuntimeError("Project must be loaded before subtitle alignment.")

        subtitle_config = _subtitle_configuration(context)
        assets = context.project.assets

        if not subtitle_config.enabled:
            context.logger.debug("Subtitle generation disabled; skipping alignment.")
            return context

        if assets.audio is None or assets.lyrics is None:
            context.logger.debug(
                "Subtitle alignment requires both audio and lyrics assets; skipping."
            )
            return context

        context.event_bus.publish(AlignmentStartedEvent(provider=subtitle_config.provider))

        parsed_lyrics = LyricsParser().parse_document(assets.lyrics)
        duration = self._resolve_audio_duration(assets.audio.path, subtitle_config)
        song_metadata = (
            self._metadata_parser.parse_file(assets.metadata.path)
            if assets.metadata is not None
            else None
        )

        request = AlignmentRequest(
            audio_path=assets.audio.path,
            parsed_lyrics=parsed_lyrics,
            raw_lyrics=assets.lyrics.text,
            language=subtitle_config.language,
            audio_duration=duration,
        )
        document = self._service.align(
            request,
            provider_name=subtitle_config.provider,
            model=subtitle_config.model,
            metadata=song_metadata,
        )
        self._validator.validate(document)

        context.subtitle_document = document
        context.event_bus.publish(
            AlignmentCompletedEvent(
                provider=subtitle_config.provider,
                segment_count=len(document.segments),
            )
        )
        return context

    @staticmethod
    def _resolve_audio_duration(
        audio_path: Path,
        subtitle_config: SubtitleConfiguration,
    ) -> float | None:
        if subtitle_config.audio_duration_seconds is not None:
            return subtitle_config.audio_duration_seconds
        try:
            return get_audio_duration(audio_path)
        except AudioError:
            return None


class SubtitleExportStage:
    """Export the generated subtitle document to SRT and JSON files."""

    name = "subtitle-export"

    def __init__(
        self,
        srt_exporter: SrtExporter | None = None,
        json_exporter: JsonExporter | None = None,
    ) -> None:
        self._srt_exporter = srt_exporter
        self._json_exporter = json_exporter or JsonExporter()

    def execute(self, context: PipelineContext) -> PipelineContext:
        document = context.subtitle_document
        if document is None or document.is_empty:
            context.logger.debug("No subtitle document available; skipping export.")
            return context

        subtitle_config = _subtitle_configuration(context)
        if subtitle_config.file is None:
            context.logger.debug("No subtitle output path configured; skipping export.")
            return context

        srt_exporter = self._srt_exporter or SrtExporter(subtitle_config.max_line_length)
        srt_path = subtitle_config.file
        json_path = srt_path.with_suffix(".json")

        srt_exporter.export(document, srt_path)
        self._json_exporter.export(document, json_path)

        context.artifacts["subtitle_srt_path"] = str(srt_path)
        context.artifacts["subtitle_json_path"] = str(json_path)
        context.event_bus.publish(
            SubtitleExportCompletedEvent(srt_path=str(srt_path), json_path=str(json_path))
        )
        return context


class RenderingPlaceholderStage:
    """Placeholder for the future video rendering stage (Milestone M3)."""

    name = "rendering-placeholder"

    def execute(self, context: PipelineContext) -> PipelineContext:
        context.artifacts["rendering_placeholder_completed"] = True
        return context


def build_core_pipeline() -> ProcessingPipeline:
    """Build the core processing pipeline."""

    stages: list[PipelineStage] = [
        ConfigurationStage(),
        ProjectLoadingStage(),
        ProviderInitializationStage(),
        SubtitleAlignmentStage(),
        SubtitleExportStage(),
        RenderingPlaceholderStage(),
    ]
    return ProcessingPipeline(stages)
