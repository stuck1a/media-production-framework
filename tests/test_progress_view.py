from __future__ import annotations

import io

from media_production_framework.events import (
    EventBus,
    RenderingCompletedEvent,
    RenderingProgressEvent,
    RenderingStartedEvent,
)
from media_production_framework.progress_view import RenderProgressView, _format_duration


class _TtyStringIO(io.StringIO):
    """A StringIO that reports itself as a TTY so the in-place bar is exercised."""

    def isatty(self) -> bool:
        return True


def test_format_duration() -> None:
    assert _format_duration(0) == "0:00"
    assert _format_duration(75) == "1:15"
    assert _format_duration(3661) == "1:01:01"


def test_progress_view_renders_bar_percent_and_eta() -> None:
    stream = _TtyStringIO()
    bus = EventBus()
    RenderProgressView(stream=stream).subscribe(bus)

    bus.publish(RenderingStartedEvent(backend="ffmpeg", preview=False))
    bus.publish(RenderingProgressEvent(fraction=0.5, completed_seconds=5.0, total_seconds=10.0))
    bus.publish(
        RenderingCompletedEvent(backend="ffmpeg", output_path="out.mp4", success=True)
    )

    output = stream.getvalue()
    assert "ffmpeg" in output
    assert "50.0%" in output
    assert "ETA" in output
    assert "#" in output  # progress bar filled portion
    assert "Rendered in" in output
    assert "out.mp4" in output


def test_progress_view_without_total_shows_elapsed_only() -> None:
    stream = _TtyStringIO()
    bus = EventBus()
    RenderProgressView(stream=stream).subscribe(bus)

    bus.publish(RenderingStartedEvent(backend="moviepy"))
    bus.publish(RenderingProgressEvent(fraction=0.0, completed_seconds=3.0, total_seconds=None))

    output = stream.getvalue()
    assert "%" not in output.split("Rendering")[-1]  # no percentage without a total
    assert "encoded" in output


def test_progress_view_non_tty_uses_plain_lines() -> None:
    stream = io.StringIO()  # not a TTY
    bus = EventBus()
    RenderProgressView(stream=stream).subscribe(bus)

    bus.publish(RenderingStartedEvent(backend="ffmpeg"))
    bus.publish(RenderingProgressEvent(fraction=1.0, completed_seconds=10.0, total_seconds=10.0))
    bus.publish(RenderingCompletedEvent(backend="ffmpeg", output_path="out.mp4", success=True))

    output = stream.getvalue()
    assert "\r" not in output  # no carriage-return redraws on a non-TTY stream
    assert "100.0%" in output
