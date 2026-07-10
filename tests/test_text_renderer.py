from __future__ import annotations

import logging
from pathlib import Path

import pytest

from media_production_framework import text_renderer
from media_production_framework.configuration import FontConfiguration, TextConfiguration
from media_production_framework.layout import SegmentLayout, TextBox
from media_production_framework.text_renderer import (
    DefaultFontSource,
    FontFileSet,
    TextRenderer,
    TrueTypeFontFile,
    default_font_set,
    resolve_font_set,
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
        # Crop to the top third of the image so the band contains only the first
        # line ("Hi"); the two lines are packed tightly, so a half-height band
        # would catch the top scanline of the wide second line and mask the
        # first line's alignment offset.
        band_height = max(overlay.image.size[1] // 3, 1)
        band = overlay.image.crop((0, 0, overlay.image.size[0], band_height))
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


def _stroked_ink_height(text: str, font_size: int, outline: int) -> int:
    from PIL import Image, ImageDraw

    font = DefaultFontSource().load(font_size)
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    _, top, _, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=outline)
    return bottom - top


def test_single_line_descenders_are_not_cropped() -> None:
    # Regression: the renderer used to allocate `bottom - top` per line but draw
    # from the ascender line, clipping the descenders (and outline) of the last
    # line by the font's top bearing. The ink height must now equal the full
    # stroked glyph height.
    line = "gjpqy"
    overlay = TextRenderer().render(layout_for(line, font_size=48), text_config(outline=4))

    alpha_bbox = overlay.image.getchannel("A").getbbox()
    assert alpha_bbox is not None
    ink_height = alpha_bbox[3] - alpha_bbox[1]
    assert ink_height == _stroked_ink_height(line, 48, outline=4)


def test_last_line_descenders_preserved_in_multiline() -> None:
    last = "gjpqy"
    overlay = TextRenderer().render(
        layout_for("Top line", last, font_size=48), text_config(outline=4)
    )

    first_height = _stroked_ink_height("Top line", 48, outline=4)
    band = overlay.image.crop((0, first_height, overlay.image.size[0], overlay.image.size[1]))
    alpha_bbox = band.getchannel("A").getbbox()
    assert alpha_bbox is not None
    ink_height = alpha_bbox[3] - alpha_bbox[1]
    assert ink_height == _stroked_ink_height(last, 48, outline=4)


# --- Font-name resolution -----------------------------------------------------


@pytest.mark.parametrize(
    ("subfamily", "expected"),
    [
        ("Regular", "regular"),
        ("Bold", "bold"),
        ("Italic", "italic"),
        ("Oblique", "italic"),
        ("Bold Italic", "bold_italic"),
        ("BoldOblique", "bold_italic"),
        ("", "regular"),
    ],
)
def test_style_key_classifies_subfamily(subfamily: str, expected: str) -> None:
    assert text_renderer._style_key(subfamily) == expected


def test_resolve_font_set_maps_generic_names_to_bundled_font() -> None:
    fonts = resolve_font_set(FontConfiguration(name="Sans"))

    assert isinstance(fonts.regular, DefaultFontSource)


def test_resolve_font_set_falls_back_and_warns_for_unknown_font(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(text_renderer, "_font_variants", lambda name: None)

    with caplog.at_level(logging.WARNING):
        fonts = resolve_font_set(FontConfiguration(name="NoSuchFamily"))

    assert isinstance(fonts.regular, DefaultFontSource)
    assert any("NoSuchFamily" in record.message for record in caplog.records)


def test_resolve_font_set_builds_variants_from_index(monkeypatch: pytest.MonkeyPatch) -> None:
    variants = {"regular": Path("reg.ttf"), "bold": Path("bold.ttf")}
    monkeypatch.setattr(text_renderer, "_font_variants", lambda name: variants)

    fonts = resolve_font_set(FontConfiguration(name="Mistral"))

    assert isinstance(fonts.regular, TrueTypeFontFile)
    assert fonts.regular.path == Path("reg.ttf")
    assert isinstance(fonts.bold, TrueTypeFontFile)
    assert fonts.italic is None
    assert fonts.bold_italic is None


def test_resolve_font_set_uses_explicit_file_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A name that is an existing font-file path is used directly, without a scan.
    font_file = tmp_path / "custom.ttf"
    font_file.write_bytes(b"")  # contents are irrelevant; only the path resolves here

    def fail(_name: str) -> None:  # pragma: no cover - must not be called
        raise AssertionError("system fonts must not be scanned for an explicit path")

    monkeypatch.setattr(text_renderer, "_font_variants", fail)

    fonts = resolve_font_set(FontConfiguration(name=str(font_file)))

    assert isinstance(fonts.regular, TrueTypeFontFile)
    assert fonts.regular.path == font_file
