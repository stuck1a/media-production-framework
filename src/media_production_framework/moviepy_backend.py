"""
MoviePy rendering backend.

Implements a second, interchangeable
:class:`~media_production_framework.render_backends.RenderBackend` (FR-029),
using the MoviePy library instead of driving ``ffmpeg`` directly. It builds the
same kind of composition as the FFmpeg backend from a
:class:`~media_production_framework.rendering.RenderJob`:

- the background (solid colour, static image or looping video), scaled and
  padded to the output resolution while preserving aspect ratio
  (FR-049 - FR-054);
- the timed subtitle overlays rendered by the Text Renderer (Part 3);
- the project audio; and
- the configured encoder settings (FR-024 - FR-028).

MoviePy is an optional dependency (the ``moviepy`` extra) and is imported
lazily so this module -- and :class:`RenderBackendFactory` -- keep working
without it installed, exactly like the FFmpeg backend and the Whisper
alignment providers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from media_production_framework.configuration import TextConfiguration
from media_production_framework.layout import LayoutEngine, SegmentLayout, TextMeasurer
from media_production_framework.render_backends import BACKEND_MOVIEPY, RenderingError
from media_production_framework.rendering import (
    BackgroundOperation,
    RenderJob,
    RenderPlan,
    RenderProgress,
    RenderResult,
)
from media_production_framework.text_renderer import (
    FontFileSet,
    FontSourceMeasurer,
    TextRenderer,
    resolve_font_set,
)

ProgressCallback = Callable[[RenderProgress], None]


def is_moviepy_available() -> bool:
    """Return whether the optional ``moviepy`` dependency can be imported."""

    try:
        import moviepy  # noqa: F401
    except ImportError:
        return False
    return True


def _color_to_rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b)


@dataclass(frozen=True)
class OverlaySpec:
    """A rasterized overlay image and where/when to composite it."""

    path: Path
    x: int
    y: int
    start: float
    end: float


class MoviePyCommandBuilder:
    """Build a symbolic description of the MoviePy composition from a plan.

    MoviePy has no command-line form, so there is no literal argv to record.
    This mirrors the FFmpeg backend's ``argv`` regardless: a deterministic,
    ordered sequence of tokens describing every composition step, built
    without importing MoviePy, so it stays fully unit-testable.
    """

    def build(
        self,
        plan: RenderPlan,
        overlays: Sequence[OverlaySpec],
        audio_path: Path | None = None,
    ) -> tuple[str, ...]:
        """Return the ordered tokens describing the MoviePy composition."""

        background = plan.background
        tokens = [
            "moviepy",
            "compose",
            f"{plan.width}x{plan.height}@{plan.fps}",
            f"background={self._background_token(background)}",
        ]
        if plan.duration is not None:
            tokens.append(f"duration={plan.duration}")
        for overlay in overlays:
            tokens.append(
                f"overlay={overlay.path.name}:pos=({overlay.x},{overlay.y})"
                f":t={overlay.start}-{overlay.end}"
            )
        if audio_path is not None:
            tokens.append(f"audio={audio_path.name}")
        tokens += [
            f"codec={plan.video_codec}",
            f"bitrate={plan.video_bitrate}",
            f"preset={plan.preset}",
            f"fps={plan.fps}",
            f"out={plan.output_path.name}",
        ]
        return tuple(tokens)

    @staticmethod
    def _background_token(background: BackgroundOperation) -> str:
        if background.kind == "color":
            return f"color:{background.color}"
        detail = background.source.name if background.source is not None else "?"
        if background.kind == "video":
            return f"video:{detail}:loop={background.loop}"
        return f"{background.kind}:{detail}"


class _ProgressBridge:
    """Adapts MoviePy's proglog progress bars to :class:`RenderProgress`.

    MoviePy's ``write_videofile`` reports progress through a ``proglog`` bar
    named ``frame_index`` (current frame / total frames). This bridges that
    into the same ``RenderProgress`` callback shape used by the FFmpeg backend
    (FR-032, NFR-011), so callers do not need to know which backend is active.
    """

    def __init__(
        self, fps: int, total_seconds: float | None, on_progress: ProgressCallback
    ) -> None:
        self._fps = fps
        self._total_seconds = total_seconds
        self._on_progress = on_progress

    def build_logger(self) -> Any:
        import proglog

        bridge = self

        class _Logger(proglog.ProgressBarLogger):  # type: ignore[misc]
            def bars_callback(
                self, bar: str, attr: str, value: int, old_value: int | None = None
            ) -> None:
                if bar != "frame_index" or attr != "index":
                    return
                bridge._on_progress(
                    RenderProgress(
                        completed_seconds=value / bridge._fps,
                        total_seconds=bridge._total_seconds,
                    )
                )

        return _Logger()


class MoviePyRenderBackend:
    """Render backend that composes and encodes a video with MoviePy."""

    name = BACKEND_MOVIEPY

    def __init__(
        self,
        *,
        fonts: FontFileSet | None = None,
        measurer: TextMeasurer | None = None,
        on_progress: ProgressCallback | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._on_progress = on_progress
        self._logger = logger or logging.getLogger(__name__)
        self._command_builder = MoviePyCommandBuilder()
        # Fonts are resolved from the job's configured family lazily (mirrors the
        # FFmpeg backend); injected fonts/measurer take precedence for tests.
        self._injected_fonts = fonts
        self._injected_measurer = measurer
        self._layout_engine: LayoutEngine | None = None
        self._text_renderer: TextRenderer | None = None

    def _components(self, job: RenderJob) -> tuple[LayoutEngine, TextRenderer]:
        """Return the layout engine and text renderer for this job's font."""

        if self._layout_engine is None or self._text_renderer is None:
            fonts = self._injected_fonts or resolve_font_set(job.text.font, logger=self._logger)
            measurer = self._injected_measurer or FontSourceMeasurer(fonts)
            self._layout_engine = LayoutEngine(measurer)
            self._text_renderer = TextRenderer(fonts)
        return self._layout_engine, self._text_renderer

    def plan(self, job: RenderJob) -> RenderPlan:
        """Return the render plan, including the composition it would build."""

        layout_engine, _ = self._components(job)
        base = _base_plan(job, self.name)
        layouts = self._layout_document(job, layout_engine)
        specs = [
            _placement_spec(layout, job.text, Path(f"overlay-{layout.segment_index}.png"))
            for layout in layouts
        ]
        argv = self._command_builder.build(base, specs, job.audio_path)
        return replace(base, argv=argv)

    def render(self, job: RenderJob) -> RenderResult:
        """Compose and encode the video, returning the render result."""

        try:
            from moviepy import AudioFileClip, CompositeVideoClip, ImageClip
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RenderingError(
                "The MoviePy backend requires the optional 'moviepy' dependency. "
                "Install it with: pip install media-production-framework[moviepy]"
            ) from exc

        layout_engine, text_renderer = self._components(job)
        plan = _base_plan(job, self.name)

        with TemporaryDirectory(prefix="mpf-moviepy-") as tmp_dir:
            overlays = self._rasterize_overlays(
                job, Path(tmp_dir), layout_engine, text_renderer
            )
            background_clip = self._build_background_clip(job, plan)

            overlay_clips = [
                ImageClip(str(overlay.path), duration=max(overlay.end - overlay.start, 0.0))
                .with_start(overlay.start)
                .with_position((overlay.x, overlay.y))
                for overlay in overlays
            ]

            composite = CompositeVideoClip(
                [background_clip, *overlay_clips], size=(plan.width, plan.height)
            )
            if plan.duration is not None:
                composite = composite.with_duration(plan.duration)

            if job.audio_path is not None:
                audio_clip = AudioFileClip(str(job.audio_path))
                composite = composite.with_audio(audio_clip)

            self._write(composite, job, plan)

        if not job.output_path.is_file() or job.output_path.stat().st_size == 0:
            raise RenderingError(
                f"MoviePy reported success but produced no output at {job.output_path}."
            )

        return RenderResult(
            output_path=job.output_path,
            backend=self.name,
            success=True,
            duration=job.duration,
            preview=job.preview,
            message="Rendered with MoviePy.",
        )

    def _build_background_clip(self, job: RenderJob, plan: RenderPlan) -> Any:
        from moviepy import ColorClip, ImageClip, VideoFileClip
        from moviepy.video.fx import Loop

        background = BackgroundOperation.from_config(job.background)
        width, height = plan.width, plan.height

        if background.kind == "color":
            return ColorClip(
                size=(width, height),
                color=_color_to_rgb(background.color or "#000000"),
                duration=plan.duration,
            )

        if background.source is None:
            raise RenderingError(f"A '{background.kind}' background requires a source path.")

        if background.kind == "image":
            raw = ImageClip(str(background.source), duration=plan.duration)
        elif background.kind == "video":
            raw = VideoFileClip(str(background.source))
            if background.loop and plan.duration is not None:
                raw = raw.with_effects([Loop(duration=plan.duration)])
            elif plan.duration is not None:
                raw = raw.subclipped(0, min(plan.duration, raw.duration))
        else:
            raise RenderingError(f"Unsupported background kind: {background.kind}")

        return self._scale_and_pad(raw, width, height, plan.duration)

    @staticmethod
    def _scale_and_pad(clip: Any, width: int, height: int, duration: float | None) -> Any:
        from moviepy import ColorClip, CompositeVideoClip

        # Preserve aspect ratio (FR-054): scale to fit within the target frame,
        # then pad the remainder with a centred black canvas.
        scale = min(width / clip.w, height / clip.h)
        resized = clip.resized(new_size=(round(clip.w * scale), round(clip.h * scale)))
        canvas = ColorClip(
            size=(width, height), color=(0, 0, 0), duration=duration or clip.duration
        )
        return CompositeVideoClip(
            [canvas, resized.with_position(("center", "center"))], size=(width, height)
        )

    @staticmethod
    def _layout_document(
        job: RenderJob, layout_engine: LayoutEngine
    ) -> Sequence[SegmentLayout]:
        return layout_engine.layout_document(
            job.subtitle_document,
            job.text,
            job.settings.width,
            job.settings.height,
        )

    def _rasterize_overlays(
        self,
        job: RenderJob,
        tmp_dir: Path,
        layout_engine: LayoutEngine,
        text_renderer: TextRenderer,
    ) -> list[OverlaySpec]:
        layouts = self._layout_document(job, layout_engine)
        overlays = text_renderer.render_document(layouts, job.text)
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

    def _write(self, composite: Any, job: RenderJob, plan: RenderPlan) -> None:
        job.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._logger.info("Rendering '%s' with MoviePy.", job.output_path.name)

        kwargs: dict[str, Any] = {
            "fps": plan.fps,
            "codec": plan.video_codec,
            "bitrate": plan.video_bitrate,
            "preset": plan.preset,
            "audio": job.audio_path is not None,
        }
        if self._on_progress is not None:
            bridge = _ProgressBridge(plan.fps, plan.duration, self._on_progress)
            kwargs["logger"] = bridge.build_logger()

        composite.write_videofile(str(job.output_path), **kwargs)


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
    # The Text Renderer pads the top-left of each overlay by the outline width
    # (see text_renderer.TextRenderer.render); mirror that here so the plan
    # preview matches the placement actually used at render time.
    pad = max(text_config.outline, 0)
    return OverlaySpec(
        path=path,
        x=layout.box.x - pad,
        y=layout.box.y - pad,
        start=layout.start,
        end=layout.end,
    )
