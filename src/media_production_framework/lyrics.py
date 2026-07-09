"""
Lyrics parsing.

Lyrics supplied by the user are the authoritative source of textual content
(FR-010). The parser preserves the original line segmentation while additionally
tokenizing each line so that word-level alignment results can be mapped back
onto the original lines.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from media_production_framework.domain import LyricsDocument

# Matches words including internal apostrophes (e.g. "don't", "l'amour").
_TOKEN_PATTERN = re.compile(r"\w+(?:'\w+)?", re.UNICODE)


def tokenize(text: str) -> Sequence[str]:
    """Split a line of text into word tokens."""

    return tuple(_TOKEN_PATTERN.findall(text))


@dataclass(frozen=True)
class LyricLine:
    """A single line of lyrics and its word tokens."""

    text: str
    tokens: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ParsedLyrics:
    """Structured lyrics preserving the original line segmentation."""

    lines: Sequence[LyricLine] = field(default_factory=tuple)

    @property
    def all_tokens(self) -> Sequence[str]:
        """Return every token across all lines in reading order."""

        return tuple(token for line in self.lines for token in line.tokens)

    @property
    def token_count(self) -> int:
        """Return the total number of tokens across all lines."""

        return sum(len(line.tokens) for line in self.lines)


class LyricsParser:
    """Parse raw lyrics text into structured, tokenized lines."""

    def parse(self, text: str) -> ParsedLyrics:
        """Parse raw lyrics text, ignoring blank lines."""

        lines = [
            LyricLine(text=stripped, tokens=tokenize(stripped))
            for raw_line in text.splitlines()
            if (stripped := raw_line.strip())
        ]
        return ParsedLyrics(lines=tuple(lines))

    def parse_document(self, document: LyricsDocument) -> ParsedLyrics:
        """Parse a :class:`LyricsDocument` loaded from a project."""

        return self.parse(document.text)
