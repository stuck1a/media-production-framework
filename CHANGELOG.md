# Changelog

All notable changes to Media Production Framework are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Milestone M3 Part 5 (MoviePy backend + automatic selection): `moviepy_backend.py`
  implements a second, interchangeable `MoviePyRenderBackend` (FR-029) covering
  the same ground as the FFmpeg backend — colour/image/looping-video
  backgrounds scaled and padded to preserve aspect ratio (FR-049-FR-054), Part
  3's timed text overlays, audio, and the configured encoder settings. Video
  backgrounds loop and trim to the exact output duration via MoviePy's `Loop`
  effect (FR-052/FR-053). Progress is bridged from MoviePy's `proglog` progress
  bars into the same `RenderProgress` callback shape the FFmpeg backend uses
  (FR-032). `MoviePyCommandBuilder` builds a symbolic, ordered description of
  the composition (MoviePy has no literal command line) so it stays fully
  argv-style testable without importing MoviePy. `moviepy` is lazily imported
  and added as its own optional extra.
  - `RenderBackendFactory` now supports `"auto"` backend selection (FR-030):
    `resolve_auto_backend` is a pure policy function (prefers FFmpeg, falls
    back to MoviePy, raises `RenderingError` if neither is available, FR-031)
    testable with fake availability checks with no heavy dependency needed.
    The factory accepts an injectable `availability` mapping for exactly that.
  - Extracted the shared `FontSourceMeasurer` (bridges the Layout Engine's
    sizing pass to a backend's own fonts) from `ffmpeg_backend.py` into
    `text_renderer.py` so both real backends reuse the same font-consistent
    measurement instead of duplicating it.
  - tests/test_render_selection.py (9 tests) and tests/test_moviepy_backend.py
    (11 tests): pure selection-policy and command-token assertions, plus
    `@pytest.mark.moviepy` integration tests (skipped when moviepy is absent)
    that render a real clip and verify video-background loop/trim.
  - Registered the `moviepy` pytest marker and `moviepy` optional extra.
- Milestone M3 Part 4 (FFmpeg backend): `ffmpeg_backend.py` implements the real
  `FfmpegRenderBackend`, driving the `ffmpeg` binary as a subprocess to compose
  and encode a video end-to-end. Builds the command/filtergraph for solid
  colour (`lavfi color`), static image (`-loop 1`) and looping video
  (`-stream_loop`) backgrounds, all scaled and padded to the output resolution
  preserving aspect ratio (FR-049-FR-054); overlays the Part 3 timed text
  (`enable='between(t,...)'`), maps audio and applies the configured encoder
  settings (FR-024-FR-028). Looping/trimming to the exact output duration via
  `-t`/`-shortest` (FR-052/FR-053). Progress is parsed from `-progress` output
  into `RenderProgress` updates via an injectable callback (FR-032, NFR-011),
  and success is confirmed only when a non-empty output file exists (NFR-020).
  The backend is registered in `RenderBackendFactory` with a lazy import and
  probes the binary, raising `RenderingError` when ffmpeg is absent so a future
  part can fall back to another backend (FR-031).
- tests/test_ffmpeg_backend.py (19 tests): pure argv/filtergraph assertions for
  every background type, audio mapping and overlay-index/enable-expression
  construction; progress-parser tests against captured `-progress` text; binary
  probing; and a `@pytest.mark.ffmpeg` integration test (skipped when ffmpeg is
  absent) that renders a real ~0.5 s clip and asserts a non-empty file.
- Registered the `ffmpeg` pytest marker in `pyproject.toml`.
- Milestone M3 Part 3 (Text Renderer): `text_renderer.py` rasterizes each
  `SegmentLayout` into a transparent RGBA overlay image via Pillow, honouring
  colour, bold/italic font selection (`FontFileSet`), outline (stroke) and
  drop shadow (FR-036, FR-041, FR-047). Overlays are keyed by segment index
  for the future compositor (Part 4). Effects are drawn as small, additive
  steps so new ones can be added without touching existing code (FR-048).
  `DefaultFontSource` uses Pillow's own bundled scalable font, so tests
  rasterize deterministically offline with no bundled binary font asset and
  no system-font dependency.
- Added `Pillow` to the `dev` optional-dependency group (already available
  standalone as the `render` extra) so the full test suite runs without
  extra setup.
- Milestone M3 Part 2 (Layout Engine): `layout.py` deterministically computes,
  for each subtitle segment, pixel-measured word-preserving wrapped lines, an
  automatically scaled font size (binary search over the configured
  `[min_size, max_size]` range, governed by the hardest-to-fit segment per
  FR-039) and the text block's bounding box from `vertical`/`horizontal`/
  container padding. Measurement is delegated to a `TextMeasurer` protocol
  (`FakeTextMeasurer` for deterministic tests, `PillowTextMeasurer` for real
  usage via the lazily-imported `render` extra), so layout stays a pure,
  offline-testable function (no rasterization or I/O).
- Milestone M3 Part 1 (Rendering foundation): `rendering` and `ffmpeg`
  configuration sections (`configuration.py`) with per-key validation for
  video format, background source, text/font/container layout and karaoke
  (parsed and reserved for M4).
- Rendering domain model (`rendering.py`): `RenderSettings`, `RenderJob`,
  `RenderPlan`, `BackgroundOperation`, `RenderProgress` and `RenderResult`.
- Pluggable render backend seam (`render_backends.py`): `RenderBackend`
  protocol, `RenderBackendFactory`, `RenderService` and the default offline
  `DryRunRenderBackend` that plans a render without executing any tooling
  (see ADR-0002).
- Rendering events (`RenderingStartedEvent`, `RenderingProgressEvent`,
  `RenderingCompletedEvent`, `PreviewRenderingCompletedEvent`).
- Optional `render` dependency extra (`Pillow`) for text measurement and
  rasterization in later M3 parts.
- ADR-0002 documenting the render-backend architecture (plan/execute split,
  dry-run testing strategy, Pillow and FFmpeg-as-subprocess choices).
- Milestone M2 (Subtitle Generation): provider-based Alignment Engine with
  `heuristic` (offline, deterministic default), `stable-whisper` and
  `faster-whisper` providers (see ADR-0001).
- Lyrics parsing (`lyrics.py`), word-preserving text wrapping
  (`text_wrapping.py`), FFMETADATA1 metadata parsing (`metadata.py`) and WAV
  duration inspection (`audio.py`).
- Subtitle domain model (`subtitles.py`) with segment- and word-level timing,
  subtitle validation (`subtitle_validation.py`), and interchangeable SRT/JSON
  exporters (`subtitle_export.py`).
- New `subtitle-alignment` and `subtitle-export` pipeline stages, wired into
  the core pipeline between provider initialization and rendering.
- `subtitles` configuration section (`enabled`, `provider`, `model`,
  `language`, `file`, `max_line_length`, `audio_duration_seconds`).

### Changed
- Renamed the final placeholder pipeline stage from `placeholder-processing`
  to `rendering-placeholder` to reflect that subtitle generation is no longer
  a placeholder.

### Removed
- Deleted the legacy, non-functional `subtitles/create_subtitles_OLD.py`
  script; it collided with the new `subtitles.py` domain module and its
  functionality is now implemented properly by the Alignment Engine.

## [0.1.1] - 2026-07-06

### Changed
- Renamed project from "lyrics-video-renderer" to "Media Production Framework" as it has been grown from a monolythic script to a large framwork project.

## [0.1.0] - 2026-07-06

### Added
- Introduced project architecture and roadmap.
