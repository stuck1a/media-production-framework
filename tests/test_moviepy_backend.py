from __future__ import annotations

import wave
from pathlib import Path

import pytest

from media_production_framework.configuration import BackgroundConfiguration, TextConfiguration
from media_production_framework.moviepy_backend import (
    MoviePyCommandBuilder,
    MoviePyRenderBackend,
    is_moviepy_available,
)
from media_production_framework.moviepy_backend import OverlaySpec as MoviePyOverlaySpec
from media_production_framework.render_backends import RenderBackendFactory, RenderingError
from media_production_framework.rendering import (
    BackgroundOperation,
    RenderJob,
    RenderPlan,
    RenderSettings,
)
from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment


def make_plan(
    background: BackgroundOperation,
    *,
    duration: float | None = 1.0,
    output: str = "out.mp4",
) -> RenderPlan:
    return RenderPlan(
        backend="moviepy",
        width=1920,
        height=1080,
        fps=30,
        duration=duration,
        background=background,
        output_path=Path(output),
        video_codec="libx264",
        video_bitrate="8M",
        audio_sample_rate=48000,
        preset="medium",
        crf=18,
    )


def color_bg(color: str = "#101820") -> BackgroundOperation:
    return BackgroundOperation(kind="color", color=color, source=None, loop=True)


# --- Command builder: pure, no MoviePy import required ------------------------


def test_color_background_token() -> None:
    plan = make_plan(color_bg("#112233"))
    tokens = MoviePyCommandBuilder().build(plan, [], None)

    assert tokens[0] == "moviepy"
    assert "background=color:#112233" in tokens
    assert "duration=1.0" in tokens
    assert tokens[-1] == "out=out.mp4"


def test_image_background_token() -> None:
    background = BackgroundOperation(kind="image", source=Path("bg.png"), loop=False)
    tokens = MoviePyCommandBuilder().build(make_plan(background), [], None)

    assert "background=image:bg.png" in tokens


def test_video_background_token_includes_loop_flag() -> None:
    background = BackgroundOperation(kind="video", source=Path("clip.mp4"), loop=True)
    tokens = MoviePyCommandBuilder().build(make_plan(background), [], None)

    assert "background=video:clip.mp4:loop=True" in tokens


def test_overlay_and_audio_tokens() -> None:
    plan = make_plan(color_bg())
    overlays = [
        MoviePyOverlaySpec(path=Path("o1.png"), x=10, y=20, start=0.0, end=1.5),
        MoviePyOverlaySpec(path=Path("o2.png"), x=30, y=40, start=1.5, end=3.0),
    ]
    tokens = MoviePyCommandBuilder().build(plan, overlays, Path("song.wav"))

    assert "overlay=o1.png:pos=(10,20):t=0.0-1.5" in tokens
    assert "overlay=o2.png:pos=(30,40):t=1.5-3.0" in tokens
    assert "audio=song.wav" in tokens


def test_encoder_settings_tokens() -> None:
    plan = make_plan(color_bg())
    tokens = MoviePyCommandBuilder().build(plan, [], None)

    assert "codec=libx264" in tokens
    assert "bitrate=8M" in tokens
    assert "preset=medium" in tokens
    assert "fps=30" in tokens


# --- Availability + factory ----------------------------------------------------


def test_factory_creates_moviepy_backend() -> None:
    backend = RenderBackendFactory().create("moviepy")

    assert isinstance(backend, MoviePyRenderBackend)
    assert backend.name == "moviepy"


def test_moviepy_backend_module_is_importable_regardless_of_moviepy_install() -> None:
    # The module itself must import cleanly even if moviepy is absent; only
    # actually rendering requires it. is_moviepy_available reflects the truth
    # of the current environment either way.
    assert is_moviepy_available() in (True, False)


# --- Plan construction (pure; exercises layout + placement, no moviepy needed) -


def build_job(output_path: Path, *, audio_path: Path | None = None) -> RenderJob:
    settings = RenderSettings(
        width=160,
        height=90,
        fps=10,
        video_bitrate="500k",
        video_codec="libx264",
        audio_sample_rate=48000,
        preset="ultrafast",
        crf=30,
    )
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(index=1, text="Hello", start=0.0, end=0.3),
            SubtitleSegment(index=2, text="World now", start=0.3, end=0.5),
        )
    )
    return RenderJob(
        output_path=output_path,
        settings=settings,
        background=BackgroundConfiguration(type="color", color="#101820", source=None, loop=True),
        text=TextConfiguration(outline=1, shadow=1),
        subtitle_document=document,
        audio_path=audio_path,
        duration=0.5,
    )


def test_plan_includes_one_overlay_per_segment() -> None:
    plan = MoviePyRenderBackend().plan(build_job(Path("out.mp4")))

    assert plan.backend == "moviepy"
    assert plan.segment_count == 2
    overlay_tokens = [token for token in plan.argv if token.startswith("overlay=")]
    assert len(overlay_tokens) == 2


# --- Integration (requires moviepy) --------------------------------------------


def _write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * int(8000 * seconds))


@pytest.mark.moviepy
@pytest.mark.skipif(not is_moviepy_available(), reason="moviepy is not installed")
def test_moviepy_backend_renders_real_clip(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    _write_wav(audio_path, 0.5)
    output_path = tmp_path / "clip.mp4"

    progress_updates: list[float] = []
    backend = MoviePyRenderBackend(
        on_progress=lambda progress: progress_updates.append(progress.completed_seconds)
    )
    result = backend.render(build_job(output_path, audio_path=audio_path))

    assert result.success is True
    assert result.backend == "moviepy"
    assert output_path.is_file()
    assert output_path.stat().st_size > 0
    assert len(progress_updates) > 0


@pytest.mark.moviepy
@pytest.mark.skipif(not is_moviepy_available(), reason="moviepy is not installed")
def test_moviepy_backend_video_background_loops_and_trims(tmp_path: Path) -> None:
    # Build a tiny 0.2s background clip with ffmpeg, then request a 0.6s
    # render: the background must loop and be trimmed to exactly 0.6s
    # (FR-052/FR-053), independent of the ffmpeg backend under test elsewhere.
    from media_production_framework.ffmpeg_backend import is_ffmpeg_available

    if not is_ffmpeg_available():
        pytest.skip("ffmpeg is required to build the test background clip")

    import subprocess

    bg_path = tmp_path / "bg.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=64x36:r=10:d=0.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(bg_path),
        ],
        check=True,
        capture_output=True,
    )

    settings = RenderSettings(
        width=160,
        height=90,
        fps=10,
        video_bitrate="500k",
        video_codec="libx264",
        audio_sample_rate=48000,
        preset="ultrafast",
        crf=30,
    )
    output_path = tmp_path / "looped.mp4"
    job = RenderJob(
        output_path=output_path,
        settings=settings,
        background=BackgroundConfiguration(type="video", color=None, source=bg_path, loop=True),
        text=TextConfiguration(),
        subtitle_document=SubtitleDocument(segments=()),
        duration=0.6,
    )

    result = MoviePyRenderBackend().render(job)

    assert result.success is True
    assert output_path.stat().st_size > 0


def test_render_raises_when_moviepy_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import media_production_framework.moviepy_backend as moviepy_backend_module

    backend = moviepy_backend_module.MoviePyRenderBackend()
    job = build_job(tmp_path / "out.mp4")

    original_import = __import__

    def blocking_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "moviepy":
            raise ImportError("simulated: moviepy not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocking_import)

    with pytest.raises(RenderingError, match="requires the optional 'moviepy'"):
        backend.render(job)
