# Changelog

All notable changes to Media Production Framework are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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
