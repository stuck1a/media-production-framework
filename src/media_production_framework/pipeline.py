"""
Processing pipeline infrastructure.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from media_production_framework.configuration import ConfigurationLoader, ProjectConfiguration
from media_production_framework.domain import Project
from media_production_framework.events import (
    ConfigurationLoadedEvent,
    EventBus,
    PipelineCompletedEvent,
    PipelineStageCompletedEvent,
    PipelineStartedEvent,
    ProjectLoadedEvent,
)
from media_production_framework.projects import ProjectLoader
from media_production_framework.providers import ProviderRegistry


@dataclass
class PipelineContext:
    """Shared runtime state passed between pipeline stages."""

    project_root: Path
    configuration_path: Path | None = None
    strict_validation: bool = True
    configuration: ProjectConfiguration | None = None
    project: Project | None = None
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


class PlaceholderProcessingStage:
    """Placeholder for future domain processing stages."""

    name = "placeholder-processing"

    def execute(self, context: PipelineContext) -> PipelineContext:
        context.artifacts["placeholder_processing_completed"] = True
        return context


def build_core_pipeline() -> ProcessingPipeline:
    """Build the M1 core pipeline."""

    stages: list[PipelineStage] = [
        ConfigurationStage(),
        ProjectLoadingStage(),
        ProviderInitializationStage(),
        PlaceholderProcessingStage(),
    ]
    return ProcessingPipeline(stages)
