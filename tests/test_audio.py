from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest

from media_production_framework import audio
from media_production_framework.audio import AudioError, get_audio_duration


def _write_wav(path: Path, seconds: float, frame_rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(frame_rate)
        handle.writeframes(b"\x00\x00" * int(seconds * frame_rate))


def test_wav_duration_uses_stdlib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = tmp_path / "clip.wav"
    _write_wav(wav, 2.5)

    def fail(*_args: object, **_kwargs: object) -> None:  # pragma: no cover - must not run
        raise AssertionError("ffprobe must not be used for a valid WAV")

    monkeypatch.setattr(audio.subprocess, "run", fail)

    assert get_audio_duration(wav) == pytest.approx(2.5, abs=0.01)


def test_missing_file_raises() -> None:
    with pytest.raises(AudioError, match="does not exist"):
        get_audio_duration(Path("nope.wav"))


def test_non_wav_uses_ffprobe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"not really an mp3")

    monkeypatch.setattr(audio.shutil, "which", lambda _name: "ffprobe")

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="183.456\n", stderr="")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    assert get_audio_duration(mp3) == pytest.approx(183.456)


def test_non_wav_without_ffprobe_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"data")

    monkeypatch.setattr(audio.shutil, "which", lambda _name: None)

    with pytest.raises(AudioError, match="ffprobe"):
        get_audio_duration(mp3)


def test_ffprobe_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"data")

    monkeypatch.setattr(audio.shutil, "which", lambda _name: "ffprobe")

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)

    with pytest.raises(AudioError, match="could not read audio duration"):
        get_audio_duration(mp3)
