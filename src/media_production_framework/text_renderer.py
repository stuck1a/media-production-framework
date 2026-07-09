"""
Text Renderer.

Rasterizes the :class:`~media_production_framework.layout.SegmentLayout` output
of the Layout Engine into transparent RGBA overlay images (FR-036, FR-041,
FR-047), one per subtitle segment, ready for a compositor to paste onto the
background (Part 4).

This is the one module in the Rendering Engine that genuinely needs Pillow --
there is no meaningful "fake" rasterizer the way :mod:`layout` has
``FakeTextMeasurer``. Pillow itself is still an optional dependency (the
``render`` extra, see ADR-0002): the heavy import is deferred to render time so
this module remains importable without it installed, mirroring the lazy
Whisper imports in ``alignment.py``.

Effects (currently outline and shadow) are drawn as small, additive steps so a
future effect can be added without touching the existing ones (FR-048).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from media_production_framework.configuration import TextConfiguration
from media_production_framework.layout import SegmentLayout, TextBox

if TYPE_CHECKING:
    from PIL import Image

DEFAULT_OUTLINE_COLOR = (0, 0, 0, 255)
DEFAULT_SHADOW_COLOR = (0, 0, 0, 255)


class TextRenderingError(RuntimeError):
    """Raised when rasterizing subtitle text fails."""


class FontSource(Protocol):
    """A source that can load a Pillow font object at a given pixel size."""

    def load(self, size: int) -> Any:
        """Return a Pillow font object usable with ``ImageDraw.text``."""


@dataclass(frozen=True)
class TrueTypeFontFile:
    """A font source backed by a specific TrueType/OpenType file on disk."""

    path: Path

    def load(self, size: int) -> Any:
        """Load the font file at the given pixel size."""

        try:
            from PIL import ImageFont
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise TextRenderingError(
                "Text rendering requires the optional 'Pillow' dependency. "
                "Install it with: pip install media-production-framework[render]"
            ) from exc
        return ImageFont.truetype(str(self.path), size)


@dataclass(frozen=True)
class DefaultFontSource:
    """A font source backed by Pillow's bundled scalable default font.

    Requires no external font file, so it is used as the zero-configuration
    fallback and throughout the test suite for fully offline, deterministic
    rendering (mirroring the bundled-test-font requirement without adding a
    binary font asset to the repository).
    """

    def load(self, size: int) -> Any:
        """Load Pillow's bundled default font at the given pixel size."""

        try:
            from PIL import ImageFont
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise TextRenderingError(
                "Text rendering requires the optional 'Pillow' dependency. "
                "Install it with: pip install media-production-framework[render]"
            ) from exc
        return ImageFont.load_default(size=size)


@dataclass(frozen=True)
class FontFileSet:
    """Font sources for each style variant a segment may request.

    A missing ``bold``/``italic``/``bold_italic`` variant falls back to
    ``regular``; this module does not attempt synthetic bold/italic synthesis.
    """

    regular: FontSource
    bold: FontSource | None = None
    italic: FontSource | None = None
    bold_italic: FontSource | None = None

    def resolve(self, *, bold: bool, italic: bool) -> FontSource:
        """Return the font source matching the requested style, with fallback."""

        if bold and italic:
            return self.bold_italic or self.regular
        if bold:
            return self.bold or self.regular
        if italic:
            return self.italic or self.regular
        return self.regular


def default_font_set() -> FontFileSet:
    """Return a font set backed entirely by Pillow's bundled default font."""

    return FontFileSet(regular=DefaultFontSource())


@dataclass(frozen=True)
class TextOverlay:
    """A rasterized, transparent RGBA overlay for one subtitle segment."""

    segment_index: int
    image: Image.Image
    box: TextBox
    start: float
    end: float

    @property
    def size(self) -> tuple[int, int]:
        """Return the overlay image's ``(width, height)`` in pixels."""

        return self.image.size


def _hex_to_rgba(color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


def _line_offset(horizontal: str, block_width: int, line_width: int) -> int:
    if horizontal == "left":
        return 0
    if horizontal == "right":
        return block_width - line_width
    return (block_width - line_width) // 2  # center


class TextRenderer:
    """Rasterizes segment layouts into transparent text overlays."""

    def __init__(self, fonts: FontFileSet | None = None) -> None:
        self._fonts = fonts or default_font_set()

    def render(self, layout: SegmentLayout, text_config: TextConfiguration) -> TextOverlay:
        """Rasterize a single segment's layout into an RGBA overlay image."""

        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise TextRenderingError(
                "Text rendering requires the optional 'Pillow' dependency. "
                "Install it with: pip install media-production-framework[render]"
            ) from exc

        font_source = self._fonts.resolve(bold=text_config.bold, italic=text_config.italic)
        font = font_source.load(layout.font_size)

        outline = max(text_config.outline, 0)
        shadow = max(text_config.shadow, 0)

        measurer = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        line_sizes = [_measure_line(measurer, line, font) for line in layout.lines]
        block_width = max((width for width, _ in line_sizes), default=0)
        block_height = sum(height for _, height in line_sizes)

        pad_left = pad_top = outline
        pad_right = pad_bottom = outline + shadow
        canvas_width = max(block_width + pad_left + pad_right, 1)
        canvas_height = max(block_height + pad_top + pad_bottom, 1)

        image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        fill = _hex_to_rgba(text_config.color)

        y = pad_top
        for line, (line_width, line_height) in zip(layout.lines, line_sizes, strict=True):
            x = pad_left + _line_offset(text_config.horizontal, block_width, line_width)
            if shadow:
                _draw_shadow(draw, (x, y), line, font, shadow)
            _draw_outlined_text(draw, (x, y), line, font, fill, outline)
            y += line_height

        placement = TextBox(
            x=layout.box.x - pad_left,
            y=layout.box.y - pad_top,
            width=canvas_width,
            height=canvas_height,
        )
        return TextOverlay(
            segment_index=layout.segment_index,
            image=image,
            box=placement,
            start=layout.start,
            end=layout.end,
        )

    def render_document(
        self,
        layouts: Sequence[SegmentLayout],
        text_config: TextConfiguration,
    ) -> Mapping[int, TextOverlay]:
        """Rasterize every segment layout, keyed by segment index."""

        return {layout.segment_index: self.render(layout, text_config) for layout in layouts}


def _measure_line(draw: Any, text: str, font: Any) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font)
    return (right - left, bottom - top)


def _draw_shadow(draw: Any, position: tuple[int, int], text: str, font: Any, offset: int) -> None:
    x, y = position
    draw.text((x + offset, y + offset), text, font=font, fill=DEFAULT_SHADOW_COLOR)


def _draw_outlined_text(
    draw: Any,
    position: tuple[int, int],
    text: str,
    font: Any,
    fill: tuple[int, int, int, int],
    outline: int,
) -> None:
    if outline > 0:
        draw.text(
            position,
            text,
            font=font,
            fill=fill,
            stroke_width=outline,
            stroke_fill=DEFAULT_OUTLINE_COLOR,
        )
    else:
        draw.text(position, text, font=font, fill=fill)
