from __future__ import annotations

from pathlib import Path

import pytest

from media_production_framework.configuration import (
    BackgroundConfiguration,
    ConfigurationError,
    ConfigurationLoader,
    FfmpegConfiguration,
    RenderConfiguration,
    TextConfiguration,
)
from media_production_framework.domain import SongMetadata
from media_production_framework.render_backends import (
    DryRunRenderBackend,
    RenderBackendFactory,
    RenderingError,
    RenderService,
)
from media_production_framework.rendering import (
    BackgroundOperation,
    RenderJob,
    RenderProgress,
    RenderSettings,
)
from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment


def load_config(tmp_path: Path, body: str) -> ConfigurationLoader:
    config_path = tmp_path / "project.yaml"
    config_path.write_text(body.strip() + "\n", encoding="utf-8")
    return ConfigurationLoader().load(config_path)


FULL_RENDERING = """
rendering:
  video:
    resolution: 1280x720
    fps: 25
    bitrate: 6M
  background:
    type: color
    source: "#112233"
  text:
    container:
      width: 70%
      padding_top: 4%
      padding_bottom: 6%
    font:
      name: Arial
      mode: auto
      size: 60
      max_lines: 2
      min_size: 30
      max_size: 90
    color: "#abcdef"
    bold: true
    outline: 3
    shadow: 1
    vertical: middle
    horizontal: left
  karaoke:
    enabled: true
    style: glow
ffmpeg:
  preset: fast
  crf: 20
  sample_rate: 44100
"""


# --- Rendering configuration parsing ------------------------------------------


def test_rendering_configuration_parses_full_section(tmp_path: Path) -> None:
    config = load_config(tmp_path, FULL_RENDERING)

    assert config.rendering is not None
    render = config.rendering

    assert render.video.resolution == (1280, 720)
    assert render.video.width == 1280
    assert render.video.height == 720
    assert render.video.fps == 25
    assert render.video.bitrate == "6M"
    assert render.video.codec == "libx264"

    assert render.background.type == "color"
    assert render.background.color == "#112233"
    assert render.background.source is None

    assert render.text.container.width == pytest.approx(0.7)
    assert render.text.container.padding_top == pytest.approx(0.04)
    assert render.text.container.padding_bottom == pytest.approx(0.06)

    assert render.text.font.name == "Arial"
    assert render.text.font.mode == "auto"
    assert render.text.font.size == 60
    assert render.text.font.max_lines == 2
    assert render.text.font.min_size == 30
    assert render.text.font.max_size == 90

    assert render.text.color == "#ABCDEF"
    assert render.text.bold is True
    assert render.text.italic is False
    assert render.text.outline == 3
    assert render.text.shadow == 1
    assert render.text.vertical == "middle"
    assert render.text.horizontal == "left"

    assert render.karaoke.enabled is True
    assert render.karaoke.style == "glow"

    assert config.ffmpeg.preset == "fast"
    assert config.ffmpeg.crf == 20
    assert config.ffmpeg.sample_rate == 44100


def test_rendering_absent_yields_none_and_default_ffmpeg(tmp_path: Path) -> None:
    config = load_config(tmp_path, "input:\n  audio: song.wav\n")

    assert config.rendering is None
    assert config.ffmpeg == FfmpegConfiguration()
    assert config.ffmpeg.preset == "medium"


def test_default_rendering_configuration_is_valid() -> None:
    render = RenderConfiguration()

    assert render.video.resolution == (1920, 1080)
    assert render.background.type == "color"
    assert render.text.font.mode == "auto"
    assert render.karaoke.enabled is False


def test_image_background_resolves_source_path(tmp_path: Path) -> None:
    body = """
rendering:
  background:
    type: image
    source: bg.png
    loop: false
"""
    config = load_config(tmp_path, body)

    assert config.rendering is not None
    background = config.rendering.background
    assert background.type == "image"
    assert background.color is None
    assert background.source == (tmp_path / "bg.png").resolve()
    assert background.loop is False


# --- Rendering configuration validation ---------------------------------------


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("rendering:\n  video:\n    resolution: 1920-1080\n", "rendering.video.resolution"),
        ('rendering:\n  video:\n    resolution: "0x100"\n', "positive"),
        ("rendering:\n  video:\n    fps: 0\n", "rendering.video.fps"),
        ("rendering:\n  video:\n    fps: true\n", "rendering.video.fps"),
        ("rendering:\n  video:\n    bitrate: ''\n", "rendering.video.bitrate"),
        ("rendering:\n  background:\n    type: hologram\n", "rendering.background.type"),
        ("rendering:\n  background:\n    type: image\n", "rendering.background.source"),
        ("rendering:\n  background:\n    type: color\n    source: red\n", "hex colour"),
        ("rendering:\n  text:\n    color: '#12345'\n", "rendering.text.color"),
        ("rendering:\n  text:\n    vertical: sideways\n", "rendering.text.vertical"),
        ("rendering:\n  text:\n    outline: -1\n", "rendering.text.outline"),
        ("rendering:\n  text:\n    container:\n      width: 80\n", "percentage"),
        (
            "rendering:\n  text:\n    container:\n      padding_top: 60%\n"
            "      padding_bottom: 60%\n",
            "less than 100%",
        ),
        ("rendering:\n  text:\n    font:\n      mode: elastic\n", "rendering.text.font.mode"),
        (
            "rendering:\n  text:\n    font:\n      min_size: 90\n      max_size: 40\n",
            "must not exceed",
        ),
        ("rendering:\n  karaoke:\n    style: disco\n", "rendering.karaoke.style"),
        ("ffmpeg:\n  crf: 60\n", "ffmpeg.crf"),
        ("ffmpeg:\n  preset: turbo\n", "ffmpeg.preset"),
        ("ffmpeg:\n  sample_rate: 0\n", "ffmpeg.sample_rate"),
    ],
)
def test_rendering_configuration_rejects_invalid_values(
    tmp_path: Path, body: str, match: str
) -> None:
    with pytest.raises(ConfigurationError, match=match):
        load_config(tmp_path, body)


# --- Render domain objects ----------------------------------------------------


def test_render_settings_from_config_flattens_values() -> None:
    settings = RenderSettings.from_config(RenderConfiguration(), FfmpegConfiguration())

    assert settings.width == 1920
    assert settings.height == 1080
    assert settings.resolution == (1920, 1080)
    assert settings.fps == 30
    assert settings.video_codec == "libx264"
    assert settings.audio_sample_rate == 48000
    assert settings.preset == "medium"
    assert settings.crf == 18


def test_background_operation_from_config_preserves_kind() -> None:
    operation = BackgroundOperation.from_config(
        BackgroundConfiguration(type="color", color="#010203", source=None, loop=True)
    )

    assert operation.kind == "color"
    assert operation.color == "#010203"
    assert operation.source is None


@pytest.mark.parametrize(
    ("completed", "total", "expected"),
    [(5.0, 10.0, 0.5), (5.0, None, 0.0), (20.0, 10.0, 1.0), (1.0, 0.0, 0.0)],
)
def test_render_progress_fraction(completed: float, total: float | None, expected: float) -> None:
    assert RenderProgress(completed, total).fraction == pytest.approx(expected)


# --- Dry-run backend ----------------------------------------------------------


def build_job(output_path: Path, *, preview: bool = False) -> RenderJob:
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(index=1, text="Hello", start=0.0, end=1.0),
            SubtitleSegment(index=2, text="World", start=1.0, end=2.0),
        ),
    )
    settings = RenderSettings(
        width=1920,
        height=1080,
        fps=30,
        video_bitrate="8M",
        video_codec="libx264",
        audio_sample_rate=48000,
        preset="medium",
        crf=18,
    )
    return RenderJob(
        output_path=output_path,
        settings=settings,
        background=BackgroundConfiguration(type="color", color="#000000", source=None, loop=True),
        text=TextConfiguration(),
        subtitle_document=document,
        audio_path=Path("song.wav"),
        metadata=SongMetadata(fields={"title": "My Song", "artist": None}),
        duration=12.0,
        preview=preview,
    )


def test_dry_run_backend_plans_expected_render() -> None:
    plan = DryRunRenderBackend().plan(build_job(Path("out.mp4")))

    assert plan.backend == "dry-run"
    assert plan.resolution == (1920, 1080)
    assert plan.fps == 30
    assert plan.duration == 12.0
    assert plan.segment_count == 2
    assert plan.background.kind == "color"
    assert plan.background.color == "#000000"
    assert plan.metadata == {"title": "My Song"}  # None-valued fields are dropped
    assert plan.argv[0] == "dry-run"
    assert "background=color:#000000" in plan.argv
    assert "segments=2" in plan.argv
    assert "meta:title=My Song" in plan.argv
    assert "out=out.mp4" in plan.argv
    assert "preview" not in plan.argv


def test_dry_run_backend_marks_preview() -> None:
    plan = DryRunRenderBackend().plan(build_job(Path("out.mp4"), preview=True))

    assert plan.preview is True
    assert "preview" in plan.argv


def test_dry_run_backend_render_writes_nothing(tmp_path: Path) -> None:
    output_path = tmp_path / "out.mp4"
    result = DryRunRenderBackend().render(build_job(output_path))

    assert result.success is True
    assert result.backend == "dry-run"
    assert result.output_path == output_path
    assert not output_path.exists()


def test_render_service_defaults_to_dry_run() -> None:
    service = RenderService()
    job = build_job(Path("out.mp4"))

    plan = service.plan(job)
    result = service.render(job)

    assert plan.backend == "dry-run"
    assert result.backend == "dry-run"
    assert result.success is True


def test_render_backend_factory_rejects_unknown_backend() -> None:
    with pytest.raises(RenderingError, match="Unknown rendering backend"):
        RenderBackendFactory().create("ffmpeg")
