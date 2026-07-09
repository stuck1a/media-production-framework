"""
Audio inspection utilities.

The framework intentionally avoids heavy media dependencies for basic audio
inspection. Duration is currently derived from uncompressed WAV files using the
Python standard library. Compressed formats require either an explicit duration
override in the configuration or a future provider-based audio backend.
"""

from __future__ import annotations

import contextlib
import wave
from pathlib import Path


class AudioError(RuntimeError):
    """Raised when audio information cannot be determined."""


def get_audio_duration(path: Path) -> float:
    """Return the duration of an audio file in seconds.

    Only uncompressed WAV files are supported without additional dependencies.
    For other formats an :class:`AudioError` is raised so the caller can fall
    back to an explicit configuration value.
    """

    if not path.is_file():
        raise AudioError(f"Audio file does not exist: {path}")

    if path.suffix.lower() != ".wav":
        raise AudioError(
            "Automatic duration detection currently supports WAV files only; "
            f"configure an explicit duration for: {path}"
        )

    try:
        with contextlib.closing(wave.open(str(path), "rb")) as audio:
            frames = audio.getnframes()
            frame_rate = audio.getframerate()
    except wave.Error as exc:
        raise AudioError(f"Unable to read WAV audio: {path}") from exc

    if frame_rate <= 0:
        raise AudioError(f"Audio file reports an invalid frame rate: {path}")

    return frames / float(frame_rate)
