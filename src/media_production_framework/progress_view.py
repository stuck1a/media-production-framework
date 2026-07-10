"""
Render progress presentation.

A backend-agnostic consumer of the render progress events published by the
pipeline (:class:`RenderingProgressEvent`). Every render backend already
produces its own :class:`~media_production_framework.rendering.RenderProgress`
(the FFmpeg backend parses ``-progress``; the MoviePy backend bridges proglog),
so this view only has to *display* that shared data -- a progress bar, elapsed
time and an estimated time remaining -- without knowing which backend produced
it.

Elapsed time and ETA are wall-clock, presentation-side concerns and are computed
here rather than in a backend. The view degrades gracefully: without a known
total it shows elapsed time and processed seconds only, and when the output
stream is not a TTY it emits periodic plain log lines instead of an in-place bar.
"""

from __future__ import annotations

import sys
import time
from typing import TextIO

from media_production_framework.events import (
    EventBus,
    PreviewRenderingCompletedEvent,
    RenderingCompletedEvent,
    RenderingProgressEvent,
    RenderingStartedEvent,
)

_BAR_WIDTH = 28
# Cap redraws so a fast progress stream does not thrash the terminal.
_MIN_REDRAW_INTERVAL = 0.1
# Non-TTY output prints at most one line per this many seconds.
_NON_TTY_INTERVAL = 5.0


def _format_duration(seconds: float) -> str:
    """Format a duration as ``M:SS`` (or ``H:MM:SS`` past an hour)."""

    seconds = max(int(seconds), 0)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class RenderProgressView:
    """Display render progress from the event bus to a terminal stream."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stderr
        self._tty = bool(getattr(self._stream, "isatty", lambda: False)())
        self._start: float | None = None
        self._last_draw: float = 0.0
        self._backend: str = ""
        self._preview: bool = False
        self._active: bool = False
        self._line_open: bool = False

    def subscribe(self, event_bus: EventBus) -> None:
        """Register this view's handlers on ``event_bus``."""

        event_bus.subscribe(RenderingStartedEvent, self._on_started)
        event_bus.subscribe(RenderingProgressEvent, self._on_progress)
        event_bus.subscribe(RenderingCompletedEvent, self._on_completed)
        event_bus.subscribe(PreviewRenderingCompletedEvent, self._on_preview_completed)

    # -- event handlers --------------------------------------------------------

    def _on_started(self, event: RenderingStartedEvent) -> None:
        self._start = time.monotonic()
        self._last_draw = 0.0
        self._backend = event.backend
        self._preview = event.preview
        self._active = True
        label = "Rendering preview" if event.preview else "Rendering"
        self._write(f"{label} with '{event.backend}' backend...", newline=not self._tty)

    def _on_progress(self, event: RenderingProgressEvent) -> None:
        if not self._active or self._start is None:
            return

        now = time.monotonic()
        interval = _MIN_REDRAW_INTERVAL if self._tty else _NON_TTY_INTERVAL
        if event.fraction < 1.0 and (now - self._last_draw) < interval:
            return
        self._last_draw = now

        elapsed = now - self._start
        line = self._compose_line(event, elapsed)
        if self._tty:
            self._write("\r" + line, newline=False)
            self._line_open = True
        else:
            self._write(line, newline=True)

    def _on_completed(self, event: RenderingCompletedEvent) -> None:
        self._finish("Rendered" if event.success else "Render failed", event.output_path)

    def _on_preview_completed(self, event: PreviewRenderingCompletedEvent) -> None:
        self._finish("Rendered preview", event.output_path)

    # -- rendering helpers -----------------------------------------------------

    def _compose_line(self, event: RenderingProgressEvent, elapsed: float) -> str:
        elapsed_text = _format_duration(elapsed)
        if event.total_seconds and event.total_seconds > 0:
            fraction = min(max(event.fraction, 0.0), 1.0)
            filled = round(fraction * _BAR_WIDTH)
            bar = "#" * filled + "-" * (_BAR_WIDTH - filled)
            eta_text = (
                _format_duration(elapsed * (1.0 - fraction) / fraction)
                if fraction > 0
                else "--:--"
            )
            return (
                f"  [{bar}] {fraction * 100:5.1f}%  "
                f"elapsed {elapsed_text}  ETA {eta_text}"
            )
        # Total unknown: no percentage or ETA is meaningful.
        return f"  rendering... {event.completed_seconds:.1f}s encoded  elapsed {elapsed_text}"

    def _finish(self, verb: str, output_path: str) -> None:
        if not self._active:
            return
        self._active = False
        elapsed = time.monotonic() - self._start if self._start is not None else 0.0
        if self._tty and self._line_open:
            self._write("\r", newline=False)  # return to line start before overwrite
        suffix = f" -> {output_path}" if output_path else ""
        self._write(f"{verb} in {_format_duration(elapsed)}{suffix}", newline=True, clear=True)
        self._line_open = False

    def _write(self, text: str, *, newline: bool, clear: bool = False) -> None:
        try:
            if clear and self._tty:
                # Pad to clear any leftover characters from the progress bar.
                text = text.ljust(_BAR_WIDTH + 48)
            self._stream.write(text + ("\n" if newline else ""))
            self._stream.flush()
        except (OSError, ValueError):  # pragma: no cover - stream closed mid-render
            self._active = False
