# Roadmap

**Document Version:** v0.1.0  
**Status:** Living Document

---

# Purpose

This roadmap describes the planned evolution of the Media Production Framework.

It defines the intended development direction without committing to fixed release dates.

The roadmap is intended to guide architectural decisions and reduce feature creep during development.

---

# Guiding Principles

Development follows an incremental approach.

Each milestone should

- produce a usable result
- improve the existing architecture
- remain compatible with the long-term vision

Architecture quality takes precedence over release speed.

---

# Milestone M1 — Core Foundation
- Done? [x]

## Goals

Establish the technical foundation of the framework.

### Planned Features

- [x] Project structure
- [x] Configuration system
- [x] Logging system
- [x] Event system
- [x] Pipeline infrastructure
- [x] Domain objects
- [x] Provider infrastructure
- [x] CLI entry point
- [x] Basic project loading
- [x] Basic validation
- [x] Automated testing infrastructure

### Exit Criteria

The framework can execute a complete processing pipeline, even if individual stages are still placeholders.

Status: Satisfied by the M1 core pipeline (`configuration`, `project-loading`,
`provider-initialization`, `placeholder-processing`) and automated foundation tests.

---

# Milestone M2 — Subtitle Generation
- Done? [x]

## Goals

Produce accurate subtitle timing.

### Planned Features

- [x] Whisper provider
- [x] Faster-Whisper provider
- [x] Forced alignment
- [x] JSON export
- [x] Segment SRT export
- [x] Automatic line wrapping
- [x] Metadata preservation
- [x] Lyrics parsing
- [x] Subtitle validation

### Exit Criteria

Subtitle generation is production-ready.

Status: Satisfied by the `subtitle-alignment` and `subtitle-export` pipeline
stages, the provider-based Alignment Engine (`heuristic`, `stable-whisper`,
`faster-whisper`; see ADR-0001), FFMETADATA1 metadata preservation and
automated tests covering lyrics parsing, alignment, validation and export.

---

# Milestone M3 — Video Rendering
- Done? [x]

## Goals

Generate complete lyric videos.

### Planned Features

- [x] Rendering Engine
- [x] FFmpeg backend
- [x] MoviePy integration
- [x] Background colors
- [x] Background images
- [x] Background videos
- [x] Video looping
- [x] Automatic scaling
- [x] Text rendering
- [x] Automatic font scaling
- [x] Configurable layouts
- [x] Metadata embedding

### Exit Criteria

The framework can generate complete lyric videos from configuration files.

Status: Satisfied by the Rendering Engine (Layout Engine, Text Renderer and
interchangeable FFmpeg/MoviePy backends behind a deterministic `RenderBackend`
seam with a dry-run default and automatic backend selection; see ADR-0002),
the `rendering` pipeline stage, and FFMETADATA/cover-art metadata embedding.
The `mpf` CLI generates a complete lyric video from a configuration file
(`--render/--no-render`, `--preview`, `--backend`).

---

# Milestone M4 — Karaoke Rendering
- Done? [ ]

## Goals

Support professional karaoke videos.

### Planned Features

- [ ] Word-level timing
- [ ] Karaoke rendering
- [ ] Multiple karaoke styles
- [ ] Style configuration
- [ ] Animation support
- [ ] Timing optimization

### Exit Criteria

Professional karaoke videos can be rendered automatically.

---

# Milestone M5 — Project Completion (v1.0.0)
- Done? [ ]

## Goals

Deliver the first stable release.

### Planned Features

- [ ] Stable CLI
- [ ] Documentation
- [ ] Default templates
- [ ] Example projects
- [ ] Packaging
- [ ] Comprehensive testing
- [ ] Release automation
- [ ] Performance improvements
- [ ] Bug fixing

### Exit Criteria

The framework is considered production-ready.

---

# Post-v1.0 Roadmap

The following features are intentionally postponed until after the first stable release.

---

## GUI
- Done? [ ]

### Planned Features

- [ ] Web interface
- [ ] Interactive editor
- [ ] Live preview
- [ ] Configuration editor
- [ ] Template management
- [ ] Drag-and-drop positioning
- [ ] Layer editor

---

## AI-Assisted Content Generation
- Done? [ ]

### Planned Features

- Background image generation
- Background animation generation
- Prompt generation
- Lyrics analysis
- Mood analysis
- Audio analysis
- Automatic visual suggestions
- Multiple AI providers

---

## Translation
- Done? [ ]

### Planned Features

- [ ] Automatic lyric translation
- [ ] Multi-language subtitle generation
- [ ] AI translation providers
- [ ] Translation review workflow

---

## Rendering Improvements
- Done? [ ]

### Planned Features

- [ ] Additional rendering backends
- [ ] Hardware auto-detection
- [ ] Automatic renderer selection
- [ ] Render preview mode
- [ ] Render caching
- [ ] Incremental rendering

---

## Advanced Project Editing
- Done? [ ]

### Planned Features

- [ ] Image overlays
- [ ] Text overlays
- [ ] Layer management
- [ ] Project save/load
- [ ] Visual project editor

---

## Plugin Ecosystem
- Done? [ ]

### Planned Features

- [ ] External providers
- [ ] Plugin SDK
- [ ] Plugin discovery
- [ ] Third-party renderers
- [ ] Third-party AI providers

---

## Future Ideas

Potential future extensions include

- Additional subtitle formats
- Additional metadata formats
- Batch processing
- REST API
- Remote rendering
- Distributed rendering
- Asset management
- Timeline editing
- Cloud providers (optional)
- Additional export targets
- Possibility to skip the alignment process entirely and supply an already existing SRT file as subtitle input instead
- Rename `rendering.text.font.mode` to `rendering.text.font.auto_mode` (boolean), since the current enum offers no way to disable auto mode other than removing the key
- Tolerate lyric/audio alignment mismatches instead of always aborting: a `max_alignment_failures_allowed` subtitle setting (percentage of total segments, or an absolute count) that lets the pipeline continue past `SubtitleBuilder`'s "fewer words than expected" check for the affected segment(s) at the cost of timing quality, falling back to an approximation (e.g. heuristic-style interpolation) for the mismatched segment only. `0` (the default) preserves today's hard-fail behaviour.

Items in this section are intentionally unordered.

They represent possible future directions rather than committed features.

---

# Out of Scope

The project does not aim to become

- a Digital Audio Workstation (DAW)
- a general-purpose video editor
- an image editing suite
- an AI model training platform

These objectives are intentionally excluded from the roadmap.

---

# Roadmap Maintenance

The roadmap is expected to evolve over time.

New features should be added only after evaluating

- architectural impact
- maintenance cost
- long-term value

Major architectural changes should be documented through ADRs.
