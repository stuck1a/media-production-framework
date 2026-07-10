from __future__ import annotations

import wave
from pathlib import Path

import pytest

from media_production_framework.events import (
    PreviewRenderingCompletedEvent,
    RenderingCompletedEvent,
    RenderingStartedEvent,
)
from media_production_framework.ffmpeg_backend import is_ffmpeg_available
from media_production_framework.main import run_pipeline

RENDERING_BLOCK_TEMPLATE = """
rendering:
  enabled: {enabled}
  backend: {backend}
  video:
    resolution: 320x240
    fps: 10
  background:
    type: color
    source: "#102030"
ffmpeg:
  crf: 30
"""


def write_wav(path: Path, seconds: float, frame_rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(frame_rate)
        handle.writeframes(b"\x00\x00" * int(seconds * frame_rate))


def write_render_project(
    tmp_path: Path,
    *,
    output_video: str | None = "out.mp4",
    cover: bool = False,
    rendering: bool = True,
    backend: str = "dry-run",
    enabled: bool = True,
) -> Path:
    write_wav(tmp_path / "song.wav", 1.0)
    (tmp_path / "lyrics.txt").write_text("Hello world\nGoodbye now\n", encoding="utf-8")
    if cover:
        # a minimal PPM the config can point at; never actually read by dry-run.
        (tmp_path / "cover.png").write_bytes(b"\x89PNG\r\n")

    lines = ["input:", "  audio: song.wav", "  lyrics: lyrics.txt"]
    if cover:
        lines.append("  cover: cover.png")
    if output_video is not None:
        lines += ["output:", f"  video: {output_video}"]
    lines += [
        "subtitles:",
        "  enabled: true",
        "  provider: heuristic",
        "  file: subs.srt",
    ]
    body = "\n".join(lines)
    if rendering:
        block = RENDERING_BLOCK_TEMPLATE.strip().format(
            enabled=str(enabled).lower(), backend=backend
        )
        body += "\n" + block + "\n"

    config_path = tmp_path / "project.yaml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def events_of(context, event_type):  # type: ignore[no-untyped-def]
    return [event for event in context.event_bus.published_events if isinstance(event, event_type)]


# --- Dry-run end-to-end pipeline ----------------------------------------------


def test_pipeline_renders_with_dry_run_backend(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path)

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    result = context.artifacts["render_result"]
    assert result.success is True
    assert result.backend == "dry-run"
    assert context.artifacts["render_output_path"].endswith("out.mp4")
    assert events_of(context, RenderingStartedEvent)
    assert events_of(context, RenderingCompletedEvent)


def test_pipeline_render_plan_includes_metadata_and_lyrics(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path)

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    plan = context.artifacts["render_plan"]
    # The full multi-line lyrics text is embedded into the render metadata
    # (FR-059); the dry-run backend records it as a meta: token.
    assert any(token.startswith("meta:lyrics=") for token in plan.argv)
    assert plan.metadata.get("lyrics", "").startswith("Hello world")
    # Two lyric lines -> two subtitle segments -> two rendered overlays.
    assert plan.segment_count == 2


def test_pipeline_render_plan_includes_cover_when_configured(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path, cover=True)

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    plan = context.artifacts["render_plan"]
    assert any(token.startswith("cover=") for token in plan.argv)


# --- Skip behaviour -----------------------------------------------------------


def test_pipeline_skips_rendering_without_output_video(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path, output_video=None)

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    assert "render_result" not in context.artifacts
    assert not events_of(context, RenderingStartedEvent)


def test_pipeline_skips_rendering_without_rendering_section(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path, rendering=False)

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    assert "render_result" not in context.artifacts


def test_pipeline_skips_rendering_when_disabled(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path, enabled=False)

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    assert "render_result" not in context.artifacts


# --- Preview ------------------------------------------------------------------


def test_pipeline_preview_downscales_and_publishes_preview_event(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path)

    context = run_pipeline(
        configuration_path=config_path, log_level="CRITICAL", preview=True
    )

    result = context.artifacts["render_result"]
    assert result.preview is True
    assert result.output_path.name == "out_preview.mp4"
    plan = context.artifacts["render_plan"]
    # 320x240 downscaled to a max preview width of 640 stays 320x240 here; the
    # preview always renders at ultrafast for speed.
    assert plan.preset == "ultrafast"
    assert events_of(context, PreviewRenderingCompletedEvent)
    assert not events_of(context, RenderingCompletedEvent)


# --- Real end-to-end (M3 exit criterion) --------------------------------------


@pytest.mark.ffmpeg
@pytest.mark.skipif(not is_ffmpeg_available(), reason="ffmpeg binary is not installed")
def test_pipeline_generates_real_video_from_config(tmp_path: Path) -> None:
    config_path = write_render_project(tmp_path, backend="ffmpeg")

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    output_path = tmp_path / "out.mp4"
    assert output_path.is_file()
    assert output_path.stat().st_size > 0
    assert context.artifacts["render_result"].success is True
    assert context.artifacts["render_result"].backend == "ffmpeg"
