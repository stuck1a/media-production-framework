"""
Synchronous event infrastructure.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypeVar
from uuid import uuid4


@dataclass(frozen=True)
class Event:
    """Base class for framework events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # noqa: UP017


@dataclass(frozen=True)
class ApplicationStartedEvent(Event):
    """Published when application execution starts."""


@dataclass(frozen=True)
class ConfigurationLoadedEvent(Event):
    """Published after configuration has been loaded."""

    path: str = ""


@dataclass(frozen=True)
class ProjectLoadedEvent(Event):
    """Published after a project has been loaded."""

    project_root: str = ""


@dataclass(frozen=True)
class PipelineStartedEvent(Event):
    """Published when pipeline execution starts."""


@dataclass(frozen=True)
class PipelineStageCompletedEvent(Event):
    """Published after a pipeline stage completes."""

    stage_name: str = ""


@dataclass(frozen=True)
class PipelineCompletedEvent(Event):
    """Published when pipeline execution completes."""


@dataclass(frozen=True)
class ValidationFailedEvent(Event):
    """Published when validation fails."""

    message: str = ""


@dataclass(frozen=True)
class AlignmentStartedEvent(Event):
    """Published when subtitle alignment starts."""

    provider: str = ""


@dataclass(frozen=True)
class AlignmentCompletedEvent(Event):
    """Published after subtitle alignment completes."""

    provider: str = ""
    segment_count: int = 0


@dataclass(frozen=True)
class SubtitleGeneratedEvent(Event):
    """Published when a subtitle document has been generated."""

    segment_count: int = 0


@dataclass(frozen=True)
class SubtitleExportCompletedEvent(Event):
    """Published after subtitle files have been written to disk."""

    srt_path: str = ""
    json_path: str = ""


@dataclass(frozen=True)
class RenderingStartedEvent(Event):
    """Published when video rendering starts."""

    backend: str = ""
    preview: bool = False


@dataclass(frozen=True)
class RenderingProgressEvent(Event):
    """Published periodically while a render is in progress (FR-032)."""

    fraction: float = 0.0
    completed_seconds: float = 0.0
    total_seconds: float | None = None


@dataclass(frozen=True)
class RenderingCompletedEvent(Event):
    """Published after video rendering completes."""

    backend: str = ""
    output_path: str = ""
    success: bool = False


@dataclass(frozen=True)
class PreviewRenderingCompletedEvent(Event):
    """Published after a preview render completes (FR-033/FR-034)."""

    backend: str = ""
    output_path: str = ""


EventT = TypeVar("EventT", bound=Event)
EventHandler = Callable[[EventT], None]


class EventBus:
    """Dispatch framework events to subscribed handlers."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._subscribers: defaultdict[type[Event], list[EventHandler[Event]]] = defaultdict(list)
        self.published_events: list[Event] = []

    def subscribe(self, event_type: type[EventT], handler: EventHandler[EventT]) -> None:
        """Register a handler for an event type."""

        self._subscribers[event_type].append(handler)  # type: ignore[arg-type]

    def publish(self, event: Event) -> None:
        """Publish an event to matching handlers."""

        self.published_events.append(event)
        handlers = list(self._subscribers[type(event)]) + list(self._subscribers[Event])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                self._logger.exception("Event handler failed for %s", type(event).__name__)
