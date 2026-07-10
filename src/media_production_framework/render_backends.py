"""
Rendering backends.

The Rendering Engine executes a :class:`~media_production_framework.rendering.RenderJob`
through a pluggable :class:`RenderBackend`, mirroring the provider pattern used
by the Alignment Engine (see ``alignment.py`` and ADR-0001). Every backend turns
a job into a deterministic :class:`~media_production_framework.rendering.RenderPlan`
first, then optionally executes it.

The default :class:`DryRunRenderBackend` builds the plan and records the command
it *would* run without invoking any external tooling. This keeps the module
importable and the pipeline testable with zero heavy dependencies. Real backends
(FFmpeg, MoviePy) are added in later milestone parts and import their heavy
dependencies lazily, exactly like the Whisper alignment providers.

See ADR-0002 for the rationale behind the plan/execute split.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from media_production_framework.domain import SongMetadata
from media_production_framework.rendering import (
    BackgroundOperation,
    RenderJob,
    RenderPlan,
    RenderResult,
)

BACKEND_DRY_RUN = "dry-run"
BACKEND_FFMPEG = "ffmpeg"
BACKEND_MOVIEPY = "moviepy"
BACKEND_AUTO = "auto"

DEFAULT_RENDER_BACKEND = BACKEND_DRY_RUN

# FR-030: automatic selection prefers FFmpeg, falling back to MoviePy.
AUTO_BACKEND_ORDER: tuple[str, ...] = (BACKEND_FFMPEG, BACKEND_MOVIEPY)

BackendAvailabilityCheck = Callable[[], bool]


class RenderingError(RuntimeError):
    """Raised when video rendering fails or is misconfigured."""


class RenderBackend(Protocol):
    """Interface implemented by rendering backends."""

    name: str

    def plan(self, job: RenderJob) -> RenderPlan:
        """Return the deterministic render plan for the given job."""

    def render(self, job: RenderJob) -> RenderResult:
        """Execute the render described by the job and return its result."""


def _metadata_mapping(metadata: SongMetadata | None) -> dict[str, str]:
    """Flatten song metadata into a deterministic string mapping."""

    if metadata is None:
        return {}
    return {str(key): str(value) for key, value in metadata.fields.items() if value is not None}


def _background_token(operation: BackgroundOperation) -> str:
    """Build a stable, human-readable token describing the background."""

    if operation.kind == "color":
        return f"color:{operation.color}"
    detail = operation.source.name if operation.source is not None else "?"
    if operation.kind == "video":
        return f"video:{detail}:loop={operation.loop}"
    return f"{operation.kind}:{detail}"


class DryRunRenderBackend:
    """Deterministic backend that plans a render without executing it.

    This is the rendering analogue of the offline ``heuristic`` alignment
    provider: it produces the full :class:`RenderPlan` (and the symbolic command
    it would run) so the pipeline and its tests exercise the whole seam without
    FFmpeg, MoviePy or any file being written.
    """

    name = BACKEND_DRY_RUN

    def plan(self, job: RenderJob) -> RenderPlan:
        settings = job.settings
        background = BackgroundOperation.from_config(job.background)
        metadata = _metadata_mapping(job.metadata)
        argv = self._build_argv(job, background, metadata)
        return RenderPlan(
            backend=self.name,
            width=settings.width,
            height=settings.height,
            fps=settings.fps,
            duration=job.duration,
            background=background,
            output_path=job.output_path,
            video_codec=settings.video_codec,
            video_bitrate=settings.video_bitrate,
            audio_sample_rate=settings.audio_sample_rate,
            preset=settings.preset,
            crf=settings.crf,
            segment_count=len(job.subtitle_document.segments),
            metadata=metadata,
            argv=argv,
            preview=job.preview,
        )

    def render(self, job: RenderJob) -> RenderResult:
        # A dry run performs no I/O: it only confirms the job produces a valid
        # plan, then reports success without touching the output path.
        self.plan(job)
        return RenderResult(
            output_path=job.output_path,
            backend=self.name,
            success=True,
            duration=job.duration,
            preview=job.preview,
            message="Dry run: no output was written.",
        )

    @staticmethod
    def _build_argv(
        job: RenderJob,
        background: BackgroundOperation,
        metadata: dict[str, str],
    ) -> tuple[str, ...]:
        settings = job.settings
        tokens = [
            "dry-run",
            "render",
            f"{settings.width}x{settings.height}@{settings.fps}",
            f"background={_background_token(background)}",
            f"codec={settings.video_codec}",
            f"bitrate={settings.video_bitrate}",
            f"preset={settings.preset}",
            f"crf={settings.crf}",
            f"sample_rate={settings.audio_sample_rate}",
            f"segments={len(job.subtitle_document.segments)}",
        ]
        if job.audio_path is not None:
            tokens.append(f"audio={job.audio_path.name}")
        if job.duration is not None:
            tokens.append(f"duration={job.duration}")
        for key in sorted(metadata):
            tokens.append(f"meta:{key}={metadata[key]}")
        if job.preview:
            tokens.append("preview")
        tokens.append(f"out={job.output_path.name}")
        return tuple(tokens)


def resolve_auto_backend(
    order: Sequence[str],
    availability: Mapping[str, BackendAvailabilityCheck],
) -> str:
    """Return the first available backend name in ``order`` (FR-030/FR-031).

    Pure selection policy, independent of how a backend is instantiated: it
    only calls the injected availability checks, so it is fully testable with
    fake checks and needs neither FFmpeg nor MoviePy installed.
    """

    checked: list[str] = []
    for name in order:
        check = availability.get(name)
        if check is not None and check():
            return name
        checked.append(name)
    raise RenderingError(
        f"No rendering backend is available (checked: {', '.join(checked)}). "
        "Install ffmpeg or the 'moviepy' extra, or configure an explicit backend."
    )


def _ffmpeg_available() -> bool:
    from media_production_framework.ffmpeg_backend import is_ffmpeg_available

    return is_ffmpeg_available()


def _moviepy_available() -> bool:
    from media_production_framework.moviepy_backend import is_moviepy_available

    return is_moviepy_available()


def default_backend_availability() -> dict[str, BackendAvailabilityCheck]:
    """Return the real, lazily-evaluated availability check for each backend."""

    return {BACKEND_FFMPEG: _ffmpeg_available, BACKEND_MOVIEPY: _moviepy_available}


class RenderBackendFactory:
    """Create rendering backends by name.

    The offline :class:`DryRunRenderBackend` is always available. The FFmpeg
    and MoviePy backends are imported lazily so this module keeps importing
    (and the dry-run path keeps working) even where neither is installed.
    ``"auto"`` resolves to the first available backend in
    :data:`AUTO_BACKEND_ORDER` using ``availability`` (real system probes by
    default; tests may inject fakes, see :func:`resolve_auto_backend`).
    """

    def __init__(self, availability: Mapping[str, BackendAvailabilityCheck] | None = None) -> None:
        self._availability = availability or default_backend_availability()

    def create(self, name: str) -> RenderBackend:
        """Return a rendering backend for the given name."""

        normalized = name.lower()
        if normalized == BACKEND_DRY_RUN:
            return DryRunRenderBackend()
        if normalized == BACKEND_AUTO:
            resolved = resolve_auto_backend(AUTO_BACKEND_ORDER, self._availability)
            return self.create(resolved)
        if normalized == BACKEND_FFMPEG:
            from media_production_framework.ffmpeg_backend import FfmpegRenderBackend

            return FfmpegRenderBackend()
        if normalized == BACKEND_MOVIEPY:
            from media_production_framework.moviepy_backend import MoviePyRenderBackend

            return MoviePyRenderBackend()
        raise RenderingError(f"Unknown rendering backend: {name}")


@dataclass
class RenderService:
    """Facade coordinating backend selection, planning and execution."""

    factory: RenderBackendFactory = field(default_factory=RenderBackendFactory)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def plan(self, job: RenderJob, backend_name: str = DEFAULT_RENDER_BACKEND) -> RenderPlan:
        """Build the render plan for a job using the named backend."""

        return self.factory.create(backend_name).plan(job)

    def render(self, job: RenderJob, backend_name: str = DEFAULT_RENDER_BACKEND) -> RenderResult:
        """Render a job using the named backend and return its result."""

        backend = self.factory.create(backend_name)
        self.logger.info(
            "Rendering '%s' using backend '%s'.",
            job.output_path.name,
            backend.name,
        )
        return backend.render(job)
