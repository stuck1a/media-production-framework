from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from media_production_framework.alignment import (
    AlignmentError,
    AlignmentProviderFactory,
    AlignmentRequest,
    AlignmentService,
    HeuristicAlignmentProvider,
    SubtitleBuilder,
    WordTiming,
)
from media_production_framework.audio import AudioError, get_audio_duration
from media_production_framework.configuration import ConfigurationLoader
from media_production_framework.domain import SongMetadata
from media_production_framework.events import PipelineStageCompletedEvent
from media_production_framework.lyrics import LyricsParser, tokenize
from media_production_framework.main import run_pipeline
from media_production_framework.metadata import MetadataError, MetadataParser
from media_production_framework.subtitle_export import JsonExporter, SrtExporter
from media_production_framework.subtitle_validation import (
    SubtitleValidationError,
    SubtitleValidator,
)
from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment, SubtitleWord
from media_production_framework.text_wrapping import wrap_text


def write_wav(path: Path, duration_seconds: float, frame_rate: int = 8000) -> None:
    frame_count = int(duration_seconds * frame_rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(frame_rate)
        handle.writeframes(b"\x00\x00" * frame_count)


def write_subtitle_project(tmp_path: Path, subtitles_extra: str = "") -> Path:
    audio_path = tmp_path / "song.wav"
    lyrics_path = tmp_path / "lyrics.txt"
    write_wav(audio_path, duration_seconds=4.0)
    lyrics_path.write_text("Hello world\nGoodbye now\n", encoding="utf-8")

    config_path = tmp_path / "project.yaml"
    config_path.write_text(
        f"""
input:
  audio: song.wav
  lyrics: lyrics.txt
subtitles:
  enabled: true
  file: output.srt
{subtitles_extra}
""".strip(),
        encoding="utf-8",
    )
    return config_path


# --- Lyrics parsing -----------------------------------------------------------


def test_tokenize_preserves_apostrophes() -> None:
    assert tokenize("don't stop believing") == ("don't", "stop", "believing")


def test_lyrics_parser_ignores_blank_lines() -> None:
    parsed = LyricsParser().parse("First line\n\n  \nSecond line\n")

    assert [line.text for line in parsed.lines] == ["First line", "Second line"]
    assert parsed.token_count == 4
    assert parsed.all_tokens == ("First", "line", "Second", "line")


# --- Text wrapping -------------------------------------------------------------


def test_wrap_text_does_not_split_words() -> None:
    lines = wrap_text("the quick brown fox jumps", max_line_length=10)

    assert all(len(line) <= 10 for line in lines)
    assert " ".join(lines) == "the quick brown fox jumps"


def test_wrap_text_disabled_returns_single_line() -> None:
    assert wrap_text("hello   world", max_line_length=0) == ("hello world",)


# --- Audio duration ------------------------------------------------------------


def test_get_audio_duration_reads_wav(tmp_path: Path) -> None:
    audio_path = tmp_path / "clip.wav"
    write_wav(audio_path, duration_seconds=2.5, frame_rate=8000)

    assert get_audio_duration(audio_path) == pytest.approx(2.5)


def test_get_audio_duration_rejects_non_wav(tmp_path: Path) -> None:
    audio_path = tmp_path / "clip.mp3"
    audio_path.write_bytes(b"not a real mp3")

    with pytest.raises(AudioError):
        get_audio_duration(audio_path)


# --- Metadata parsing ------------------------------------------------------------


def test_metadata_parser_reads_ffmetadata1() -> None:
    metadata = MetadataParser().parse(";FFMETADATA1\ntitle=My Song\nartist=Someone\n")

    assert metadata.title == "My Song"
    assert metadata.artist == "Someone"


def test_metadata_parser_rejects_missing_header() -> None:
    with pytest.raises(MetadataError):
        MetadataParser().parse("title=My Song\n")


# --- Heuristic alignment ---------------------------------------------------------


def test_heuristic_provider_distributes_timing_across_duration() -> None:
    parsed = LyricsParser().parse("Hello world")
    request = AlignmentRequest(
        audio_path=Path("unused.wav"),
        parsed_lyrics=parsed,
        raw_lyrics="Hello world",
        audio_duration=10.0,
    )

    timings = HeuristicAlignmentProvider().align(request)

    assert [timing.word for timing in timings] == ["Hello", "world"]
    assert timings[0].start == 0.0
    assert timings[-1].end == pytest.approx(10.0)
    assert timings[0].end <= timings[1].start + 1e-9


def test_heuristic_provider_requires_audio_duration() -> None:
    parsed = LyricsParser().parse("Hello world")
    request = AlignmentRequest(
        audio_path=Path("unused.wav"),
        parsed_lyrics=parsed,
        raw_lyrics="Hello world",
        audio_duration=None,
    )

    with pytest.raises(AlignmentError):
        HeuristicAlignmentProvider().align(request)


def test_alignment_provider_factory_rejects_unknown_provider() -> None:
    with pytest.raises(AlignmentError):
        AlignmentProviderFactory().create("does-not-exist")


# --- Subtitle building -----------------------------------------------------------


def test_subtitle_builder_maps_words_back_onto_lyric_lines() -> None:
    parsed = LyricsParser().parse("Hello world\nGoodbye now")
    timings = [
        WordTiming(word="Hello", start=0.0, end=1.0),
        WordTiming(word="world", start=1.0, end=2.0),
        WordTiming(word="Goodbye", start=2.0, end=3.0),
        WordTiming(word="now", start=3.0, end=4.0),
    ]

    document = SubtitleBuilder().build(parsed, timings, language="en", audio_duration=4.0)

    assert [segment.text for segment in document.segments] == ["Hello world", "Goodbye now"]
    assert document.segments[0].start == 0.0
    assert document.segments[0].end == 2.0
    assert document.segments[1].start == 2.0
    assert document.segments[1].end == 4.0
    assert len(document.segments[0].words) == 2


def test_subtitle_builder_raises_on_word_count_mismatch() -> None:
    parsed = LyricsParser().parse("Hello world")
    timings = [WordTiming(word="Hello", start=0.0, end=1.0)]

    with pytest.raises(AlignmentError):
        SubtitleBuilder().build(parsed, timings)


def test_alignment_service_end_to_end_with_heuristic_provider() -> None:
    parsed = LyricsParser().parse("Hello world")
    request = AlignmentRequest(
        audio_path=Path("unused.wav"),
        parsed_lyrics=parsed,
        raw_lyrics="Hello world",
        audio_duration=2.0,
    )

    document = AlignmentService().align(request, provider_name="heuristic")

    assert len(document.segments) == 1
    assert document.segments[0].text == "Hello world"


# --- Subtitle validation ----------------------------------------------------------


def test_subtitle_validator_accepts_well_formed_document() -> None:
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(index=1, text="Hello", start=0.0, end=1.0),
            SubtitleSegment(index=2, text="World", start=1.0, end=2.0),
        ),
        audio_duration=2.0,
    )

    SubtitleValidator().validate(document)  # must not raise


def test_subtitle_validator_rejects_overlapping_segments() -> None:
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(index=1, text="Hello", start=0.0, end=2.0),
            SubtitleSegment(index=2, text="World", start=1.0, end=3.0),
        ),
    )

    with pytest.raises(SubtitleValidationError, match="overlaps"):
        SubtitleValidator().validate(document)


def test_subtitle_validator_rejects_empty_text() -> None:
    document = SubtitleDocument(segments=(SubtitleSegment(index=1, text="  ", start=0.0, end=1.0),))

    with pytest.raises(SubtitleValidationError, match="empty"):
        SubtitleValidator().validate(document)


def test_subtitle_validator_rejects_word_outside_segment_bounds() -> None:
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(
                index=1,
                text="Hello world",
                start=0.0,
                end=1.0,
                words=(SubtitleWord(text="world", start=0.5, end=1.5),),
            ),
        ),
    )

    with pytest.raises(SubtitleValidationError, match="ends after"):
        SubtitleValidator().validate(document)


# --- Subtitle export ----------------------------------------------------------------


def test_srt_exporter_writes_expected_format(tmp_path: Path) -> None:
    document = SubtitleDocument(
        segments=(SubtitleSegment(index=1, text="Hello world", start=0.0, end=1.5),),
    )
    output_path = tmp_path / "out.srt"

    SrtExporter(max_line_length=100).export(document, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert content.startswith("1\n00:00:00,000 --> 00:00:01,500\nHello world\n")


def test_json_exporter_preserves_words_and_metadata(tmp_path: Path) -> None:
    document = SubtitleDocument(
        segments=(
            SubtitleSegment(
                index=1,
                text="Hello world",
                start=0.0,
                end=1.0,
                words=(SubtitleWord(text="Hello", start=0.0, end=0.5),),
            ),
        ),
        language="en",
        audio_duration=1.0,
        metadata=SongMetadata(fields={"title": "My Song"}),
    )
    output_path = tmp_path / "out.json"

    JsonExporter().export(document, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["language"] == "en"
    assert payload["metadata"] == {"title": "My Song"}
    assert payload["segments"][0]["words"][0]["text"] == "Hello"


# --- End-to-end pipeline integration ------------------------------------------------


def test_pipeline_generates_subtitles_with_heuristic_provider(tmp_path: Path) -> None:
    config_path = write_subtitle_project(tmp_path, subtitles_extra="  provider: heuristic\n")

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    assert context.subtitle_document is not None
    assert len(context.subtitle_document.segments) == 2

    srt_path = tmp_path / "output.srt"
    json_path = tmp_path / "output.json"
    assert srt_path.is_file()
    assert json_path.is_file()
    assert "Hello world" in srt_path.read_text(encoding="utf-8")

    stage_names = [
        event.stage_name
        for event in context.event_bus.published_events
        if isinstance(event, PipelineStageCompletedEvent)
    ]
    assert "subtitle-alignment" in stage_names
    assert "subtitle-export" in stage_names


def test_pipeline_skips_subtitle_alignment_when_disabled(tmp_path: Path) -> None:
    config_path = write_subtitle_project(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("enabled: true", "enabled: false"),
        encoding="utf-8",
    )

    context = run_pipeline(configuration_path=config_path, log_level="CRITICAL")

    assert context.subtitle_document is None
    assert not (tmp_path / "output.srt").exists()


def test_configuration_loader_parses_subtitles_section(tmp_path: Path) -> None:
    extra = "  provider: heuristic\n  max_line_length: 30\n"
    config_path = write_subtitle_project(tmp_path, subtitles_extra=extra)

    configuration = ConfigurationLoader().load(config_path)

    assert configuration.subtitles.enabled is True
    assert configuration.subtitles.provider == "heuristic"
    assert configuration.subtitles.max_line_length == 30
    assert configuration.subtitles.file == (tmp_path / "output.srt").resolve()
