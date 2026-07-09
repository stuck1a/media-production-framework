from __future__ import annotations

from pathlib import Path

import pytest

from media_production_framework.configuration import TextConfiguration
from media_production_framework.layout import SegmentLayout, TextBox
from media_production_framework.text_renderer import (
    DefaultFontSource,
    FontFileSet,
    TextRenderer,
    TrueTypeFontFile,
    default_font_set,
)


def layout_for(*lines: str, font_size: int = 32, box: TextBox | None = None) -> SegmentLayout:
    return SegmentLayout(
        segment_index=1,
        lines=lines,
        font_size=font_size,
        box=box or TextBox(x=100, y=200, width=300, height=100),
        start=1.0,
        end=2.0,
    )


def text_config(
    *, outline: int = 0, shadow: int = 0, horizontal: str = "center", **overrides
) -> TextConfiguration:
    return TextConfiguration(outline=outline, shadow=shadow, horizontal=horizontal, **overrides)


# --- FontFileSet resolution (pure logic, no Pillow needed) --------------------


def test_font_file_set_resolves_regular_by_default() -> None:
    regular = DefaultFontSource()
    fonts = FontFileSet(regular=regular)

    assert fonts.resolve(bold=False, italic=False) is regular
    assert fonts.resolve(bold=True, italic=False) is regular  # falls back
    assert fonts.resolve(bold=False, italic=True) is regular  # falls back
    assert fonts.resolve(bold=True, italic=True) is regular  # falls back


def test_font_file_set_prefers_specific_variants_when_present() -> None:
    regular = DefaultFontSource()
    bold = TrueTypeFontFile(Path("bold.ttf"))
    italic = TrueTypeFontFile(Path("italic.ttf"))
    bold_italic = TrueTypeFontFile(Path("bold_italic.ttf"))
    fonts = FontFileSet(regular=regular, bold=bold, italic=italic, bold_italic=bold_italic)

    assert fonts.resolve(bold=True, italic=False) is bold
    assert fonts.resolve(bold=False, italic=True) is italic
    assert fonts.resolve(bold=True, italic=True) is bold_italic
    assert fonts.resolve(bold=False, italic=False) is regular


def test_default_font_set_uses_bundled_font() -> None:
    fonts = default_font_set()

    assert isinstance(fonts.regular, DefaultFontSource)
    assert fonts.bold is None


# --- Rasterization (Pillow's bundled font -> fully offline & deterministic) ---


def test_overlay_is_transparent_rgba_with_nontransparent_text_pixels() -> None:
    overlay = TextRenderer().render(layout_for("Hello"), text_config())

    assert overlay.image.mode == "RGBA"
    bbox = overlay.image.getbbox()
    assert bbox is not None  # some pixels are non-transparent


def test_overlay_dimensions_grow_by_exact_outline_and_shadow_padding() -> None:
    layout = layout_for("Hello world")
    renderer = TextRenderer()

    plain = renderer.render(layout, text_config(outline=0, shadow=0))
    outlined = renderer.render(layout, text_config(outline=4, shadow=0))
    shadowed = renderer.render(layout, text_config(outline=0, shadow=3))
    both = renderer.render(layout, text_config(outline=4, shadow=3))

    plain_w, plain_h = plain.size
    assert outlined.size == (plain_w + 8, plain_h + 8)  # +outline on every side
    assert shadowed.size == (plain_w + 3, plain_h + 3)  # shadow only pads right/bottom
    assert both.size == (plain_w + 8 + 3, plain_h + 8 + 3)


def test_overlay_placement_shifts_by_top_left_padding() -> None:
    layout = layout_for("Hello", box=TextBox(x=100, y=200, width=300, height=100))
    overlay = TextRenderer().render(layout, text_config(outline=5, shadow=2))

    assert overlay.box.x == 100 - 5
    assert overlay.box.y == 200 - 5


def test_rendering_is_byte_for_byte_deterministic() -> None:
    layout = layout_for("Hello world", "Second line")
    config = text_config(outline=2, shadow=1, color="#ABCDEF")
    renderer = TextRenderer()

    first = renderer.render(layout, config)
    second = renderer.render(layout, config)

    assert first.image.tobytes() == second.image.tobytes()
    assert first.size == second.size


def _opaque_pixel_count(image) -> int:  # type: ignore[no-untyped-def]
    alpha = image.getchannel("A")
    return sum(1 for value in alpha.tobytes() if value > 0)


def test_shadow_adds_more_opaque_pixels_than_without() -> None:
    layout = layout_for("Hello")
    renderer = TextRenderer()

    plain = renderer.render(layout, text_config(shadow=0))
    shadowed = renderer.render(layout, text_config(shadow=4))

    assert _opaque_pixel_count(shadowed.image) > _opaque_pixel_count(plain.image)


def test_outline_adds_more_opaque_pixels_than_without() -> None:
    layout = layout_for("Hello")
    renderer = TextRenderer()

    plain = renderer.render(layout, text_config(outline=0))
    outlined = renderer.render(layout, text_config(outline=4))

    assert _opaque_pixel_count(outlined.image) > _opaque_pixel_count(plain.image)


@pytest.mark.parametrize(
    ("horizontal",),
    [("left",), ("center",), ("right",)],
)
def test_horizontal_alignment_is_accepted_for_multiline_layout(horizontal: str) -> None:
    # "Hi" is much narrower than "Hello there"; just verifying every alignment
    # renders without error and produces a non-empty image is the deterministic,
    # font-metric-independent part of this behaviour.
    layout = layout_for("Hi", "Hello there")
    overlay = TextRenderer().render(layout, text_config(horizontal=horizontal))

    assert overlay.image.getbbox() is not None


def test_horizontal_alignment_orders_short_line_offset_left_to_right() -> None:
    # The short first line ("Hi") should sit further right as alignment moves
    # left -> center -> right, regardless of exact font metrics.
    layout = layout_for("Hi", "Hello there")
    renderer = TextRenderer()

    def first_line_left_edge(horizontal: str) -> int:
        overlay = renderer.render(layout, text_config(horizontal=horizontal))
        # Crop to the top portion of the image (roughly the first line's row
        # band) and find the left edge of non-transparent pixels there.
        half_height = max(overlay.image.size[1] // 2, 1)
        band = overlay.image.crop((0, 0, overlay.image.size[0], half_height))
        bbox = band.getbbox()
        assert bbox is not None
        return bbox[0]

    left_edge = first_line_left_edge("left")
    center_edge = first_line_left_edge("center")
    right_edge = first_line_left_edge("right")

    assert left_edge < center_edge < right_edge


def test_render_document_keys_overlays_by_segment_index() -> None:
    layouts = [
        SegmentLayout(
            segment_index=1,
            lines=("First",),
            font_size=30,
            box=TextBox(x=0, y=0, width=100, height=50),
            start=0.0,
            end=1.0,
        ),
        SegmentLayout(
            segment_index=2,
            lines=("Second",),
            font_size=30,
            box=TextBox(x=0, y=60, width=100, height=50),
            start=1.0,
            end=2.0,
        ),
    ]

    overlays = TextRenderer().render_document(layouts, text_config())

    assert set(overlays) == {1, 2}
    assert overlays[1].segment_index == 1
    assert overlays[2].segment_index == 2


def test_render_handles_degenerate_empty_line() -> None:
    overlay = TextRenderer().render(layout_for(""), text_config())

    assert overlay.image.size[0] >= 1
    assert overlay.image.size[1] >= 1
