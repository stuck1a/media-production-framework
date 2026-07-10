from __future__ import annotations

import pytest

from media_production_framework.render_backends import (
    AUTO_BACKEND_ORDER,
    BACKEND_FFMPEG,
    BACKEND_MOVIEPY,
    RenderBackendFactory,
    RenderingError,
    resolve_auto_backend,
)


def always(value: bool):  # -> Callable[[], bool]
    return lambda: value


# --- resolve_auto_backend: pure selection policy (fake checks, no heavy deps) -


def test_auto_prefers_ffmpeg_when_both_available() -> None:
    resolved = resolve_auto_backend(
        AUTO_BACKEND_ORDER, {BACKEND_FFMPEG: always(True), BACKEND_MOVIEPY: always(True)}
    )

    assert resolved == BACKEND_FFMPEG


def test_auto_falls_back_to_moviepy_when_ffmpeg_unavailable() -> None:
    resolved = resolve_auto_backend(
        AUTO_BACKEND_ORDER, {BACKEND_FFMPEG: always(False), BACKEND_MOVIEPY: always(True)}
    )

    assert resolved == BACKEND_MOVIEPY


def test_auto_raises_when_nothing_is_available() -> None:
    with pytest.raises(RenderingError, match="No rendering backend is available"):
        resolve_auto_backend(
            AUTO_BACKEND_ORDER, {BACKEND_FFMPEG: always(False), BACKEND_MOVIEPY: always(False)}
        )


def test_auto_treats_missing_availability_entry_as_unavailable() -> None:
    resolved = resolve_auto_backend(AUTO_BACKEND_ORDER, {BACKEND_MOVIEPY: always(True)})

    assert resolved == BACKEND_MOVIEPY


def test_auto_respects_a_custom_order() -> None:
    resolved = resolve_auto_backend(
        (BACKEND_MOVIEPY, BACKEND_FFMPEG),
        {BACKEND_FFMPEG: always(True), BACKEND_MOVIEPY: always(True)},
    )

    assert resolved == BACKEND_MOVIEPY


# --- RenderBackendFactory: injected availability drives "auto" dispatch ------


def test_factory_auto_resolves_to_ffmpeg_backend_type() -> None:
    from media_production_framework.ffmpeg_backend import FfmpegRenderBackend

    factory = RenderBackendFactory(
        availability={BACKEND_FFMPEG: always(True), BACKEND_MOVIEPY: always(True)}
    )

    backend = factory.create("auto")

    assert isinstance(backend, FfmpegRenderBackend)
    assert backend.name == BACKEND_FFMPEG


def test_factory_auto_falls_back_to_moviepy_backend_type() -> None:
    from media_production_framework.moviepy_backend import MoviePyRenderBackend

    factory = RenderBackendFactory(
        availability={BACKEND_FFMPEG: always(False), BACKEND_MOVIEPY: always(True)}
    )

    backend = factory.create("auto")

    assert isinstance(backend, MoviePyRenderBackend)
    assert backend.name == BACKEND_MOVIEPY


def test_factory_auto_raises_when_nothing_available() -> None:
    factory = RenderBackendFactory(
        availability={BACKEND_FFMPEG: always(False), BACKEND_MOVIEPY: always(False)}
    )

    with pytest.raises(RenderingError, match="No rendering backend is available"):
        factory.create("auto")


def test_factory_still_creates_explicit_backends_regardless_of_availability() -> None:
    from media_production_framework.moviepy_backend import MoviePyRenderBackend

    # An explicit backend name bypasses "auto" selection entirely, even if the
    # injected availability says it is unavailable.
    factory = RenderBackendFactory(availability={BACKEND_MOVIEPY: always(False)})

    backend = factory.create(BACKEND_MOVIEPY)

    assert isinstance(backend, MoviePyRenderBackend)
