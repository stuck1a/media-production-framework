"""
Subtitle validation.

Validates the internal subtitle model before it is exported or rendered. The
validator enforces the invariants that later stages rely on: ordered,
non-overlapping segments with sane, non-negative timing and non-empty text.
"""

from __future__ import annotations

from media_production_framework.subtitles import SubtitleDocument, SubtitleSegment

# Segments may legitimately touch (one ends exactly when the next begins).
# A small tolerance absorbs floating-point rounding when comparing boundaries.
_TIMING_TOLERANCE = 1e-6


class SubtitleValidationError(ValueError):
    """Raised when a subtitle document fails validation."""


class SubtitleValidator:
    """Validate the structural and timing integrity of a subtitle document."""

    def validate(self, document: SubtitleDocument) -> None:
        """Validate a subtitle document, raising on the first set of errors."""

        errors: list[str] = []
        previous_end = 0.0

        for segment in document.segments:
            label = f"segment {segment.index}"

            if not segment.text.strip():
                errors.append(f"{label}: text must not be empty")

            if segment.start < -_TIMING_TOLERANCE:
                errors.append(f"{label}: start time must not be negative")

            if segment.end + _TIMING_TOLERANCE < segment.start:
                errors.append(f"{label}: end time precedes start time")

            if segment.start + _TIMING_TOLERANCE < previous_end:
                errors.append(f"{label}: overlaps the previous segment")

            if (
                document.audio_duration is not None
                and segment.end > document.audio_duration + _TIMING_TOLERANCE
            ):
                errors.append(f"{label}: end time exceeds the audio duration")

            errors.extend(self._validate_words(segment, label))

            previous_end = max(previous_end, segment.end)

        if errors:
            raise SubtitleValidationError("; ".join(errors))

    @staticmethod
    def _validate_words(segment: SubtitleSegment, label: str) -> list[str]:
        errors: list[str] = []

        for position, word in enumerate(segment.words, start=1):
            if word.end + _TIMING_TOLERANCE < word.start:
                errors.append(f"{label} word {position}: end time precedes start time")
            if word.start + _TIMING_TOLERANCE < segment.start:
                errors.append(f"{label} word {position}: starts before the segment")
            if word.end > segment.end + _TIMING_TOLERANCE:
                errors.append(f"{label} word {position}: ends after the segment")
        return errors
