"""
FFmpeg rendering backend.

Implements the real :class:`~media_production_framework.render_backends.RenderBackend`
by driving the ``ffmpeg`` binary as a subprocess (see ADR-0002). It turns a
:class:`~media_production_framework.rendering.RenderJob` into a full FFmpeg
command/filtergraph that

- produces the background (solid colour, static image or looping video),
  scaled and padded to the output resolution while preserving aspect ratio
  (FR-049 - FR-054);
- overlays the timed subtitle text rendered by the Text Renderer (Part 3);
- maps the project audio and applies the configured encoder settings
  (FR-024 - FR-028); and
- reports progress by parsing ``-progress`` output (FR-032, NFR-011).

FFmpeg is an external tool, not a Python dependency, so the module imports
cleanly without it. It is registered in ``RenderBackendFactory`` with a lazy
import; ``render`` probes the binary and raises :class:`RenderingError` when it
is missing so the factory can fall back to another backend (FR-031).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from media_production_framework.configuration import TextConfiguration
from media_production_framework.layout import LayoutEngine, SegmentLayout, TextMeasurer
from media_production_framework.render_backends import BACKEND_FFMPEG, RenderingError
from media_production_framework.rendering import (
    BackgroundOperation,
    RenderJob,
    RenderPlan,
    RenderProgress,
    RenderResult,
)
from media_production_framework.text_renderer import FontFileSet, TextRenderer, default_font_set

DEFAULT_FFMPEG_BINARY = "ffmpeg"
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_PIXEL_FORMAT = "yuv420p"

ProgressCallback = Callable[[RenderProgress], None]


@dataclass(frozen=True)
class OverlaySpec:
    """A rasterized overlay image and where/when to composite it."""

    path: Path
    x: int
    y: int
    start: float
    end: float


def _format_time(value: float) -> str:
    """Format a time/duration in seconds with millisecond precision."""

    return f"{value:.3f}"


def _color_to_ffmpeg(color: str) -> str:
    """Convert a ``#RRGGBB`` hex colour into FFmpeg's ``0xRRGGBB`` form."""

    return "0x" + color.lstrip("#").upper()


def resolve_ffmpeg_binary(binary: str | None = None) -> str:
    """Return an executable path for ffmpeg, or raise :class:`RenderingError`.

    An explicit existing file path is used as-is; otherwise the name is looked
    up on ``PATH``. Raising here lets the factory treat an absent binary as a
    trigger to fall back to another backend (FR-031).
    """

    candidate = binary or DEFAULT_FFMPEG_BINARY
    if Path(candidate).is_file():
        return candidate
    resolved = shutil.which(candidate)
    if resolved is None:
        raise RenderingError(
            f"The ffmpeg binary '{candidate}' was not found. Install FFmpeg and "
            "ensure it is on PATH, or configure an explicit binary path."
        )
    return resolved


def is_ffmpeg_available(binary: str | None = None) -> bool:
    """Return whether a working ffmpeg binary can be located and executed."""

    try:
        path = resolve_ffmpeg_binary(binary)
    except RenderingError:
        return False
    try:
        completed = subprocess.run(
            [path, "-version"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


class FfmpegProgressParser:
    """Parse ffmpeg ``-progress`` key/value output into progress updates.

    ffmpeg emits ``key=value`` lines; a new value for ``out_time_us`` (elapsed
    output time in microseconds) marks measurable forward progress, which is
    the only key this parser reacts to. ``N/A`` values (emitted before the
    first frame) are ignored.
    """

    def __init__(self, total_seconds: float | None) -> None:
        self._total_seconds = total_seconds

    def feed(self, line: str) -> RenderProgress | None:
        """Return a :class:`RenderProgress` if ``line`` reports elapsed time."""

        key, separator, value = line.partition("=")
        if separator != "=" or key.strip() != "out_time_us":
            return None
        try:
            microseconds = int(value.strip())
        except ValueError:
            return None
        return RenderProgress(
            completed_seconds=microseconds / 1_000_000,
            total_seconds=self._total_seconds,
        )


@dataclass(frozen=True)
class FontSourceMeasurer:
    """A :class:`TextMeasurer` that measures with the rasterizer's own fonts.

    Using the same :class:`FontFileSet` for both measurement and rasterization
    keeps the Layout Engine's line breaks consistent with what is actually
    drawn, avoiding overflow from a mismatched metrics source.
    """

    fonts: FontFileSet

    def measure(
        self, text: str, font: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        from PIL import Image, ImageDraw

        loaded = self.fonts.resolve(bold=bold, italic=italic).load(size)
        draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=loaded)
        return (int(right - left), int(bottom - top))


class FfmpegCommandBuilder:
    """Build the ffmpeg argv/filtergraph from a plan, overlays and audio.

    This is a pure function of its inputs (no I/O, no subprocess), so the
    command construction is fully unit-testable via argv assertions without
    running ffmpeg.
    """

    def build(
        self,
        plan: RenderPlan,
        overlays: Sequence[OverlaySpec],
        audio_path: Path | None = None,
        *,
        ffmpeg_binary: str = DEFAULT_FFMPEG_BINARY,
    ) -> list[str]:
        """Return the complete ffmpeg command line for the given plan."""

        command: list[str] = [ffmpeg_binary, "-y"]
        command += self._background_input(plan)

        has_audio = audio_path is not None
        if audio_path is not None:
            command += ["-i", str(audio_path)]

        for overlay in overlays:
            command += ["-i", str(overlay.path)]

        overlay_start_index = 1 + (1 if has_audio else 0)
        filtergraph, video_label = self._filtergraph(plan, overlays, overlay_start_index)
        command += ["-filter_complex", filtergraph, "-map", f"[{video_label}]"]

        if has_audio:
            audio_index = 1
            command += ["-map", f"{audio_index}:a", "-c:a", DEFAULT_AUDIO_CODEC]
            command += ["-ar", str(plan.audio_sample_rate)]

        command += [
            "-c:v",
            plan.video_codec,
            "-preset",
            plan.preset,
            "-crf",
            str(plan.crf),
            "-b:v",
            plan.video_bitrate,
            "-pix_fmt",
            DEFAULT_PIXEL_FORMAT,
            "-r",
            str(plan.fps),
        ]

        command += self._duration_flags(plan.duration, has_audio)
        command += ["-progress", "pipe:1", "-nostats"]
        command += [str(plan.output_path)]
        return command

    @staticmethod
    def _background_input(plan: RenderPlan) -> list[str]:
        background = plan.background
        if background.kind == "color":
            color = _color_to_ffmpeg(background.color or "#000000")
            spec = f"color=c={color}:s={plan.width}x{plan.height}:r={plan.fps}"
            if plan.duration is not None:
                spec += f":d={_format_time(plan.duration)}"
            return ["-f", "lavfi", "-i", spec]

        if background.source is None:
            raise RenderingError(
                f"A '{background.kind}' background requires a source path."
            )

        if background.kind == "image":
            return ["-loop", "1", "-i", str(background.source)]

        if background.kind == "video":
            if background.loop:
                # Loop the source indefinitely; the output is trimmed to the
                # exact duration by the -t / -shortest flags (FR-052/FR-053).
                return ["-stream_loop", "-1", "-i", str(background.source)]
            return ["-i", str(background.source)]

        raise RenderingError(f"Unsupported background kind: {background.kind}")

    @staticmethod
    def _filtergraph(
        plan: RenderPlan,
        overlays: Sequence[OverlaySpec],
        overlay_start_index: int,
    ) -> tuple[str, str]:
        # Scale the background into the frame preserving aspect ratio, then pad
        # the remaining area, centring the content (FR-054).
        scale_pad = (
            f"[0:v]scale={plan.width}:{plan.height}:force_original_aspect_ratio=decrease,"
            f"pad={plan.width}:{plan.height}:(ow-iw)/2:(oh-ih)/2,setsar=1[bg]"
        )
        filters = [scale_pad]

        current_label = "bg"
        for offset, overlay in enumerate(overlays):
            input_index = overlay_start_index + offset
            output_label = f"v{offset}"
            enable = f"between(t,{_format_time(overlay.start)},{_format_time(overlay.end)})"
            filters.append(
                f"[{current_label}][{input_index}:v]"
                f"overlay=x={overlay.x}:y={overlay.y}:enable='{enable}'[{output_label}]"
            )
            current_label = output_label

        return (";".join(filters), current_label)

    @staticmethod
    def _duration_flags(duration: float | None, has_audio: bool) -> list[str]:
        if duration is not None:
            # Trim every input to the exact output duration (FR-053).
            return ["-t", _format_time(duration)]
        if has_audio:
            # Without an explicit duration, end when the audio ends.
            return ["-shortest"]
        return []


class FfmpegRenderBackend:
    """Render backend that composes and encodes a video with ffmpeg."""

    name = BACKEND_FFMPEG

    def __init__(
        self,
        *,
        ffmpeg_binary: str | None = None,
        fonts: FontFileSet | None = None,
        measurer: TextMeasurer | None = None,
        on_progress: ProgressCallback | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._binary = ffmpeg_binary
        self._fonts = fonts or default_font_set()
        self._measurer = measurer or FontSourceMeasurer(self._fonts)
        self._on_progress = on_progress
        self._logger = logger or logging.getLogger(__name__)
        self._layout_engine = LayoutEngine(self._measurer)
        self._text_renderer = TextRenderer(self._fonts)
        self._command_builder = FfmpegCommandBuilder()

    def plan(self, job: RenderJob) -> RenderPlan:
        """Return the render plan, including the ffmpeg command it would run."""

        base = _base_plan(job, self.name)
        layouts = self._layout_document(job)
        specs = [
            _placement_spec(layout, job.text, Path(f"overlay-{layout.segment_index}.png"))
            for layout in layouts
        ]
        argv = self._command_builder.build(
            base,
            specs,
            job.audio_path,
            ffmpeg_binary=self._binary or DEFAULT_FFMPEG_BINARY,
        )
        return replace(base, argv=tuple(argv))

    def render(self, job: RenderJob) -> RenderResult:
        """Compose and encode the video, returning the render result."""

        binary = resolve_ffmpeg_binary(self._binary)
        plan = _base_plan(job, self.name)

        with TemporaryDirectory(prefix="mpf-render-") as tmp_dir:
            overlays = self._rasterize_overlays(job, Path(tmp_dir))
            command = self._command_builder.build(
                plan, overlays, job.audio_path, ffmpeg_binary=binary
            )
            self._run(command, job.duration, job.output_path)

        if not job.output_path.is_file() or job.output_path.stat().st_size == 0:
            raise RenderingError(
                f"ffmpeg reported success but produced no output at {job.output_path}."
            )

        return RenderResult(
            output_path=job.output_path,
            backend=self.name,
            success=True,
            duration=job.duration,
            preview=job.preview,
            message="Rendered with ffmpeg.",
        )

    def _layout_document(self, job: RenderJob) -> Sequence[SegmentLayout]:
        return self._layout_engine.layout_document(
            job.subtitle_document,
            job.text,
            job.settings.width,
            job.settings.height,
        )

    def _rasterize_overlays(self, job: RenderJob, tmp_dir: Path) -> list[OverlaySpec]:
        layouts = self._layout_document(job)
        overlays = self._text_renderer.render_document(layouts, job.text)
        specs: list[OverlaySpec] = []
        for layout in layouts:
            overlay = overlays[layout.segment_index]
            image_path = tmp_dir / f"overlay-{layout.segment_index}.png"
            overlay.image.save(image_path)
            specs.append(
                OverlaySpec(
                    path=image_path,
                    x=overlay.box.x,
                    y=overlay.box.y,
                    start=overlay.start,
                    end=overlay.end,
                )
            )
        return specs

    def _run(self, command: list[str], duration: float | None, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.info("Running ffmpeg with %d arguments.", len(command))
        parser = FfmpegProgressParser(duration)

        # Progress is written to stdout (``-progress pipe:1``); ffmpeg's logs go
        # to stderr. Merge them into one stream and drain it in a single loop so
        # a full stderr pipe can never deadlock the process.
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise RenderingError(f"Failed to start ffmpeg: {exc}") from exc

        stdout = process.stdout
        assert stdout is not None  # noqa: S101 - guaranteed by stdout=PIPE
        recent_lines: deque[str] = deque(maxlen=50)
        for line in stdout:
            stripped = line.strip()
            recent_lines.append(stripped)
            progress = parser.feed(stripped)
            if progress is not None and self._on_progress is not None:
                self._on_progress(progress)

        return_code = process.wait()
        if return_code != 0:
            tail = " | ".join(entry for entry in recent_lines if entry)[-500:]
            raise RenderingError(f"ffmpeg failed with exit code {return_code}: {tail}")


def _base_plan(job: RenderJob, backend_name: str) -> RenderPlan:
    """Build the plan skeleton shared by planning and execution."""

    settings = job.settings
    background = BackgroundOperation.from_config(job.background)
    metadata = _metadata_mapping(job.metadata)
    return RenderPlan(
        backend=backend_name,
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
        preview=job.preview,
    )


def _metadata_mapping(metadata: Any) -> dict[str, str]:
    if metadata is None:
        return {}
    return {str(key): str(value) for key, value in metadata.fields.items() if value is not None}


def _placement_spec(
    layout: SegmentLayout,
    text_config: TextConfiguration,
    path: Path,
) -> OverlaySpec:
    # The Text Renderer pads the top-left of each overlay by the outline width,
    # so the overlay is placed that many pixels up and to the left of the text
    # box; mirror that here so the plan matches the rasterized placement.
    pad = max(text_config.outline, 0)
    return OverlaySpec(
        path=path,
        x=layout.box.x - pad,
        y=layout.box.y - pad,
        start=layout.start,
        end=layout.end,
    )
