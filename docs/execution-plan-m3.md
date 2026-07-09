# Execution Plan — Milestone M3 (Video Rendering)

**Status:** Temporary planning artifact — **delete once M3 is complete.**
**Author:** Opus 4.8 (planning pass, effort: Extra)
**Date:** 2026-07-09

> This document is **not** authoritative architecture. The authoritative sources
> remain `docs/implementation-plan.md` and the ADRs. This file exists only to
> (a) justify why M3 must be split and (b) hand a downstream implementation model
> a concrete, session-sized breakdown with recommended agent settings per part.
> It is safe to `git rm` this file after M3 ships.

---

## 1. TL;DR

- **M3 is roughly 3–4× the implementation footprint of M2, and >4× its
  testing/verification difficulty.** A single session would exceed the context
  budget (M2 alone reached ~50%), creating exactly the context-loss /
  hallucination risk we want to avoid.
- **Recommendation: split M3 into 6 sequential parts**, each ≤ one M2-sized unit
  and each leaving the test suite green.
- **Part 1 is the keystone** (backend seam + config + domain + ADR-0002) and
  should be done by the strongest model. The remaining parts are well-specified
  fill-in against a stable interface and can be handed to cheaper models.
- **Spend the expensive model only where architectural or subprocess-correctness
  risk is high** (Parts 1 and 4). Everything else is Sonnet 5 / Opus 4.7 at
  Medium effort.

---

## 2. Why M3 is a large multiple of M2 (effort estimate)

### 2.1 What M2 actually was (the reference unit)

M2 (already implemented, uncommitted in the working tree) is:

| Metric | M2 actual |
|---|---|
| New source modules | 8 (`alignment` 295, `subtitle_export` 95, `lyrics` 71, `subtitle_validation` 70, `subtitles` 50, `metadata` 48, `audio` 48, `text_wrapping` 44) |
| New source LOC | ~720 |
| Test LOC | 349 (30 tests) |
| ADRs | 1 (ADR-0001) |
| External runtime deps *actually exercised* | **0** — the default `heuristic` provider is pure-Python; `stable-ts`/`faster-whisper` are lazy-imported and never run in tests |
| Side effects | text in → text out (SRT/JSON); a silent 4 s WAV fixture |
| Determinism | trivial — proportional arithmetic, byte-for-byte reproducible |

The reason M2 fit in one session is that **its real work is pure data
transformation** and the heavy providers are stubbed behind a lazy seam.

### 2.2 Why M3 is fundamentally heavier (not just "more lines")

M3's *entire purpose* is to produce a real video file. There is no pure-Python
equivalent that emits an MP4, so the difficulty is qualitatively different:

1. **External tooling is the core, not optional.** FFmpeg (subprocess) and
   MoviePy are load-bearing. M2 could pass all tests with zero heavy deps; M3
   cannot render anything without them.
2. **Two interchangeable backends** (FFmpeg + MoviePy) behind a provider
   interface, plus **automatic selection and fallback** (FR-029/030/031,
   NFR-013/014) — logic M2 never needed.
3. **Seven cooperating sub-renderers** per implementation-plan §4.7: Layout
   Engine, Background Renderer, Text Renderer, Video Composer, Encoder, Metadata
   Writer (Karaoke Renderer is M4). Each has its own config and tests.
4. **Background rendering** with 3 source types (color / image / video), video
   **looping + trim-to-duration** and **aspect-ratio-preserving scale/pad**
   (FR-049–FR-055) — fiddly filtergraph work.
5. **Automatic font scaling** (FR-038/039/040): a search for the largest font
   size whose wrapped text fits `max_lines` within a container width expressed as
   a percentage of video width. This needs **real font metrics** (pixel
   measurement, not character counts), i.e. a new dependency and a determinism
   concern.
6. **~4–5× larger config surface.** The `subtitles` section had ~7 leaf options.
   The templates already define `rendering.{video,background,text,karaoke}` +
   `ffmpeg` with ~30 leaf options, each needing parsing, validation, defaults and
   a domain object.
7. **Progress reporting** for a long-running encode (FR-032, NFR-011) — parse
   FFmpeg progress and emit events. New concern.
8. **Metadata embedding** including cover art (FR-057/058/059) — M2 only *read*
   FFMETADATA; M3 must *write* it back into the container.
9. **Preview rendering** reusing the same pipeline (FR-033/034).
10. **Testing is much harder.** You cannot render 1080p in a unit test, and
    `docs/testing.md` mandates fast, deterministic, offline tests. This forces a
    deliberate **testable seam** (see §3) — the single most important design
    decision in M3.

### 2.3 Estimate

| Dimension | M2 | M3 (estimated) | Ratio |
|---|---|---|---|
| New source modules | 8 | ~14–18 | ~2× |
| New source LOC | ~720 | ~2,200–2,800 | ~3–4× |
| Distinct external integrations exercised | 0 | 3 (ffmpeg subprocess, MoviePy, Pillow) | n/a (new class of work) |
| Test difficulty | low (pure arithmetic) | high (needs fakes/seams + skip-guarded integration) | >4× |
| New ADRs | 1 | 1–2 | ~same |

**Conclusion:** M3 ≈ **3–4 M2-units of implementation** and clearly exceeds a
single safe session. Split it.

---

## 3. The keystone design: a deterministic, testable render seam

Every part below depends on one idea, established in Part 1 and mirrored on
ADR-0001's reasoning (offline-first, deterministic, heavy deps lazy & optional):

> **Separate the *plan* from the *execution*.** A `RenderBackend` takes a fully
> resolved, deterministic **`RenderPlan`** (resolution, duration, background
> operation, per-segment text layout, encoder args, metadata args) and produces
> output. A default **`DryRunRenderBackend`** returns the `RenderPlan` (and the
> exact argv / filtergraph it *would* run) **without invoking anything.**

This is the M3 analogue of M2's `heuristic` provider:

- **Unit tests** assert the `RenderPlan` and the constructed FFmpeg argv for
  known inputs — fully deterministic, no subprocess, no Pillow rasterization
  required for the command-construction tests.
- **The real FFmpeg/MoviePy backends** are exercised only by a handful of
  integration tests guarded by a skip marker (`@pytest.mark.ffmpeg`,
  skip-if-unavailable) that render a ~1 s clip to a temp file and assert it
  exists and is non-empty (NFR-020).

Get this seam right in Part 1 and the rest becomes safe fill-in.

---

## 4. Part breakdown

Dependency order is strict: **1 → 2 → 3 → 4 → (5) → 6**. Part 5 (MoviePy) is the
only optional/deferrable part — the FFmpeg backend alone satisfies the M3 exit
criterion; MoviePy exists to satisfy FR-029 "multiple backends" and can slip to a
follow-up if plan usage is tight.

Each part targets **≤ ~40–50% context** (one M2-unit or less), runs the existing
suite green before and after, updates `CHANGELOG.md`, and is committed on its own.

---

### Part 1 — Rendering foundation: config, domain objects, backend seam + ADR-0002  ⭐ keystone

**Goal:** Establish every interface the later parts fill in, plus the deterministic
dry-run backend, without executing any renderer.

**Covers:** FR-024–FR-028 (resolution/fps/bitrate/sample-rate/codec config),
config groundwork for FR-035–FR-055, the provider architecture for FR-029.

**Do:**
- **Config** (`configuration.py`): add frozen dataclasses + parsing/validation
  for the `rendering` and `ffmpeg` sections. Mirror the existing
  `SubtitleConfiguration` style exactly (per-key type checks, `ConfigurationError`
  with actionable messages, defaults as module constants):
  - `VideoConfiguration` (resolution `"1920x1080"` → `(1920, 1080)`, fps, bitrate str)
  - `BackgroundConfiguration` (type enum `color|image|video`, source, loop bool)
  - `TextConfiguration` / `FontConfiguration` (container width/padding as `"80%"`
    → fraction; font name/size/max_lines/min_size/max_size; color hex validation;
    bold/italic; outline/shadow px; vertical `top|middle|bottom`; horizontal
    `left|center|right`)
  - `FfmpegConfiguration` (preset enum, crf 0–51, sample_rate)
  - `KaraokeConfiguration` — **parse & validate only, then reserve.** Karaoke
    *rendering* is M4; store the values so the hook exists.
  - Add `rendering: RenderConfiguration | None` and `ffmpeg: FfmpegConfiguration`
    to `ProjectConfiguration`.
- **Domain** (new `rendering.py` or `render_model.py`): `RenderSettings`,
  `RenderJob` (bundles subtitle document + assets + settings), `RenderResult`
  (output path, duration, backend name, success), `RenderProgress`, and a
  `RenderPlan` (the deterministic description described in §3).
- **Backend seam** (new `render_backends.py`): `RenderBackend` Protocol
  (`name`, `render(job) -> RenderResult`, `plan(job) -> RenderPlan`), a
  `RenderBackendFactory`, and `DryRunRenderBackend` (default) that builds the
  `RenderPlan` and records the argv it would run. Follow the
  `AlignmentProvider` / `AlignmentProviderFactory` / `AlignmentService` shape
  from `alignment.py`. Heavy backends are added in Parts 4–5 with **lazy imports**.
- **Events** (`events.py`): add `RenderingStartedEvent`,
  `RenderingProgressEvent`, `RenderingCompletedEvent`,
  `PreviewRenderingCompletedEvent`.
- **ADR-0002** (`docs/adr/ADR-0002-render-backend-architecture.md`): document the
  backend-provider decision, the plan/execute split, the dry-run testing
  strategy, the choice of Pillow for text measurement/rasterization (Part 2/3),
  and FFmpeg-as-subprocess vs library. Mirror ADR-0001's structure
  (Context / Decision / Alternatives / Consequences) and cite the FRs.
- **Optional deps** (`pyproject.toml`): add extras `render = ["Pillow"]` (or fold
  Pillow into core — decide in the ADR) mirroring the `whisper` extras pattern.

**Tests:** config parsing incl. every validation error path; resolution/percent/
color parsers; domain object construction; `DryRunRenderBackend.plan()` returns
the expected `RenderPlan` for a tiny project. All pure-Python, deterministic.

**Done when:** suite green; pipeline still ends in the placeholder stage; no
renderer executed anywhere.

**Recommended agent settings:** **Opus 4.8, effort High** (fallback: Opus 4.7
High). *Rationale:* this part fixes the interfaces the whole milestone builds on;
interface mistakes here are expensive to unwind later.

---

### Part 2 — Layout Engine + automatic font scaling (pure logic)

**Goal:** Deterministically compute, for each subtitle segment, the wrapped lines,
the chosen font size, and the text-block anchor position — no rasterization, no I/O.

**Covers:** FR-035–FR-046 (font family/style/size/color config surface consumed
here), **FR-038/039/040** (auto font sizing), FR-042/043/044 (alignment /
positioning / container width), FR-045/046 (wrap without splitting words /
preserve timing).

**Do:**
- New `layout.py`. Introduce a `TextMeasurer` Protocol
  (`measure(text, font, size) -> (width_px, height_px)`) so the algorithm is
  independent of the rasterizer. Provide the Pillow-backed measurer **and** a
  deterministic fake measurer for tests.
- Font scaling: binary-search the largest size in `[min_size, max_size]` whose
  word-preserving wrap (reuse `text_wrapping.wrap_text`, but measure in **pixels**
  against the container width, not characters) fits within `max_lines`. If nothing
  fits, clamp to `min_size` and wrap as best as possible (never split words).
- Compute the block bounding box and its (x, y) anchor from `vertical` /
  `horizontal` / container padding, in output-pixel space.
- Output a `SegmentLayout` (lines, size, box, anchor) list — feeds Parts 3 & 4.

**Tests:** scaling picks the expected size for known widths; longest segment
governs the size (FR-039); wrap never splits a word; anchor math for each
alignment/vertical combination. All against the fake measurer → deterministic.

**Done when:** suite green; layout is a pure function testable without Pillow.

**Recommended agent settings:** **Sonnet 5, effort Medium** (fallback: Opus 4.7
Medium). *Rationale:* self-contained, math-heavy, guarded by strong deterministic
tests against a stable interface — ideal cheaper-model work.

---

### Part 3 — Text Renderer (rasterize overlays via Pillow)

**Goal:** Turn each `SegmentLayout` into a transparent RGBA overlay image (text +
outline + shadow, color, bold/italic).

**Covers:** FR-041 (colours), FR-047 (outline/shadow/readability), FR-036 (styles),
FR-048 (new effects addable without touching existing code).

**Do:**
- New `text_renderer.py`. Render each segment's lines with Pillow `ImageFont` at
  the layout-chosen size, apply outline (stroke) and shadow, honour color and
  bold/italic. Bundle one small open-licensed test font under `tests/` for
  determinism (do **not** depend on system fonts in tests; ASM-007 covers runtime).
- Return overlays keyed by segment (image bytes/handle + placement) for the
  compositor. Keep effect implementations small and additive (FR-048).

**Tests:** overlay has expected dimensions and anchor; non-empty pixels where text
is; deterministic byte hash for the bundled font at a fixed size; outline/shadow
change output as expected.

**Done when:** suite green; overlays render deterministically from a bundled font.

**Recommended agent settings:** **Sonnet 5, effort Medium**. *Rationale:* bounded
Pillow work against the Part 2 output; easy to verify visually and by hash.

---

### Part 4 — FFmpeg backend: background + composition + encode + progress  ⭐ correctness-critical

**Goal:** Implement the real `FfmpegRenderBackend` end-to-end.

**Covers:** FR-023, FR-024–FR-028, FR-029/031, FR-032, FR-049–FR-055, NFR-011,
NFR-014, NFR-020.

**Do:**
- New `ffmpeg_backend.py`. Build the FFmpeg command/filtergraph from the
  `RenderPlan`:
  - **Background:** color (`lavfi color=`), image (`-loop 1`), video (`-stream_loop`
    + `-t` **trim to exact duration**, FR-052/053), all **scaled/padded preserving
    aspect ratio** (FR-054).
  - **Overlay** the Part 3 timed text overlays; **map audio**; apply encoder
    settings (codec/bitrate/fps/preset/crf/sample_rate).
  - Locate the `ffmpeg` binary; **probe availability**; if unavailable, raise a
    `RenderingError` that the factory can use to fall back (FR-031).
  - Execute via subprocess with `-progress pipe:1`; parse progress →
    `RenderingProgressEvent`. Verify the output file exists and is non-empty
    before reporting success (NFR-020).
- Register the backend in `RenderBackendFactory` (lazy import — the module must
  import without ffmpeg present, exactly like the whisper providers).

**Tests:** the **command/filtergraph construction** is unit-tested via the
`RenderPlan` and an argv assertion for known inputs (no execution). **One**
integration test behind `@pytest.mark.ffmpeg` (skip if binary missing) renders a
~1 s clip to `tmp_path` and asserts it exists & non-empty. Progress parser tested
against captured sample `-progress` text.

**Done when:** unit suite green with no ffmpeg present; integration test passes
where ffmpeg is installed.

**Recommended agent settings:** **Opus 4.7, effort High** (fallback: Opus 4.8
Medium). *Rationale:* filtergraph correctness, loop/trim/scale edge cases,
fallback logic and progress parsing are the highest-bug-density work in M3.

---

### Part 5 — MoviePy backend + automatic backend selection  (optional / deferrable)

**Goal:** A second interchangeable backend and the auto-select/fallback policy.

**Covers:** FR-029 (multiple backends), FR-030 (auto selection), FR-031
(fallback), NFR-013/014.

**Do:**
- New `moviepy_backend.py` implementing the same `RenderBackend` interface against
  the `RenderPlan`. Lazy import; add `moviepy` optional extra to `pyproject.toml`.
- `RenderBackendFactory` selection: config value (`auto` | `ffmpeg` | `moviepy`);
  `auto` probes availability, prefers FFmpeg, falls back to MoviePy (or the next
  compatible backend). Test with **fake backends** so no heavy dep is needed.

**Tests:** selection/fallback logic with fake backends (deterministic); MoviePy
execution behind a skip marker.

**Done when:** suite green; selection/fallback covered without installing MoviePy.

**Recommended agent settings:** **Sonnet 5, effort Medium**. *Rationale:* the
pattern is fixed by Part 4; this is adapter + policy work against a stable seam.
*If plan usage is tight, defer this part — FFmpeg alone meets the exit criterion.*

---

### Part 6 — Pipeline integration, metadata embedding, preview, CLI, docs

**Goal:** Wire rendering into the pipeline and finish the milestone.

**Covers:** FR-023 (end-to-end), FR-033/034 (preview), FR-057/058/059 (metadata
embedding + cover art), FR-005/032 (progress surfaced).

**Do:**
- Replace `RenderingPlaceholderStage` with a real `RenderingStage` that **skips
  gracefully** when `output.video` is unset or rendering is disabled (mirror
  `SubtitleAlignmentStage`'s skip pattern), builds a `RenderJob` from config +
  `context.subtitle_document` + assets, selects a backend, renders, stores the
  `RenderResult` in `context.artifacts`, and publishes the render events.
- **Metadata Writer** (FR-057/058/059): extend the FFmpeg command to embed
  `SongMetadata` (via a temp FFMETADATA file) and cover art; preserve multi-line
  lyrics where the container supports it. Reuse the existing `MetadataParser`
  output — no new parsing.
- **Preview** (FR-033/034): a `preview=True` low-res/fast path reusing the same
  backend and pipeline; publish `PreviewRenderingCompletedEvent`.
- **CLI** (`main.py`): add `--render / --no-render`, `--preview`, optional
  `--backend`; handle `RenderingError` like `AlignmentError`.
- **Docs:** update `CHANGELOG.md`; flip M3 → `[x]` in `roadmap.md` with an exit
  note; update `docs/capabilities.md`; cross-link ADR-0002. Register render
  backends as `ProviderDescriptor`s in `ProviderRegistry` for discovery (FR-094).

**Tests:** end-to-end pipeline with the `DryRunRenderBackend` yields a
`RenderResult` and the expected argv incl. metadata args; skip behaviour when no
`output.video`; a `@pytest.mark.ffmpeg` end-to-end that produces a real file.

**Done when:** full suite green; the framework generates a lyric video from a
config file (implementation-plan M3 exit criterion).

**Recommended agent settings:** **Opus 4.7, effort Medium** (fallback: Sonnet 5
Medium). *Rationale:* broad but well-scoped wiring across many files; the
end-to-end dry-run test keeps it deterministic and low-risk.

---

## 5. Summary: parts, dependencies, recommended settings

| Part | Scope | Depends on | Model | Effort | Context budget |
|---|---|---|---|---|---|
| 1 ⭐ | Config + domain + backend seam + ADR-0002 | — | **Opus 4.8** | **High** | ~1 M2-unit |
| 2 | Layout Engine + auto font scaling | 1 | Sonnet 5 | Medium | ~0.7 M2-unit |
| 3 | Text Renderer (Pillow overlays) | 2 | Sonnet 5 | Medium | ~0.6 M2-unit |
| 4 ⭐ | FFmpeg backend (bg/compose/encode/progress) | 1, 3 | **Opus 4.7** | **High** | ~1 M2-unit |
| 5 | MoviePy backend + auto-selection *(optional)* | 4 | Sonnet 5 | Medium | ~0.6 M2-unit |
| 6 | Pipeline + metadata embed + preview + CLI + docs | 4 (5) | Opus 4.7 | Medium | ~0.8 M2-unit |

⭐ = spend the expensive model here (architecture / subprocess correctness).
Parts 2, 3, 5 are the plan-usage savings: cheaper model, stable interface, strong
deterministic tests.

**Merge/split levers if a session runs hot or cold:**
- If the executor model is strong and context allows, **2 + 3 can merge** (layout
  → rasterize is one coherent flow).
- If Part 4 feels too large in one session, split off **progress parsing +
  fallback** into its own sub-session after the happy-path render works.
- **Part 5 is the release valve** — defer it entirely if needed.

---

## 6. Per-session protocol (for the executing model)

Give each part's agent this standing instruction:

1. **Read first (per `docs/developer-guide.md` order):**
   `docs/implementation-plan.md` §4.7 + the FRs your part covers, `ADR-0001`,
   `ADR-0002` (once Part 1 writes it), `docs/coding-standards.md`,
   `docs/testing.md`. Then read this file's section for your part.
2. **Match the M2 patterns already in the tree** — they are the reference
   implementation: `alignment.py` (Protocol + Factory + Service, lazy heavy
   imports), `subtitle_export.py` (Protocol + concrete exporters), pipeline stages
   in `pipeline.py` (graceful skip), config in `configuration.py` (per-key
   validation). Frozen dataclasses, full type hints, English docstrings/messages,
   `ruff` line-length 100.
3. **Keep the seam:** default to the deterministic dry-run/fake path; guard every
   real ffmpeg/moviepy execution behind a skip marker. No test may require a heavy
   binary to pass.
4. **Green before and after.** Run `python -m pytest -q` at the start and end.
   Update `CHANGELOG.md` under `[Unreleased]`. Commit the part on its own.
5. **Interpreter gotcha:** the project targets **Python 3.14** (`pyproject.toml`;
   note the plan text §TC-002 still says 3.12 — a doc inconsistency worth flagging
   but out of M3 scope). The code already uses 3.10+ syntax such as
   `zip(..., strict=True)`. Run on the target interpreter, **not** a 3.9 runtime,
   or those constructs will falsely appear broken (3 M2 tests fail today for
   exactly this reason).

---

## 7. Explicitly out of scope for M3

- **Karaoke rendering (M4).** Part 1 parses/validates/reserves `rendering.karaoke`
  config, but word-highlighting rendering is M4. The subtitle model already
  carries word-level timing, so the hook exists.
- GPU/hardware-accelerated backends, distributed/live-preview rendering — post-1.0
  per the roadmap.
- AI-assisted background generation (M-AI, post-1.0).
