from __future__ import annotations

import wave
from pathlib import Path

import pytest

from media_production_framework.configuration import BackgroundConfiguration, TextConfiguration
from media_production_framework.ffmpeg_backend import (
    DEFAULT_AUDIO_CODEC,
    FfmpegCommandBuilder,
    FfmpegProgressParser,
    FfmpegRenderBackend,
    OverlaySpec,
    is_ffmpeg_available,
    resolve_ffmpeg_binary,
    write_ffmetadata,
)
from media_production_framework.render_backends import RenderBackendFactory, RenderingError
from media_production_framework.rendering import (
    BackgroundOperation,
    RenderJob,
    RenderPlan,
    RenderSettings,
)
from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment

MISSING_BINARY = "definitely-not-a-real-ffmpeg-binary-xyz"


def make_plan(
    background: BackgroundOperation,
    *,
    duration: float | None = 1.0,
    output: str = "out.mp4",
) -> RenderPlan:
    return RenderPlan(
        backend="ffmpeg",
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


# --- Command builder: backgrounds ---------------------------------------------


def test_color_background_command_without_audio_or_overlays() -> None:
    plan = make_plan(color_bg("#112233"))
    command = FfmpegCommandBuilder().build(plan, [], None, ffmpeg_binary="ffmpeg")

    assert command[:2] == ["ffmpeg", "-y"]
    assert "-f" in command and "lavfi" in command
    color_spec = command[command.index("lavfi") + 2]
    assert color_spec == "color=c=0x112233:s=1920x1080:r=30:d=1.000"

    graph = command[command.index("-filter_complex") + 1]
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in graph
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2" in graph
    assert graph.endswith("[bg]")

    assert command[command.index("-map") + 1] == "[bg]"
    assert command[-1] == "out.mp4"
    assert "-t" in command and command[command.index("-t") + 1] == "1.000"
    assert command[command.index("-progress") + 1] == "pipe:1"
    # No audio mapping without an audio input.
    assert f"{DEFAULT_AUDIO_CODEC}" not in command


def test_encoder_settings_are_applied() -> None:
    plan = make_plan(color_bg())
    command = FfmpegCommandBuilder().build(plan, [], None)

    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-preset") + 1] == "medium"
    assert command[command.index("-crf") + 1] == "18"
    assert command[command.index("-b:v") + 1] == "8M"
    assert command[command.index("-pix_fmt") + 1] == "yuv420p"
    assert command[command.index("-r") + 1] == "30"


def test_image_background_uses_loop_flag() -> None:
    background = BackgroundOperation(kind="image", source=Path("bg.png"), loop=False)
    command = FfmpegCommandBuilder().build(make_plan(background), [], None)

    assert "-loop" in command
    assert command[command.index("-loop") + 1] == "1"
    assert command[command.index("-i") + 1] == "bg.png"


def test_video_background_loops_and_trims_to_duration() -> None:
    background = BackgroundOperation(kind="video", source=Path("clip.mp4"), loop=True)
    command = FfmpegCommandBuilder().build(make_plan(background, duration=2.5), [], None)

    assert "-stream_loop" in command
    assert command[command.index("-stream_loop") + 1] == "-1"
    assert command[command.index("-t") + 1] == "2.500"


def test_video_background_without_loop_omits_stream_loop() -> None:
    background = BackgroundOperation(kind="video", source=Path("clip.mp4"), loop=False)
    command = FfmpegCommandBuilder().build(make_plan(background), [], None)

    assert "-stream_loop" not in command
    assert command[command.index("-i") + 1] == "clip.mp4"


def test_color_background_without_duration_and_no_audio_has_no_trim() -> None:
    plan = make_plan(color_bg(), duration=None)
    command = FfmpegCommandBuilder().build(plan, [], None)

    assert "-t" not in command
    assert "-shortest" not in command


# --- Command builder: audio ---------------------------------------------------


def test_audio_is_mapped_and_encoded() -> None:
    plan = make_plan(color_bg())
    command = FfmpegCommandBuilder().build(plan, [], Path("song.wav"))

    # Background is input 0; audio is input 1.
    assert command[command.index("-map") + 1] == "[bg]"
    assert "1:a" in command
    assert command[command.index("-c:a") + 1] == DEFAULT_AUDIO_CODEC
    assert command[command.index("-ar") + 1] == "48000"


def test_no_duration_with_audio_uses_shortest() -> None:
    plan = make_plan(color_bg(), duration=None)
    command = FfmpegCommandBuilder().build(plan, [], Path("song.wav"))

    assert "-shortest" in command
    assert "-t" not in command


# --- Command builder: overlays ------------------------------------------------


def test_overlay_chain_and_enable_expression_without_audio() -> None:
    plan = make_plan(color_bg())
    overlays = [
        OverlaySpec(path=Path("o1.png"), x=10, y=20, start=0.0, end=1.5),
        OverlaySpec(path=Path("o2.png"), x=30, y=40, start=1.5, end=3.0),
    ]
    command = FfmpegCommandBuilder().build(plan, overlays, None)

    # Overlays are inputs 1 and 2 (background is 0, no audio).
    graph = command[command.index("-filter_complex") + 1]
    assert "[bg][1:v]overlay=x=10:y=20:enable='between(t,0.000,1.500)'[v0]" in graph
    assert "[v0][2:v]overlay=x=30:y=40:enable='between(t,1.500,3.000)'[v1]" in graph
    assert command[command.index("-map") + 1] == "[v1]"


def test_overlay_indices_account_for_audio_input() -> None:
    plan = make_plan(color_bg())
    overlays = [OverlaySpec(path=Path("o1.png"), x=5, y=6, start=0.0, end=1.0)]
    command = FfmpegCommandBuilder().build(plan, overlays, Path("song.wav"))

    # Background is 0, audio is 1, so the overlay is input 2.
    graph = command[command.index("-filter_complex") + 1]
    assert "[bg][2:v]overlay=x=5:y=6" in graph


# --- Command builder: metadata + cover (FR-057/FR-058) ------------------------


def test_metadata_input_is_mapped() -> None:
    plan = make_plan(color_bg())
    command = FfmpegCommandBuilder().build(plan, [], None, metadata_path=Path("meta.ffmeta"))

    # The lavfi background is input 0, so the metadata file is input 1.
    assert "meta.ffmeta" in command
    assert command[command.index("-map_metadata") + 1] == "1"


def test_cover_is_mapped_as_attached_picture() -> None:
    plan = make_plan(color_bg())
    command = FfmpegCommandBuilder().build(plan, [], None, cover_path=Path("cover.png"))

    assert "cover.png" in command
    assert "1:v" in command  # cover is input 1, mapped as a video stream
    assert command[command.index("-c:v:1") + 1] == "mjpeg"
    assert command[command.index("-disposition:v:1") + 1] == "attached_pic"


def test_metadata_and_cover_indices_with_audio_and_overlays() -> None:
    plan = make_plan(color_bg())
    overlays = [OverlaySpec(path=Path("o1.png"), x=1, y=2, start=0.0, end=1.0)]
    command = FfmpegCommandBuilder().build(
        plan,
        overlays,
        Path("song.wav"),
        metadata_path=Path("meta.ffmeta"),
        cover_path=Path("cover.png"),
    )

    # Inputs: bg=0, audio=1, overlay=2, metadata=3, cover=4.
    assert command[command.index("-map_metadata") + 1] == "3"
    assert "4:v" in command
    graph = command[command.index("-filter_complex") + 1]
    assert "[bg][2:v]overlay=x=1:y=2" in graph


# --- FFMETADATA writer (FR-057/FR-059) ----------------------------------------


def test_write_ffmetadata_starts_with_header_and_writes_fields(tmp_path: Path) -> None:
    path = tmp_path / "meta.ffmeta"
    write_ffmetadata({"title": "Song", "artist": "Someone"}, path)

    content = path.read_text(encoding="utf-8")
    assert content.startswith(";FFMETADATA1\n")
    assert "title=Song" in content
    assert "artist=Someone" in content


def test_write_ffmetadata_escapes_special_characters(tmp_path: Path) -> None:
    path = tmp_path / "meta.ffmeta"
    write_ffmetadata({"lyrics": "line one\nline; two = end"}, path)

    content = path.read_text(encoding="utf-8")
    # newline, ';' and '=' inside the value must be backslash-escaped so the
    # multi-line lyrics round-trip through the container (FR-059).
    assert "line one\\\nline\\; two \\= end" in content


# --- Progress parser ----------------------------------------------------------


def test_progress_parser_reads_out_time_us() -> None:
    parser = FfmpegProgressParser(total_seconds=2.0)

    progress = parser.feed("out_time_us=500000")

    assert progress is not None
    assert progress.completed_seconds == pytest.approx(0.5)
    assert progress.fraction == pytest.approx(0.25)


def test_progress_parser_ignores_other_and_na_lines() -> None:
    parser = FfmpegProgressParser(total_seconds=2.0)

    assert parser.feed("frame=10") is None
    assert parser.feed("progress=continue") is None
    assert parser.feed("out_time_us=N/A") is None
    assert parser.feed("no-equals-sign") is None


def test_progress_parser_across_a_sample_block() -> None:
    sample = """frame=10
fps=25.0
bitrate=  84.0kbits/s
total_size=1024
out_time_us=1000000
out_time=00:00:01.000000
speed=2.5x
progress=continue""".splitlines()
    parser = FfmpegProgressParser(total_seconds=4.0)

    updates = [parser.feed(line.strip()) for line in sample]
    non_null = [update for update in updates if update is not None]

    assert len(non_null) == 1
    assert non_null[0].completed_seconds == pytest.approx(1.0)
    assert non_null[0].fraction == pytest.approx(0.25)


# --- Binary resolution --------------------------------------------------------


def test_resolve_ffmpeg_binary_raises_when_missing() -> None:
    with pytest.raises(RenderingError, match="was not found"):
        resolve_ffmpeg_binary(MISSING_BINARY)


def test_is_ffmpeg_available_false_for_missing_binary() -> None:
    assert is_ffmpeg_available(MISSING_BINARY) is False


# --- Backend / factory --------------------------------------------------------


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
        segments=(SubtitleSegment(index=1, text="Hello", start=0.0, end=0.5),)
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


def test_factory_creates_ffmpeg_backend() -> None:
    backend = RenderBackendFactory().create("ffmpeg")

    assert isinstance(backend, FfmpegRenderBackend)
    assert backend.name == "ffmpeg"


def test_plan_includes_one_overlay_input_per_segment() -> None:
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(index=1, text="Hello", start=0.0, end=0.5),
            SubtitleSegment(index=2, text="World", start=0.5, end=1.0),
        )
    )
    settings = RenderSettings(
        width=640,
        height=360,
        fps=24,
        video_bitrate="2M",
        video_codec="libx264",
        audio_sample_rate=44100,
        preset="fast",
        crf=20,
    )
    job = RenderJob(
        output_path=Path("out.mp4"),
        settings=settings,
        background=BackgroundConfiguration(type="color", color="#000000", source=None, loop=True),
        text=TextConfiguration(),
        subtitle_document=document,
        duration=1.0,
    )

    plan = FfmpegRenderBackend().plan(job)

    assert plan.backend == "ffmpeg"
    assert plan.segment_count == 2
    graph = plan.argv[plan.argv.index("-filter_complex") + 1]
    assert "[v0]" in graph and "[v1]" in graph


def test_render_raises_when_binary_missing(tmp_path: Path) -> None:
    backend = FfmpegRenderBackend(ffmpeg_binary=MISSING_BINARY)

    with pytest.raises(RenderingError, match="was not found"):
        backend.render(build_job(tmp_path / "out.mp4"))


# --- Integration (requires ffmpeg) --------------------------------------------


def _write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * int(8000 * seconds))


@pytest.mark.ffmpeg
@pytest.mark.skipif(not is_ffmpeg_available(), reason="ffmpeg binary is not installed")
def test_ffmpeg_backend_renders_real_clip(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    _write_wav(audio_path, 0.5)
    output_path = tmp_path / "clip.mp4"

    progress_updates: list[float] = []
    backend = FfmpegRenderBackend(
        on_progress=lambda progress: progress_updates.append(progress.completed_seconds)
    )
    result = backend.render(build_job(output_path, audio_path=audio_path))

    assert result.success is True
    assert result.backend == "ffmpeg"
    assert output_path.is_file()
    assert output_path.stat().st_size > 0
