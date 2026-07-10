"""
Layout Engine.

Deterministically computes, for each subtitle segment, the pixel-measured
wrapped lines, the automatically scaled font size and the text block's bounding
box in output-pixel space (FR-035 - FR-046). No rasterization or file I/O
happens here; concrete glyph measurement is delegated to a :class:`TextMeasurer`
so the layout algorithm stays a pure, deterministic function that is fully
testable without Pillow (see ADR-0002 and Part 3's rasterizer).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from media_production_framework.configuration import FontConfiguration, TextConfiguration
from media_production_framework.subtitles import SubtitleDocument


class LayoutError(RuntimeError):
    """Raised when text layout cannot be computed."""


class TextMeasurer(Protocol):
    """Interface for measuring the rendered pixel size of a line of text."""

    def measure(
        self, text: str, font: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        """Return the ``(width_px, height_px)`` of ``text`` rendered at ``size``."""


@dataclass(frozen=True)
class FakeTextMeasurer:
    """Deterministic, dependency-free measurer used by tests and as a fallback.

    Width and height are derived from character count and font size using fixed
    factors, with no font file involved, so results are perfectly reproducible.
    """

    char_width_factor: float = 0.6
    line_height_factor: float = 1.2
    bold_width_factor: float = 1.08

    def measure(
        self, text: str, font: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        factor = self.char_width_factor * (self.bold_width_factor if bold else 1.0)
        width = round(len(text) * size * factor)
        height = round(size * self.line_height_factor)
        return (width, height)


class PillowTextMeasurer:
    """Text measurer backed by real Pillow font metrics.

    Pillow is an optional dependency (the ``render`` extra) and is imported
    lazily so this module stays importable without it installed, mirroring the
    lazy Whisper imports in ``alignment.py``. ``font`` is treated as a path or a
    name Pillow/FreeType can resolve directly; family-name resolution and
    bold/italic font-file selection are the rasterizer's concern (Part 3), which
    also bundles a test font for deterministic, offline rendering tests.
    """

    def __init__(self, font_path: str | None = None) -> None:
        self._font_path = font_path
        self._font_cache: dict[tuple[str, int], Any] = {}

    def measure(
        self, text: str, font: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        try:
            from PIL import ImageFont
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise LayoutError(
                "Real text measurement requires the optional 'Pillow' dependency. "
                "Install it with: pip install media-production-framework[render]"
            ) from exc

        resolved = self._font_path or font
        cache_key = (resolved, size)
        loaded = self._font_cache.get(cache_key)
        if loaded is None:
            loaded = ImageFont.truetype(resolved, size)
            self._font_cache[cache_key] = loaded

        left, top, right, bottom = loaded.getbbox(text or " ")
        return (int(right - left), int(bottom - top))


@dataclass(frozen=True)
class TextBox:
    """A pixel-space bounding box, ``(x, y)`` being its top-left corner."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class SegmentLayout:
    """The computed layout for a single subtitle segment."""

    segment_index: int
    lines: Sequence[str]
    font_size: int
    box: TextBox
    start: float
    end: float


def wrap_text_by_width(
    text: str,
    measurer: TextMeasurer,
    font: str,
    size: int,
    max_width_px: int,
    *,
    bold: bool = False,
    italic: bool = False,
) -> Sequence[str]:
    """Wrap text into lines that fit ``max_width_px``, never splitting a word.

    A word that alone exceeds ``max_width_px`` is still placed on its own line
    rather than being split (FR-045), mirroring ``text_wrapping.wrap_text``'s
    character-based behaviour but measured in real pixels.
    """

    normalized = " ".join(text.split())
    if not normalized:
        return ("",)

    lines: list[str] = []
    current: list[str] = []

    for word in normalized.split(" "):
        candidate = " ".join([*current, word])
        width, _ = measurer.measure(candidate, font, size, bold=bold, italic=italic)
        if not current or width <= max_width_px:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return tuple(lines)


def _segment_fits(
    text: str,
    measurer: TextMeasurer,
    font_config: FontConfiguration,
    size: int,
    max_width_px: int,
    *,
    bold: bool,
    italic: bool,
) -> bool:
    lines = wrap_text_by_width(
        text, measurer, font_config.name, size, max_width_px, bold=bold, italic=italic
    )
    return len(lines) <= font_config.max_lines


def _search_font_size(
    texts: Sequence[str],
    measurer: TextMeasurer,
    font_config: FontConfiguration,
    max_width_px: int,
    *,
    bold: bool,
    italic: bool,
) -> int:
    """Binary-search the largest font size for which every segment fits.

    FR-039: the hardest-to-fit ("longest") segment governs the chosen size, so
    every segment is checked at each candidate size. If no size in
    ``[min_size, max_size]`` satisfies every segment, the result clamps to
    ``min_size`` (the caller then wraps best-effort, possibly exceeding
    ``max_lines``, per the Part 2 specification).
    """

    if not font_config.auto_mode:
        return font_config.size

    low, high = font_config.min_size, font_config.max_size
    best = low
    while low <= high:
        mid = (low + high) // 2
        if all(
            _segment_fits(text, measurer, font_config, mid, max_width_px, bold=bold, italic=italic)
            for text in texts
        ):
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


def _compute_box(
    block_width: int,
    block_height: int,
    *,
    container_width_px: int,
    padding_top_px: int,
    padding_bottom_px: int,
    available_height_px: int,
    video_width: int,
    video_height: int,
    horizontal: str,
    vertical: str,
) -> TextBox:
    container_x = (video_width - container_width_px) // 2

    if horizontal == "left":
        x = container_x
    elif horizontal == "right":
        x = container_x + container_width_px - block_width
    else:  # center
        x = container_x + (container_width_px - block_width) // 2

    if vertical == "top":
        y = padding_top_px
    elif vertical == "bottom":
        y = video_height - padding_bottom_px - block_height
    else:  # middle
        y = padding_top_px + (available_height_px - block_height) // 2

    return TextBox(x=x, y=y, width=block_width, height=block_height)


class LayoutEngine:
    """Compute deterministic segment layouts for a subtitle document."""

    def __init__(self, measurer: TextMeasurer | None = None) -> None:
        self._measurer = measurer or FakeTextMeasurer()

    def layout_document(
        self,
        document: SubtitleDocument,
        text_config: TextConfiguration,
        video_width: int,
        video_height: int,
    ) -> Sequence[SegmentLayout]:
        """Return the layout of every segment in ``document`` (FR-035 - FR-046)."""

        if not document.segments:
            return ()

        font_config = text_config.font
        container_width_px = round(text_config.container.width * video_width)
        padding_top_px = round(text_config.container.padding_top * video_height)
        padding_bottom_px = round(text_config.container.padding_bottom * video_height)
        available_height_px = max(video_height - padding_top_px - padding_bottom_px, 0)

        font_size = _search_font_size(
            [segment.text for segment in document.segments],
            self._measurer,
            font_config,
            container_width_px,
            bold=text_config.bold,
            italic=text_config.italic,
        )

        layouts: list[SegmentLayout] = []
        for segment in document.segments:
            lines = wrap_text_by_width(
                segment.text,
                self._measurer,
                font_config.name,
                font_size,
                container_width_px,
                bold=text_config.bold,
                italic=text_config.italic,
            )
            line_metrics = [
                self._measurer.measure(
                    line,
                    font_config.name,
                    font_size,
                    bold=text_config.bold,
                    italic=text_config.italic,
                )
                for line in lines
            ]
            block_width = max((width for width, _ in line_metrics), default=0)
            block_height = sum(height for _, height in line_metrics)
            box = _compute_box(
                block_width,
                block_height,
                container_width_px=container_width_px,
                padding_top_px=padding_top_px,
                padding_bottom_px=padding_bottom_px,
                available_height_px=available_height_px,
                video_width=video_width,
                video_height=video_height,
                horizontal=text_config.horizontal,
                vertical=text_config.vertical,
            )
            layouts.append(
                SegmentLayout(
                    segment_index=segment.index,
                    lines=lines,
                    font_size=font_size,
                    box=box,
                    start=segment.start,
                    end=segment.end,
                )
            )

        return tuple(layouts)
