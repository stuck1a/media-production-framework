"""
Processing pipeline infrastructure.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from media_production_framework.alignment import AlignmentRequest, AlignmentService
from media_production_framework.audio import AudioError, get_audio_duration
from media_production_framework.configuration import (
    ConfigurationLoader,
    ProjectConfiguration,
    SubtitleConfiguration,
)
from media_production_framework.domain import Project, ProjectAssets, SongMetadata
from media_production_framework.events import (
    AlignmentCompletedEvent,
    AlignmentStartedEvent,
    ConfigurationLoadedEvent,
    EventBus,
    PipelineCompletedEvent,
    PipelineStageCompletedEvent,
    PipelineStartedEvent,
    PreviewRenderingCompletedEvent,
    ProjectLoadedEvent,
    RenderingCompletedEvent,
    RenderingProgressEvent,
    RenderingStartedEvent,
    SubtitleExportCompletedEvent,
)
from media_production_framework.lyrics import LyricsParser
from media_production_framework.metadata import MetadataParser
from media_production_framework.projects import ProjectLoader
from media_production_framework.providers import ProviderRegistry
from media_production_framework.render_backends import (
    RenderService,
    render_backend_descriptors,
)
from media_production_framework.rendering import RenderJob, RenderProgress, RenderSettings
from media_production_framework.subtitle_export import JsonExporter, SrtExporter
from media_production_framework.subtitle_import import SrtImporter
from media_production_framework.subtitle_validation import SubtitleValidator
from media_production_framework.subtitles import SubtitleDocument

PREVIEW_MAX_WIDTH = 640
PREVIEW_PRESET = "ultrafast"
PREVIEW_CRF = 30

# Provider label published on alignment events when subtitles are imported from
# an existing SRT file instead of being aligned (PF9).
SUBTITLE_IMPORT_LABEL = "srt-import"


@dataclass
class PipelineContext:
    """Shared runtime state passed between pipeline stages."""

    project_root: Path
    configuration_path: Path | None = None
    strict_validation: bool = True
    render_enabled: bool = True
    preview: bool = False
    render_backend: str = BACKEND_AUTO
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
    """Initialize provider infrastructure for the current run.

    Registers the built-in render backends as provider descriptors so they are
    discoverable through the :class:`ProviderRegistry` (FR-094).
    """

    name = "provider-initialization"

    def execute(self, context: PipelineContext) -> PipelineContext:
        context.provider_registry.extend(render_backend_descriptors())
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
        importer: SrtImporter | None = None,
    ) -> None:
        self._service = service or AlignmentService()
        self._validator = validator or SubtitleValidator()
        self._metadata_parser = metadata_parser or MetadataParser()
        self._importer = importer or SrtImporter()

    def execute(self, context: PipelineContext) -> PipelineContext:
        if context.project is None:
            raise RuntimeError("Project must be loaded before subtitle alignment.")

        subtitle_config = _subtitle_configuration(context)
        assets = context.project.assets

        if not subtitle_config.enabled:
            context.logger.debug("Subtitle generation disabled; skipping alignment.")
            return context

        # PF9: an existing SRT file bypasses alignment entirely.
        if subtitle_config.source is not None:
            return self._import_subtitles(context, subtitle_config, assets)

        if assets.audio is None or assets.lyrics is None:
            context.logger.debug(
                "Subtitle alignment requires both audio and lyrics assets; skipping."
            )
            return context

        context.event_bus.publish(AlignmentStartedEvent(provider=subtitle_config.provider))

        parsed_lyrics = LyricsParser().parse_document(assets.lyrics)
        duration = self._resolve_audio_duration(assets.audio.path, subtitle_config)
        song_metadata = self._resolve_song_metadata(assets)

        request = AlignmentRequest(
            audio_path=assets.audio.path,
            parsed_lyrics=parsed_lyrics,
            raw_lyrics=assets.lyrics.text,
            language=subtitle_config.language,
            audio_duration=duration,
            options=subtitle_config.provider_options,
        )
        document = self._service.align(
            request,
            provider_name=subtitle_config.provider,
            model=subtitle_config.model,
            metadata=song_metadata,
            max_failures=subtitle_config.max_alignment_failures_allowed,
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

    def _import_subtitles(
        self,
        context: PipelineContext,
        subtitle_config: SubtitleConfiguration,
        assets: ProjectAssets,
    ) -> PipelineContext:
        """Import subtitles from an existing SRT file instead of aligning (PF9)."""

        source = subtitle_config.source
        assert source is not None  # guaranteed by the caller
        context.event_bus.publish(AlignmentStartedEvent(provider=SUBTITLE_IMPORT_LABEL))

        document = self._importer.import_file(
            source,
            language=subtitle_config.language,
            metadata=self._resolve_song_metadata(assets),
        )
        self._validator.validate(document)

        context.subtitle_document = document
        context.logger.info(
            "Imported %d subtitle segment(s) from %s; alignment skipped.",
            len(document.segments),
            source,
        )
        context.event_bus.publish(
            AlignmentCompletedEvent(
                provider=SUBTITLE_IMPORT_LABEL,
                segment_count=len(document.segments),
            )
        )
        return context

    def _resolve_song_metadata(self, assets: ProjectAssets) -> SongMetadata | None:
        if assets.metadata is None:
            return None
        return self._metadata_parser.parse_file(assets.metadata.path)

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


class RenderingStage:
    """Render the final lyric video from configuration and subtitles (FR-023).

    Like :class:`SubtitleAlignmentStage`, the stage skips gracefully whenever
    rendering is disabled, no ``rendering`` section is configured, or no
    ``output.video`` path is set, so it is a no-op for projects that do not use
    video rendering.
    """

    name = "rendering"

    def __init__(
        self,
        service: RenderService | None = None,
        metadata_parser: MetadataParser | None = None,
    ) -> None:
        self._service = service or RenderService()
        self._metadata_parser = metadata_parser or MetadataParser()

    def execute(self, context: PipelineContext) -> PipelineContext:
        config = context.configuration

        if not context.render_enabled:
            context.logger.debug("Rendering disabled; skipping rendering stage.")
            return context
        if config is None or config.rendering is None:
            context.logger.debug("No rendering configuration; skipping rendering stage.")
            return context
        if config.output.video is None:
            context.logger.debug("No output.video configured; skipping rendering stage.")
            return context

        job = self._build_job(context, config)
        backend_name = context.render_backend
        context.event_bus.publish(
            RenderingStartedEvent(backend=backend_name, preview=job.preview)
        )

        def on_progress(progress: RenderProgress) -> None:
            context.event_bus.publish(
                RenderingProgressEvent(
                    fraction=progress.fraction,
                    completed_seconds=progress.completed_seconds,
                    total_seconds=progress.total_seconds,
                )
            )

        plan = self._service.plan(job, backend_name)
        result = self._service.render(job, backend_name, on_progress=on_progress)

        context.artifacts["render_result"] = result
        context.artifacts["render_plan"] = plan
        context.artifacts["render_backend"] = result.backend
        context.artifacts["render_output_path"] = str(result.output_path)

        if job.preview:
            context.event_bus.publish(
                PreviewRenderingCompletedEvent(
                    backend=result.backend, output_path=str(result.output_path)
                )
            )
        else:
            context.event_bus.publish(
                RenderingCompletedEvent(
                    backend=result.backend,
                    output_path=str(result.output_path),
                    success=result.success,
                )
            )
        return context

    def _build_job(self, context: PipelineContext, config: ProjectConfiguration) -> RenderJob:
        assets = context.project.assets if context.project is not None else ProjectAssets()
        render_config = config.rendering
        assert render_config is not None  # guaranteed by the caller's skip checks

        subtitle_document = context.subtitle_document or SubtitleDocument()
        audio_path = assets.audio.path if assets.audio is not None else None
        assert config.output.video is not None  # guaranteed by the caller's skip checks

        job = RenderJob(
            output_path=config.output.video,
            settings=RenderSettings.from_config(render_config, config.ffmpeg),
            background=render_config.background,
            text=render_config.text,
            subtitle_document=subtitle_document,
            audio_path=audio_path,
            cover_path=config.input.cover,
            metadata=self._resolve_metadata(subtitle_document, assets),
            duration=self._resolve_duration(config, subtitle_document, audio_path),
            preview=context.preview,
        )
        if context.preview:
            job = self._apply_preview(job)
        return job

    def _resolve_metadata(
        self,
        subtitle_document: SubtitleDocument,
        assets: ProjectAssets,
    ) -> SongMetadata | None:
        song_metadata = subtitle_document.metadata
        if song_metadata is None and assets.metadata is not None:
            song_metadata = self._metadata_parser.parse_file(assets.metadata.path)

        fields: dict[str, Any] = dict(song_metadata.fields) if song_metadata is not None else {}
        # Embed the full, multi-line lyrics text into the metadata where the
        # container supports it (FR-059), unless a lyrics field already exists.
        if "lyrics" not in fields and assets.lyrics is not None:
            fields["lyrics"] = assets.lyrics.text

        return SongMetadata(fields=fields) if fields else None

    @staticmethod
    def _resolve_duration(
        config: ProjectConfiguration,
        subtitle_document: SubtitleDocument,
        audio_path: Path | None,
    ) -> float | None:
        if subtitle_document.audio_duration is not None:
            return subtitle_document.audio_duration
        if config.subtitles.audio_duration_seconds is not None:
            return config.subtitles.audio_duration_seconds
        if audio_path is not None:
            try:
                return get_audio_duration(audio_path)
            except AudioError:
                return None
        return None

    @staticmethod
    def _apply_preview(job: RenderJob) -> RenderJob:
        """Return a fast, low-resolution variant of the job (FR-033/FR-034)."""

        settings = job.settings
        preview_width = min(settings.width, PREVIEW_MAX_WIDTH)
        scale = preview_width / settings.width
        width = _even(round(settings.width * scale))
        height = _even(round(settings.height * scale))
        preview_settings = replace(
            settings, width=width, height=height, preset=PREVIEW_PRESET, crf=PREVIEW_CRF
        )
        output = job.output_path
        preview_output = output.with_name(f"{output.stem}_preview{output.suffix}")
        return replace(job, settings=preview_settings, output_path=preview_output)


def _even(value: int) -> int:
    """Round down to the nearest even number (H.264 requires even dimensions)."""

    return max(value - (value % 2), 2)


def build_core_pipeline() -> ProcessingPipeline:
    """Build the core processing pipeline."""

    stages: list[PipelineStage] = [
        ConfigurationStage(),
        ProjectLoadingStage(),
        ProviderInitializationStage(),
        SubtitleAlignmentStage(),
        SubtitleExportStage(),
        RenderingStage(),
    ]
    return ProcessingPipeline(stages)
