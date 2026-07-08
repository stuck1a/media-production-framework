from __future__ import annotations

from pathlib import Path

import pytest

from media_production_framework.configuration import ConfigurationLoader
from media_production_framework.events import (
    Event,
    EventBus,
    PipelineCompletedEvent,
    PipelineStageCompletedEvent,
)
from media_production_framework.main import main, run_pipeline
from media_production_framework.projects import ProjectLoader, ProjectValidationError
from media_production_framework.providers import (
    ProviderDescriptor,
    ProviderRegistrationError,
    ProviderRegistry,
)


def write_project(tmp_path: Path) -> Path:
    audio_path = tmp_path / "song.wav"
    lyrics_path = tmp_path / "lyrics.txt"
    metadata_path = tmp_path / "metadata.txt"

    audio_path.write_bytes(b"audio")
    lyrics_path.write_text("First line\n\nSecond line\n", encoding="utf-8")
    metadata_path.write_text("; metadata\n", encoding="utf-8")

    config_path = tmp_path / "project.yaml"
    config_path.write_text(
        """
input:
  audio: song.wav
  lyrics: lyrics.txt
  metadata: metadata.txt
output:
  video: output.mp4
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_configuration_loader_resolves_project_relative_paths(tmp_path: Path) -> None:
    config_path = write_project(tmp_path)

    configuration = ConfigurationLoader().load(config_path)

    assert configuration.project_root == tmp_path.resolve()
    assert configuration.input.audio == (tmp_path / "song.wav").resolve()
    assert configuration.input.lyrics == (tmp_path / "lyrics.txt").resolve()
    assert configuration.output.video == (tmp_path / "output.mp4").resolve()


def test_project_loader_loads_assets_and_lyrics(tmp_path: Path) -> None:
    configuration = ConfigurationLoader().load(write_project(tmp_path))

    project = ProjectLoader().load(configuration)

    assert project.assets.audio is not None
    assert project.assets.lyrics is not None
    assert project.assets.lyrics.lines == ("First line", "Second line")
    assert project.assets.metadata is not None


def test_project_loader_reports_missing_required_assets(tmp_path: Path) -> None:
    configuration = ConfigurationLoader.empty(tmp_path)

    with pytest.raises(ProjectValidationError, match="input.audio"):
        ProjectLoader().load(configuration)


def test_event_bus_records_and_dispatches_events() -> None:
    received: list[Event] = []
    bus = EventBus()
    bus.subscribe(Event, received.append)

    event = PipelineCompletedEvent()
    bus.publish(event)

    assert bus.published_events == [event]
    assert received == [event]


def test_provider_registry_registers_and_queries_capabilities() -> None:
    registry = ProviderRegistry()
    registry.register(ProviderDescriptor(name="placeholder", capabilities=("pipeline",)))

    assert registry.get("placeholder").name == "placeholder"
    assert registry.find_by_capability("pipeline")[0].name == "placeholder"

    with pytest.raises(ProviderRegistrationError):
        registry.register(ProviderDescriptor(name="placeholder"))


def test_core_pipeline_executes_all_m1_stages(tmp_path: Path) -> None:
    context = run_pipeline(configuration_path=write_project(tmp_path), log_level="CRITICAL")

    stage_events = [
        event
        for event in context.event_bus.published_events
        if isinstance(event, PipelineStageCompletedEvent)
    ]

    assert [event.stage_name for event in stage_events] == [
        "configuration",
        "project-loading",
        "provider-initialization",
        "placeholder-processing",
    ]
    assert context.project is not None
    assert context.artifacts["placeholder_processing_completed"] is True


def test_cli_executes_core_pipeline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--config", str(write_project(tmp_path)), "--log-level", "CRITICAL"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "pipeline completed (4 stages)" in captured.out
