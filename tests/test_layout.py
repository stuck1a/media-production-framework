from __future__ import annotations

import pytest

from media_production_framework.configuration import (
    ContainerConfiguration,
    FontConfiguration,
    TextConfiguration,
)
from media_production_framework.layout import (
    FakeTextMeasurer,
    LayoutEngine,
    wrap_text_by_width,
)
from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment


class SimpleMeasurer:
    """Deterministic measurer: width = len(text) * size, height = size.

    Used instead of :class:`FakeTextMeasurer` where tests need hand-computable
    numbers independent of ``FakeTextMeasurer``'s internal scaling factors.
    """

    def measure(
        self, text: str, font: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        return (len(text) * size, size)


def document_with(*texts: str) -> SubtitleDocument:
    segments = tuple(
        SubtitleSegment(index=i + 1, text=text, start=float(i), end=float(i) + 1.0)
        for i, text in enumerate(texts)
    )
    return SubtitleDocument(segments=segments)


# --- wrap_text_by_width ---------------------------------------------------------


def test_wrap_text_by_width_never_splits_a_word() -> None:
    lines = wrap_text_by_width("a bb ccc dddd", SimpleMeasurer(), "F", 10, max_width_px=25)

    assert lines == ("a", "bb", "ccc", "dddd")
    assert " ".join(lines) == "a bb ccc dddd"


def test_wrap_text_by_width_combines_words_that_fit() -> None:
    lines = wrap_text_by_width("ab cd ef", SimpleMeasurer(), "F", 5, max_width_px=25)

    assert lines == ("ab cd", "ef")


def test_wrap_text_by_width_collapses_whitespace_and_handles_empty_text() -> None:
    assert wrap_text_by_width("  hello   world  ", SimpleMeasurer(), "F", 10, 1000) == (
        "hello world",
    )
    assert wrap_text_by_width("   ", SimpleMeasurer(), "F", 10, 1000) == ("",)


# --- Automatic font sizing (FR-038/039/040) -------------------------------------


def build_text_config(
    *, min_size: int, max_size: int, max_lines: int, mode: str = "auto"
) -> TextConfiguration:
    return TextConfiguration(
        container=ContainerConfiguration(width=0.25, padding_top=0.1, padding_bottom=0.2),
        font=FontConfiguration(
            name="F", mode=mode, size=42, max_lines=max_lines, min_size=min_size, max_size=max_size
        ),
    )


def test_auto_font_sizing_picks_largest_size_that_fits() -> None:
    # container width fraction 0.25 * video_width 200 = 50px container.
    # "aa bb" (len 5) fits one line only while 5 * size <= 50, i.e. size <= 10.
    text_config = build_text_config(min_size=1, max_size=20, max_lines=1)
    engine = LayoutEngine(SimpleMeasurer())

    layouts = engine.layout_document(
        document_with("aa bb"), text_config, video_width=200, video_height=100
    )

    assert layouts[0].font_size == 10
    assert layouts[0].lines == ("aa bb",)


def test_auto_font_sizing_longest_segment_governs_size() -> None:
    # "x" never needs to wrap regardless of size; "aa bb" is the binding
    # constraint, so the document-wide size must still clamp to 10 (FR-039).
    text_config = build_text_config(min_size=1, max_size=20, max_lines=1)
    engine = LayoutEngine(SimpleMeasurer())

    layouts = engine.layout_document(
        document_with("x", "aa bb"), text_config, video_width=200, video_height=100
    )

    assert {layout.font_size for layout in layouts} == {10}
    assert layouts[0].lines == ("x",)
    assert layouts[1].lines == ("aa bb",)


def test_auto_font_sizing_clamps_to_min_size_when_nothing_fits() -> None:
    # min_size itself already produces 2 lines for "aa bb" at container 50px;
    # no size in [15, 20] satisfies max_lines=1, so the result clamps to 15
    # and wraps best-effort (exceeding max_lines) rather than raising.
    text_config = build_text_config(min_size=15, max_size=20, max_lines=1)
    engine = LayoutEngine(SimpleMeasurer())

    layouts = engine.layout_document(
        document_with("aa bb"), text_config, video_width=200, video_height=100
    )

    assert layouts[0].font_size == 15
    assert layouts[0].lines == ("aa", "bb")
    assert len(layouts[0].lines) > text_config.font.max_lines


def test_fixed_font_mode_bypasses_scaling_search() -> None:
    text_config = build_text_config(min_size=1, max_size=20, max_lines=1, mode="fixed")
    text_config = TextConfiguration(
        container=text_config.container,
        font=FontConfiguration(
            name="F", mode="fixed", size=42, max_lines=1, min_size=1, max_size=20
        ),
    )
    engine = LayoutEngine(SimpleMeasurer())

    layouts = engine.layout_document(
        document_with("aa bb"), text_config, video_width=200, video_height=100
    )

    assert layouts[0].font_size == 42


def test_layout_document_returns_empty_for_empty_document() -> None:
    engine = LayoutEngine(SimpleMeasurer())

    assert engine.layout_document(document_with(), TextConfiguration(), 1920, 1080) == ()


# --- Anchor / box math (FR-042/043/044) -----------------------------------------


@pytest.mark.parametrize(
    ("horizontal", "vertical", "expected_x", "expected_y"),
    [
        ("left", "top", 50, 10),
        ("center", "top", 90, 10),
        ("right", "top", 130, 10),
        ("left", "middle", 50, 40),
        ("center", "middle", 90, 40),
        ("right", "middle", 130, 40),
        ("left", "bottom", 50, 70),
        ("center", "bottom", 90, 70),
        ("right", "bottom", 130, 70),
    ],
)
def test_box_anchor_for_each_alignment_combination(
    horizontal: str, vertical: str, expected_x: int, expected_y: int
) -> None:
    # video 200x100; container width 0.5 -> 100px, centered -> container_x=50.
    # padding_top 0.1 -> 10px, padding_bottom 0.2 -> 20px, available height 70px.
    # single-word segment "AB" at fixed size 10: block is 20px wide, 10px tall.
    text_config = TextConfiguration(
        container=ContainerConfiguration(width=0.5, padding_top=0.1, padding_bottom=0.2),
        font=FontConfiguration(
            name="F", mode="fixed", size=10, max_lines=3, min_size=1, max_size=20
        ),
        vertical=vertical,
        horizontal=horizontal,
    )
    engine = LayoutEngine(SimpleMeasurer())

    layouts = engine.layout_document(
        document_with("AB"), text_config, video_width=200, video_height=100
    )
    box = layouts[0].box

    assert (box.x, box.y) == (expected_x, expected_y)
    assert (box.width, box.height) == (20, 10)


# --- FakeTextMeasurer wiring (sanity, not exact-formula coupled) ---------------


def test_layout_engine_defaults_to_fake_measurer() -> None:
    engine = LayoutEngine()

    layouts = engine.layout_document(
        document_with("Hello world"), TextConfiguration(), video_width=1920, video_height=1080
    )

    assert len(layouts) == 1
    assert layouts[0].font_size >= TextConfiguration().font.min_size
    assert layouts[0].box.width > 0
    assert layouts[0].box.height > 0


def test_fake_text_measurer_scales_width_with_size_and_length() -> None:
    measurer = FakeTextMeasurer()

    small_width, small_height = measurer.measure("hello", "F", 10)
    large_width, large_height = measurer.measure("hello", "F", 20)

    assert large_width > small_width
    assert large_height > small_height
    bold_width, _ = measurer.measure("hello", "F", 10, bold=True)
    assert bold_width > small_width
