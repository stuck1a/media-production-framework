"""
Audio inspection utilities.

The framework avoids a heavy audio-decoding dependency for basic inspection.
Uncompressed WAV duration is read with the Python standard library; for every
other container (MP3, M4A, FLAC, ...) duration is probed with ``ffprobe``, which
ships with FFmpeg -- already required by the rendering backends. When neither
path can determine the duration an :class:`AudioError` is raised so the caller
can fall back to an explicit configuration value.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import wave
from pathlib import Path

DEFAULT_FFPROBE_BINARY = "ffprobe"
_FFPROBE_TIMEOUT_SECONDS = 30


class AudioError(RuntimeError):
    """Raised when audio information cannot be determined."""


def get_audio_duration(path: Path) -> float:
    """Return the duration of an audio file in seconds.

    Uncompressed ``.wav`` files are read directly with the standard library
    (no external process); all other formats -- and any WAV the stdlib cannot
    parse -- are probed with ``ffprobe``. An :class:`AudioError` is raised when
    the duration cannot be determined by either path.
    """

    if not path.is_file():
        raise AudioError(f"Audio file does not exist: {path}")

    if path.suffix.lower() == ".wav":
        with contextlib.suppress(AudioError):
            return _wav_duration(path)
        # A non-PCM or malformed WAV container falls through to ffprobe.

    return _ffprobe_duration(path)


def _wav_duration(path: Path) -> float:
    """Return the duration of an uncompressed WAV file via the standard library."""

    try:
        with contextlib.closing(wave.open(str(path), "rb")) as audio:
            frames = audio.getnframes()
            frame_rate = audio.getframerate()
    except (wave.Error, EOFError) as exc:
        raise AudioError(f"Unable to read WAV audio: {path}") from exc

    if frame_rate <= 0:
        raise AudioError(f"Audio file reports an invalid frame rate: {path}")

    return frames / float(frame_rate)


def _ffprobe_duration(path: Path, *, binary: str = DEFAULT_FFPROBE_BINARY) -> float:
    """Return the duration of any audio file using ``ffprobe``.

    ``ffprobe`` is part of FFmpeg; when it is absent the error explains how to
    resolve it (install FFmpeg or configure an explicit duration).
    """

    resolved = shutil.which(binary)
    if resolved is None:
        raise AudioError(
            "Automatic duration detection for non-WAV audio requires 'ffprobe' "
            "(bundled with FFmpeg) on PATH. Install FFmpeg or configure an "
            f"explicit duration for: {path}"
        )

    command = [
        resolved,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AudioError(f"Failed to run ffprobe for {path}: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit code {completed.returncode}"
        raise AudioError(f"ffprobe could not read audio duration for {path}: {detail}")

    text = completed.stdout.strip()
    try:
        duration = float(text)
    except ValueError as exc:
        raise AudioError(
            f"ffprobe returned an unparsable duration for {path}: {text!r}"
        ) from exc

    if duration <= 0:
        raise AudioError(f"ffprobe reported a non-positive duration for {path}: {duration}")

    return duration
