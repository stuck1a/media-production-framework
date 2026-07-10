"""
Subtitle alignment.

The Alignment Engine synchronises manually supplied lyrics with an audio
recording (forced alignment) and produces the internal subtitle model. Concrete
alignment implementations are hidden behind the :class:`AlignmentProvider`
interface so business logic never depends on a particular backend (TC-022).

Two categories of providers are offered:

* :class:`HeuristicAlignmentProvider` -- a fully offline, deterministic default
  that distributes timing across the audio duration proportionally to token
  length. It requires no machine-learning dependencies and satisfies the
  "offline first" and "deterministic processing" principles.
* :class:`StableWhisperAlignmentProvider` / :class:`FasterWhisperAlignmentProvider`
  -- real forced-alignment backends built on ``stable-ts``. Their heavy
  dependencies are imported lazily so they remain entirely optional.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from media_production_framework.domain import SongMetadata
from media_production_framework.lyrics import LyricLine, ParsedLyrics
from media_production_framework.subtitles import (
    SubtitleDocument,
    SubtitleSegment,
    SubtitleWord,
)

PROVIDER_HEURISTIC = "heuristic"
PROVIDER_STABLE_WHISPER = "stable-whisper"
PROVIDER_FASTER_WHISPER = "faster-whisper"


class AlignmentError(RuntimeError):
    """Raised when subtitle alignment fails."""


@dataclass(frozen=True)
class WordTiming:
    """A single aligned word with start and end timestamps in seconds."""

    word: str
    start: float
    end: float


@dataclass(frozen=True)
class AlignmentRequest:
    """Input required to align lyrics with an audio recording.

    ``options`` is an opaque, provider-specific passthrough (e.g. stable-ts
    alignment knobs such as ``vad`` or ``word_dur_factor``); providers that do
    not recognise a given backend simply ignore it.
    """

    audio_path: Path
    parsed_lyrics: ParsedLyrics
    raw_lyrics: str
    language: str | None = None
    audio_duration: float | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


class AlignmentProvider(Protocol):
    """Interface implemented by subtitle alignment backends."""

    name: str

    def align(self, request: AlignmentRequest) -> Sequence[WordTiming]:
        """Return word-level timings aligned to the request lyrics."""


class HeuristicAlignmentProvider:
    """Deterministic, offline alignment provider.

    Timing is distributed across the full audio duration proportionally to the
    character length of each token. This produces reproducible results without
    any external dependency, making it suitable as the default provider and for
    automated testing.
    """

    name = PROVIDER_HEURISTIC

    def align(self, request: AlignmentRequest) -> Sequence[WordTiming]:
        duration = request.audio_duration
        if duration is None:
            raise AlignmentError(
                "The heuristic provider requires a known audio duration; "
                "provide a WAV file or configure an explicit duration."
            )
        if duration <= 0:
            raise AlignmentError("Audio duration must be positive for alignment.")

        tokens = list(request.parsed_lyrics.all_tokens)
        if not tokens:
            return ()

        weights = [max(len(token), 1) for token in tokens]
        total_weight = sum(weights)

        timings: list[WordTiming] = []
        elapsed_weight = 0
        for token, weight in zip(tokens, weights, strict=True):
            start = duration * (elapsed_weight / total_weight)
            elapsed_weight += weight
            end = duration * (elapsed_weight / total_weight)
            timings.append(WordTiming(word=token, start=start, end=end))
        return tuple(timings)


class StableWhisperAlignmentProvider:
    """Forced alignment using an OpenAI Whisper model via ``stable-ts``.

    ``AlignmentRequest.options`` is forwarded verbatim as keyword arguments to
    ``stable_whisper``'s ``align()`` (e.g. ``vad``, ``word_dur_factor``,
    ``max_word_dur``, ``nonspeech_skip``); this provider does not interpret or
    validate them, it only relays them to the underlying library.
    """

    name = PROVIDER_STABLE_WHISPER

    def __init__(self, model: str | None = None) -> None:
        if not model:
            raise AlignmentError(
                "The stable-whisper provider requires a configured model path."
            )
        self._model = model

    def align(self, request: AlignmentRequest) -> Sequence[WordTiming]:
        try:
            from stable_whisper import load_model
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise AlignmentError(
                "The stable-whisper provider requires the optional 'stable-ts' "
                "dependency. Install it with: pip install media-production-framework[whisper]"
            ) from exc

        model = load_model(self._model)
        result = model.align(
            str(request.audio_path),
            text=request.raw_lyrics,
            language=request.language,
            **request.options,
        )
        return _word_timings_from_stable_result(result)


class FasterWhisperAlignmentProvider:
    """Forced alignment using a Faster-Whisper model via ``stable-ts``.

    ``AlignmentRequest.options`` is forwarded verbatim as keyword arguments to
    ``stable_whisper``'s ``align()``, the same as :class:`StableWhisperAlignmentProvider`.
    """

    name = PROVIDER_FASTER_WHISPER

    def __init__(self, model: str | None = None) -> None:
        # Faster-Whisper accepts model size names (e.g. "large-v3") as well as
        # local model directories, so an explicit value is still required.
        if not model:
            raise AlignmentError(
                "The faster-whisper provider requires a configured model."
            )
        self._model = model

    def align(self, request: AlignmentRequest) -> Sequence[WordTiming]:
        try:
            from stable_whisper import load_faster_whisper
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise AlignmentError(
                "The faster-whisper provider requires the optional 'faster-whisper' "
                "dependency. Install it with: "
                "pip install media-production-framework[faster-whisper]"
            ) from exc

        model = load_faster_whisper(self._model)
        result = model.align(
            str(request.audio_path),
            text=request.raw_lyrics,
            language=request.language,
            **request.options,
        )
        return _word_timings_from_stable_result(result)


def _word_timings_from_stable_result(result: object) -> Sequence[WordTiming]:
    """Convert a stable-ts alignment result into :class:`WordTiming` objects."""

    all_words = getattr(result, "all_words", None)
    if not callable(all_words):  # pragma: no cover - defensive guard
        raise AlignmentError("Unexpected alignment result: missing word data.")

    timings: list[WordTiming] = []
    for word in all_words():
        text = str(getattr(word, "word", "")).strip()
        if not text:
            continue
        timings.append(WordTiming(word=text, start=float(word.start), end=float(word.end)))
    return tuple(timings)


class AlignmentProviderFactory:
    """Create alignment providers from a provider name and model configuration."""

    def create(self, name: str, model: str | None = None) -> AlignmentProvider:
        """Return an alignment provider for the given name."""

        normalized = name.lower()
        if normalized == PROVIDER_HEURISTIC:
            return HeuristicAlignmentProvider()
        if normalized in {PROVIDER_STABLE_WHISPER, "whisper"}:
            return StableWhisperAlignmentProvider(model=model)
        if normalized == PROVIDER_FASTER_WHISPER:
            return FasterWhisperAlignmentProvider(model=model)
        raise AlignmentError(f"Unknown alignment provider: {name}")


# Fallback on-screen duration for an unaligned segment when no audio window is
# available to distribute (e.g. the failed lines run to the end of the song and
# the audio duration is unknown). Keeps cues visible and never zero-length.
_NOMINAL_SEGMENT_DURATION = 2.0


@dataclass
class SubtitleBuilder:
    """Map word-level timings back onto the original lyric segmentation.

    Each lyric line becomes one subtitle segment. The segment inherits the start
    time of its first aligned word and the end time of its last aligned word,
    preserving the user's original line segmentation (FR-010).

    When the aligner returns fewer words than the lyrics contain, the remaining
    lines cannot be mapped word-for-word. ``max_failures`` (PF7) bounds how many
    such lines are tolerated: with the default ``0`` this raises an
    :class:`AlignmentError` that names the offending segments (PF6); with a
    higher value the builder logs a warning and approximates the timing of those
    segments (proportionally to token length, like the heuristic provider)
    instead of aborting, trading timing accuracy for a usable result.
    """

    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def build(
        self,
        parsed_lyrics: ParsedLyrics,
        word_timings: Sequence[WordTiming],
        language: str | None = None,
        audio_duration: float | None = None,
        metadata: SongMetadata | None = None,
        max_failures: int = 0,
    ) -> SubtitleDocument:
        """Build a :class:`SubtitleDocument` from lyrics and word timings."""

        lines = [line for line in parsed_lyrics.lines if len(line.tokens) > 0]
        total_words = len(word_timings)

        segments: list[SubtitleSegment] = []
        word_index = 0
        previous_end = 0.0

        for position, line in enumerate(lines):
            token_count = len(line.tokens)

            if total_words - word_index < token_count:
                # Not enough aligned words remain for this line, so it and every
                # line after it form a "degraded tail" that cannot be mapped
                # word-for-word. Report the shortfall and either abort (PF6) or
                # approximate the remaining segments (PF7).
                failed_lines = lines[position:]
                self._report_failures(failed_lines, position, max_failures)
                segments.extend(
                    self._approximate_segments(
                        failed_lines, position, previous_end, audio_duration
                    )
                )
                break

            line_timings = word_timings[word_index : word_index + token_count]
            words = tuple(
                SubtitleWord(text=timing.word, start=timing.start, end=timing.end)
                for timing in line_timings
            )
            segments.append(
                SubtitleSegment(
                    index=position + 1,
                    text=line.text,
                    start=line_timings[0].start,
                    end=line_timings[-1].end,
                    words=words,
                )
            )
            word_index += token_count
            previous_end = line_timings[-1].end

        return SubtitleDocument(
            segments=tuple(segments),
            language=language,
            audio_duration=audio_duration,
            metadata=metadata,
        )

    def _report_failures(
        self,
        failed_lines: Sequence[LyricLine],
        position: int,
        max_failures: int,
    ) -> None:
        """Log (PF6) or abort (PF7) on lyric lines that could not be aligned."""

        descriptors = "; ".join(
            f"segment {position + offset + 1} ({line.text!r})"
            for offset, line in enumerate(failed_lines)
        )
        count = len(failed_lines)

        if count > max_failures:
            raise AlignmentError(
                f"Alignment produced fewer words than the lyrics contain; "
                f"{count} segment(s) could not be aligned: {descriptors}. "
                f"The audio and lyrics may not match. Increase "
                f"'subtitles.max_alignment_failures_allowed' (currently "
                f"{max_failures}) to tolerate this at the cost of timing accuracy."
            )

        self.logger.warning(
            "Alignment could not map %d lyric segment(s); approximating their "
            "timing (max_alignment_failures_allowed=%d): %s",
            count,
            max_failures,
            descriptors,
        )

    def _approximate_segments(
        self,
        failed_lines: Sequence[LyricLine],
        position: int,
        start_bound: float,
        audio_duration: float | None,
    ) -> list[SubtitleSegment]:
        """Distribute the leftover time window across unaligned lines (PF7).

        The window spans from the end of the last aligned segment to the audio
        duration (when known); it is split between the failed lines in
        proportion to their token character length, mirroring the heuristic
        provider. When no usable window exists (the audio duration is unknown or
        does not extend past the last aligned segment -- e.g. a failed *final*
        line), each segment instead gets a fixed nominal duration so it stays
        visible and never collapses to a zero-length marker.
        """

        window = 0.0
        if audio_duration is not None and audio_duration > start_bound:
            window = audio_duration - start_bound

        if window <= 0:
            return self._nominal_segments(failed_lines, position, start_bound)

        weights = [max(sum(len(token) for token in line.tokens), 1) for line in failed_lines]
        total_weight = sum(weights)

        segments: list[SubtitleSegment] = []
        elapsed_weight = 0
        cursor = start_bound
        for offset, (line, weight) in enumerate(zip(failed_lines, weights, strict=True)):
            segment_start = cursor
            elapsed_weight += weight
            segment_end = start_bound + window * (elapsed_weight / total_weight)
            segments.append(
                SubtitleSegment(
                    index=position + offset + 1,
                    text=line.text,
                    start=segment_start,
                    end=segment_end,
                    words=self._interpolate_words(line.tokens, segment_start, segment_end),
                )
            )
            cursor = segment_end
        return segments

    def _nominal_segments(
        self,
        failed_lines: Sequence[LyricLine],
        position: int,
        start_bound: float,
    ) -> list[SubtitleSegment]:
        """Lay out unaligned lines back-to-back at a fixed nominal duration."""

        segments: list[SubtitleSegment] = []
        cursor = start_bound
        for offset, line in enumerate(failed_lines):
            segment_start = cursor
            segment_end = segment_start + _NOMINAL_SEGMENT_DURATION
            segments.append(
                SubtitleSegment(
                    index=position + offset + 1,
                    text=line.text,
                    start=segment_start,
                    end=segment_end,
                    words=self._interpolate_words(line.tokens, segment_start, segment_end),
                )
            )
            cursor = segment_end
        return segments

    @staticmethod
    def _interpolate_words(
        tokens: Sequence[str],
        start: float,
        end: float,
    ) -> tuple[SubtitleWord, ...]:
        """Spread ``tokens`` across ``[start, end]`` proportionally to length."""

        weights = [max(len(token), 1) for token in tokens]
        total_weight = sum(weights)
        span = end - start

        words: list[SubtitleWord] = []
        elapsed_weight = 0
        for token, weight in zip(tokens, weights, strict=True):
            word_start = start + span * (elapsed_weight / total_weight)
            elapsed_weight += weight
            word_end = start + span * (elapsed_weight / total_weight)
            words.append(SubtitleWord(text=token, start=word_start, end=word_end))
        return tuple(words)


@dataclass
class AlignmentService:
    """Facade coordinating provider selection and subtitle construction."""

    factory: AlignmentProviderFactory = field(default_factory=AlignmentProviderFactory)
    builder: SubtitleBuilder = field(default_factory=SubtitleBuilder)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))

    def align(
        self,
        request: AlignmentRequest,
        provider_name: str,
        model: str | None = None,
        metadata: SongMetadata | None = None,
        max_failures: int = 0,
    ) -> SubtitleDocument:
        """Align lyrics and return the resulting subtitle document."""

        provider = self.factory.create(provider_name, model=model)
        self.logger.info(
            "Aligning %d lyric lines using provider '%s'.",
            len(request.parsed_lyrics.lines),
            provider.name,
        )
        word_timings = provider.align(request)
        return self.builder.build(
            request.parsed_lyrics,
            word_timings,
            language=request.language,
            audio_duration=request.audio_duration,
            metadata=metadata,
            max_failures=max_failures,
        )
