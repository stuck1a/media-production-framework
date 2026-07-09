"""
Rendering domain objects.

These objects describe *what* should be rendered and *what happened* during a
render, independently of *how* it is executed. The execution strategy lives
behind the :class:`~media_production_framework.render_backends.RenderBackend`
seam (see ADR-0002); keeping the description separate from the execution is what
makes the Rendering Engine deterministic and testable without invoking FFmpeg.

All objects are frozen so a :class:`RenderPlan` produced for a given
:class:`RenderJob` is reproducible and safe to assert against in unit tests.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from media_production_framework.configuration import (
    BackgroundConfiguration,
    FfmpegConfiguration,
    RenderConfiguration,
    TextConfiguration,
)
from media_production_framework.domain import SongMetadata
from media_production_framework.subtitles import SubtitleDocument


@dataclass(frozen=True)
class RenderSettings:
    """Resolved output format and encoder settings for a render.

    This is the execution-facing view of :class:`RenderConfiguration` and
    :class:`FfmpegConfiguration`: it flattens the values a backend needs to
    encode the final video, leaving layout/background details in the job.
    """

    width: int
    height: int
    fps: int
    video_bitrate: str
    video_codec: str
    audio_sample_rate: int
    preset: str
    crf: int

    @property
    def resolution(self) -> tuple[int, int]:
        """Return the output resolution as a ``(width, height)`` tuple."""

        return (self.width, self.height)

    @classmethod
    def from_config(
        cls,
        render_config: RenderConfiguration,
        ffmpeg_config: FfmpegConfiguration,
    ) -> RenderSettings:
        """Build render settings from validated configuration objects."""

        video = render_config.video
        return cls(
            width=video.width,
            height=video.height,
            fps=video.fps,
            video_bitrate=video.bitrate,
            video_codec=video.codec,
            audio_sample_rate=ffmpeg_config.sample_rate,
            preset=ffmpeg_config.preset,
            crf=ffmpeg_config.crf,
        )


@dataclass(frozen=True)
class BackgroundOperation:
    """Deterministic description of how the background is produced.

    Derived from :class:`BackgroundConfiguration`; it names the source kind and
    carries either the resolved colour or the media path so a backend can build
    its command without re-reading configuration.
    """

    kind: str
    color: str | None = None
    source: Path | None = None
    loop: bool = True

    @classmethod
    def from_config(cls, background: BackgroundConfiguration) -> BackgroundOperation:
        """Build a background operation from a validated configuration."""

        return cls(
            kind=background.type,
            color=background.color,
            source=background.source,
            loop=background.loop,
        )


@dataclass(frozen=True)
class RenderJob:
    """A complete, self-contained request to render a video.

    Bundles the subtitle model, the audio/output paths, the resolved encoder
    settings and the background/text configuration a backend needs. ``preview``
    marks a fast, lower-effort render that reuses the same pipeline (FR-033).
    """

    output_path: Path
    settings: RenderSettings
    background: BackgroundConfiguration
    text: TextConfiguration
    subtitle_document: SubtitleDocument = field(default_factory=SubtitleDocument)
    audio_path: Path | None = None
    metadata: SongMetadata | None = None
    duration: float | None = None
    preview: bool = False

    @property
    def resolution(self) -> tuple[int, int]:
        """Return the output resolution as a ``(width, height)`` tuple."""

        return self.settings.resolution


@dataclass(frozen=True)
class RenderPlan:
    """The deterministic description of a render a backend intends to perform.

    A :class:`RenderPlan` is produced from a :class:`RenderJob` *before* any
    external tooling runs. ``argv`` records the exact command a backend would
    execute, which lets unit tests assert command construction without invoking
    FFmpeg (see ADR-0002).
    """

    backend: str
    width: int
    height: int
    fps: int
    duration: float | None
    background: BackgroundOperation
    output_path: Path
    video_codec: str
    video_bitrate: str
    audio_sample_rate: int
    preset: str
    crf: int
    segment_count: int = 0
    metadata: Mapping[str, str] = field(default_factory=dict)
    argv: Sequence[str] = field(default_factory=tuple)
    preview: bool = False

    @property
    def resolution(self) -> tuple[int, int]:
        """Return the planned output resolution as a ``(width, height)`` tuple."""

        return (self.width, self.height)


@dataclass(frozen=True)
class RenderProgress:
    """Progress information published during a long-running render (FR-032)."""

    completed_seconds: float
    total_seconds: float | None = None

    @property
    def fraction(self) -> float:
        """Return completion in the ``[0.0, 1.0]`` range (0 if total unknown)."""

        if self.total_seconds is None or self.total_seconds <= 0:
            return 0.0
        return min(max(self.completed_seconds / self.total_seconds, 0.0), 1.0)


@dataclass(frozen=True)
class RenderResult:
    """Outcome of a render operation."""

    output_path: Path
    backend: str
    success: bool
    duration: float | None = None
    preview: bool = False
    message: str = ""
