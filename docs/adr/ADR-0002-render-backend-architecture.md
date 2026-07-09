# ADR-0002: Render Backend Architecture

**Status:** Accepted

---

## Context

Milestone M3 introduces the Rendering Engine (FR-023 - FR-055): the framework
must turn the subtitle model produced by the Alignment Engine, together with
project media and configuration, into a finished lyric video.

Rendering is fundamentally different from the work in earlier milestones. M2 was
pure data transformation (text in, SRT/JSON out) and could run its entire test
suite with zero heavy dependencies. M3, by contrast, must drive external tooling
to emit an actual video file:

- **FFmpeg** (invoked as a subprocess) and, optionally, **MoviePy** are the
  load-bearing renderers. FR-029 requires interchangeable backends, and
  FR-030/FR-031 require automatic selection and fallback between them.
- **Text measurement and rasterization** (automatic font scaling, FR-038 -
  FR-040; outlines/shadows, FR-047) need real pixel-level font metrics, not
  character counts.
- Background rendering has three source types (colour/image/video) with looping,
  trim-to-duration and aspect-ratio-preserving scaling (FR-049 - FR-055).

At the same time, `docs/testing.md` mandates fast, deterministic, offline tests,
and the "Offline First" and "Deterministic Processing" principles (also the
basis of ADR-0001) require the framework to remain importable and useful without
any heavy rendering dependency installed. A 1080p encode cannot run inside a
unit test.

A decision was needed on how rendering backends are structured, how their heavy
dependencies are isolated, how the pipeline stays testable, and how text is
measured and rasterized.

---

## Decision

### 1. Separate the render *plan* from its *execution*

Rendering is expressed as two steps behind a `RenderBackend` interface
(`src/media_production_framework/render_backends.py`):

- **`plan(job) -> RenderPlan`** builds a fully resolved, deterministic
  description of the render — resolution, fps, duration, the background
  operation, encoder settings, metadata and the exact command (`argv`) the
  backend would run — *without invoking anything*.
- **`render(job) -> RenderResult`** executes that plan and reports the outcome.

The rendering domain objects (`rendering.py`) — `RenderJob`, `RenderSettings`,
`RenderPlan`, `BackgroundOperation`, `RenderProgress`, `RenderResult` — are all
frozen, so a plan produced for a given job is reproducible and can be asserted
against directly.

### 2. A deterministic dry-run backend is the default

`DryRunRenderBackend` is the rendering analogue of M2's offline `heuristic`
alignment provider. It produces the full `RenderPlan` (and the symbolic command
it would run) but performs no I/O. It is the default backend, keeps the pipeline
end-to-end testable, and lets unit tests assert command construction with **no
FFmpeg, no MoviePy and no file written**.

`RenderBackendFactory` resolves a backend by name and `RenderService` coordinates
selection, planning and execution — mirroring the
`AlignmentProviderFactory` / `AlignmentService` shape from ADR-0001. Backend
names are plain configuration strings; unknown or unavailable backends surface as
a `RenderingError` at render time, not at configuration-load time.

### 3. Heavy backends are isolated and lazily imported

The real FFmpeg and MoviePy backends (added in later M3 parts) import their heavy
dependencies lazily inside their execution paths, exactly like the Whisper-based
alignment providers. `render_backends.py` therefore imports cleanly without any
renderer installed. Their **command construction** is unit-tested through the
`RenderPlan`/`argv`; their **execution** is covered only by a handful of
integration tests guarded by a skip marker (`@pytest.mark.ffmpeg`,
skip-if-unavailable) that render a ~1 s clip to a temporary file and assert it
exists and is non-empty (NFR-020).

### 4. FFmpeg is driven as a subprocess; Pillow is used for text

FFmpeg is invoked as an external process (its CLI is the stable, well-documented
contract and avoids binding to a specific `ffmpeg`-python wrapper). **Pillow** is
adopted for text measurement and rasterization: it provides deterministic font
metrics and glyph rendering needed by automatic font scaling and the text
renderer. Pillow is exposed as an optional `render` extra in `pyproject.toml`
(mirroring the `whisper`/`faster-whisper` extras) rather than folded into the
core dependencies, keeping a Pillow-free install viable for users who only need
subtitle generation.

---

## Alternatives Considered

- **A single rendering class with a `backend` flag.** Rejected: it would not
  satisfy FR-029 (interchangeable backends) or FR-030/FR-031 (selection and
  fallback), and it would entangle FFmpeg and MoviePy specifics in one place.
- **Executing FFmpeg directly inside tests.** Rejected: it violates the
  fast/deterministic/offline testing requirement and would make the suite
  depend on an external binary. The plan/execute split gives the same
  confidence in command construction without running anything.
- **Binding to a Python FFmpeg wrapper library** (e.g. `ffmpeg-python`).
  Rejected: it adds a required dependency and an extra abstraction over a CLI
  that is already stable; a subprocess call keeps the contract explicit and
  inspectable via the plan's `argv`.
- **Rendering text with FFmpeg's `drawtext` only.** Rejected as the primary
  path: pixel-accurate automatic font scaling and layered outline/shadow effects
  (FR-038 - FR-040, FR-047) are far more controllable with real font metrics,
  which Pillow provides deterministically.
- **Making Pillow a core dependency.** Rejected: it is unnecessary for the
  subtitle-only workflow; an optional extra preserves "Offline First" while
  still making rendering a one-command install.

---

## Consequences

- The core pipeline and its tests remain fully functional and deterministic with
  no rendering dependency installed; the default `DryRunRenderBackend` exercises
  the entire seam offline.
- Adding a new rendering backend (FFmpeg, MoviePy, or a future GPU/cloud
  renderer) means implementing `RenderBackend` and registering it in
  `RenderBackendFactory` without modifying existing backends (FR-029, FR-055,
  NFR-034).
- Command construction is verifiable in unit tests via `RenderPlan.argv`, while
  actual encoding is validated by a small number of skip-guarded integration
  tests.
- `pyproject.toml` gains an optional `render` extra (`Pillow`); selecting a real
  backend or automatic font scaling requires installing it.
- `KaraokeConfiguration` is parsed, validated and reserved now, but karaoke
  *rendering* remains out of scope until Milestone M4; this ADR governs the
  backend seam that M4 will also build on.
