"""
Word-preserving text wrapping for subtitle rendering.
"""

from __future__ import annotations

from collections.abc import Sequence


def wrap_text(text: str, max_line_length: int) -> Sequence[str]:
    """Wrap text into lines without splitting individual words.

    A ``max_line_length`` of zero or less disables wrapping and returns the
    original text as a single line. Words longer than ``max_line_length`` are
    placed on their own line rather than being split, preserving readability.
    """

    normalized = " ".join(text.split())
    if max_line_length <= 0 or not normalized:
        return (normalized,) if normalized else ("",)

    lines: list[str] = []
    current: list[str] = []
    current_length = 0

    for word in normalized.split(" "):
        if not current:
            current.append(word)
            current_length = len(word)
            continue

        # +1 accounts for the space that would join the word to the line.
        if current_length + 1 + len(word) <= max_line_length:
            current.append(word)
            current_length += 1 + len(word)
        else:
            lines.append(" ".join(current))
            current = [word]
            current_length = len(word)

    if current:
        lines.append(" ".join(current))

    return tuple(lines)
