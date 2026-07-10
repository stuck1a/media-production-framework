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

import logging
import os
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from media_production_framework.configuration import FontConfiguration, TextConfiguration
from media_production_framework.layout import SegmentLayout, TextBox

if TYPE_CHECKING:
    from PIL import Image

_LOGGER = logging.getLogger(__name__)

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


# --- Font-name resolution -----------------------------------------------------
#
# The configured ``font.name`` is a family name (e.g. "Mistral"), but Pillow can
# only load a font from a file path. This resolver locates the matching file in
# the operating system's font directories -- without any third-party dependency
# -- and classifies bold/italic variants, so the user's font (and its full glyph
# coverage, e.g. German umlauts) is actually used instead of the bundled
# fallback. When no match is found it warns and returns the bundled font.

_FONT_FILE_SUFFIXES = (".ttf", ".otf", ".ttc")

# Generic families with no single backing file: these intentionally map to the
# bundled font, and do so silently (they are the zero-configuration defaults).
_GENERIC_FONT_NAMES = frozenset({"", "sans", "sans-serif", "serif", "monospace", "default"})

# Cache of ``(family_index, stem_index)`` built once per process; scanning the
# system font directories is comparatively expensive.
_font_index: tuple[dict[str, dict[str, Path]], dict[str, dict[str, Path]]] | None = None


def _system_font_directories() -> list[Path]:
    """Return the existing OS font directories to search, most-specific first."""

    directories: list[Path] = []
    if sys.platform.startswith("win"):
        windir = os.environ.get("WINDIR", r"C:\Windows")
        directories.append(Path(windir) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            directories.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        home = Path.home()
        directories += [
            home / "Library" / "Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        ]
    else:
        home = Path.home()
        directories += [
            home / ".fonts",
            home / ".local" / "share" / "fonts",
            Path("/usr/local/share/fonts"),
            Path("/usr/share/fonts"),
        ]
    return [directory for directory in directories if directory.is_dir()]


def _style_key(subfamily: str) -> str:
    """Map a font subfamily name to a ``regular``/``bold``/``italic`` key."""

    lowered = subfamily.lower()
    bold = "bold" in lowered
    italic = "italic" in lowered or "oblique" in lowered
    if bold and italic:
        return "bold_italic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"


def _iter_font_files() -> Iterator[Path]:
    for directory in _system_font_directories():
        for suffix in _FONT_FILE_SUFFIXES:
            yield from directory.rglob(f"*{suffix}")


def _build_font_index() -> tuple[dict[str, dict[str, Path]], dict[str, dict[str, Path]]]:
    """Index installed fonts by family name and by filename stem.

    The first font file seen for a given ``(family, style)`` wins, so the
    most-specific directory (searched first) takes precedence over system-wide
    installations.
    """

    from PIL import ImageFont

    by_family: dict[str, dict[str, Path]] = {}
    by_stem: dict[str, dict[str, Path]] = {}
    for path in _iter_font_files():
        try:
            family, subfamily = ImageFont.truetype(str(path), 10).getname()
        except (OSError, ValueError):
            continue
        style = _style_key(subfamily or "")
        by_family.setdefault((family or "").strip().lower(), {}).setdefault(style, path)
        by_stem.setdefault(path.stem.strip().lower(), {}).setdefault(style, path)
    return by_family, by_stem


def _font_variants(name: str) -> dict[str, Path] | None:
    """Return the style->path variants for a family/stem name, or ``None``."""

    global _font_index
    if _font_index is None:
        _font_index = _build_font_index()
    by_family, by_stem = _font_index
    key = name.strip().lower()
    return by_family.get(key) or by_stem.get(key)


def resolve_font_set(
    font_config: FontConfiguration,
    *,
    logger: logging.Logger | None = None,
) -> FontFileSet:
    """Resolve ``font_config.name`` to a :class:`FontFileSet` of real font files.

    Resolution order: an explicit font-file path; then a generic family name
    (mapped silently to the bundled font); then an installed family/file matched
    in the OS font directories. When nothing matches, a warning is logged and
    the bundled default font is returned so rendering still succeeds.
    """

    log = logger or _LOGGER
    name = (font_config.name or "").strip()

    candidate = Path(name).expanduser()
    if name.lower().endswith(_FONT_FILE_SUFFIXES) and candidate.is_file():
        return FontFileSet(regular=TrueTypeFontFile(candidate))

    if name.lower() in _GENERIC_FONT_NAMES:
        return default_font_set()

    try:
        variants = _font_variants(name)
    except Exception:  # pragma: no cover - font scanning must never crash a render
        log.exception("Font resolution failed while scanning system fonts for %r.", name)
        variants = None

    if not variants:
        log.warning(
            "Font %r could not be located in the system font directories; falling "
            "back to the bundled default font. Non-Latin glyphs (e.g. umlauts) may "
            "render as missing-glyph boxes. Set 'rendering.text.font.name' to an "
            "installed font family or a font-file path.",
            name,
        )
        return default_font_set()

    regular = variants.get("regular") or next(iter(variants.values()))

    def variant(style: str) -> FontSource | None:
        path = variants.get(style)
        return TrueTypeFontFile(path) if path is not None else None

    return FontFileSet(
        regular=TrueTypeFontFile(regular),
        bold=variant("bold"),
        italic=variant("italic"),
        bold_italic=variant("bold_italic"),
    )


@dataclass(frozen=True)
class FontSourceMeasurer:
    """A :class:`~media_production_framework.layout.TextMeasurer` that measures
    with a render backend's own fonts.

    Using the same :class:`FontFileSet` for both the Layout Engine's sizing
    pass and the actual rasterization keeps line breaks consistent with what
    is drawn, avoiding overflow from a mismatched metrics source. Shared by
    every backend that renders real text (FFmpeg, MoviePy).
    """

    fonts: FontFileSet

    def measure(
        self, text: str, font: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        from PIL import Image, ImageDraw

        loaded = self.fonts.resolve(bold=bold, italic=italic).load(size)
        draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=loaded)
        return (int(right - left), int(bottom - top))


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
        # Measure each line *including* the outline stroke, and keep the bbox
        # origin. The font's internal top bearing means the ink does not start at
        # the drawing origin; drawing each line offset by its own bbox origin
        # makes the ink sit flush at the top-left of its row, so the last line's
        # descenders and outline can no longer overflow the canvas (the previous
        # code allocated `bottom - top` but drew from the ascender line, cropping
        # the final line by the top bearing).
        line_boxes = [_line_box(measurer, line, font, outline) for line in layout.lines]
        line_widths = [right - left for left, _, right, _ in line_boxes]
        line_heights = [bottom - top for _, top, _, bottom in line_boxes]
        block_width = max(line_widths, default=0)
        block_height = sum(line_heights)

        # A stroke of width `outline` grows the bbox by exactly `outline` on every
        # side, so it is already inside each line box; the drop shadow only
        # extends the canvas down and to the right by `shadow` px.
        canvas_width = max(block_width + shadow, 1)
        canvas_height = max(block_height + shadow, 1)

        image = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        fill = _hex_to_rgba(text_config.color)

        y = 0
        for line, (left, top, _, _), line_width, line_height in zip(
            layout.lines, line_boxes, line_widths, line_heights, strict=True
        ):
            x = _line_offset(text_config.horizontal, block_width, line_width)
            origin = (x - left, y - top)
            if shadow:
                _draw_shadow(draw, origin, line, font, shadow)
            _draw_outlined_text(draw, origin, line, font, fill, outline)
            y += line_height

        placement = TextBox(
            x=layout.box.x - outline,
            y=layout.box.y - outline,
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


def _line_box(draw: Any, text: str, font: Any, stroke: int) -> tuple[int, int, int, int]:
    """Return the integer stroked bounding box ``(left, top, right, bottom)``."""

    left, top, right, bottom = draw.textbbox((0, 0), text or " ", font=font, stroke_width=stroke)
    return (int(left), int(top), int(right), int(bottom))


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
