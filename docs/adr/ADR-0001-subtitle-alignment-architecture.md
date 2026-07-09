# ADR-0001: Subtitle Alignment Provider Architecture

**Status:** Accepted

---

## Context

Milestone M2 requires forced alignment between user-supplied lyrics and an
audio recording (FR-007 - FR-013), producing an internal subtitle model that
can later be exported (FR-014 - FR-018) and, in future milestones, rendered.

Real forced-alignment backends (`stable-ts` on top of OpenAI Whisper or
Faster-Whisper) are heavy, GPU-friendly but optional dependencies. The
"Offline First" and "Deterministic Processing" principles require that the
framework's core functionality remain usable without any such dependency
installed, and that automated tests remain fast, deterministic and free of
network access or external AI services (see `docs/testing.md`).

A decision was needed on how alignment backends are selected, how their heavy
dependencies are isolated from the rest of the framework, and what the default
behaviour should be when no backend is configured.

---

## Decision

Subtitle alignment is implemented behind an `AlignmentProvider` interface
(`src/media_production_framework/alignment.py`), following the same
provider-based extension pattern established for other engines (TC-022).

Three providers are introduced:

- **`heuristic`** (default) - a fully offline, deterministic provider that
  distributes timing across the known audio duration proportionally to token
  length. It has no third-party dependency and is used as the default
  provider and throughout the automated test suite.
- **`stable-whisper`** - forced alignment using an OpenAI Whisper model via
  the optional `stable-ts` package.
- **`faster-whisper`** - forced alignment using a Faster-Whisper model, also
  via `stable-ts`.

The heavy dependencies for the Whisper-based providers are imported lazily
inside the provider's `align()` method rather than at module import time. This
keeps `media_production_framework.alignment` importable without either
dependency installed; only selecting one of these providers at runtime
requires the corresponding optional extra (`pip install
media-production-framework[whisper]` or `[faster-whisper]`).

`AlignmentProviderFactory` resolves a provider by name and constructs it with
the configured model. `SubtitleBuilder` then maps the provider's word-level
timings back onto the user's original lyric line segmentation (FR-010),
producing a `SubtitleDocument`.

The `provider` name is a plain configuration string; the Configuration Engine
does not import or depend on the Alignment Engine (a business engine), so
unknown or misconfigured provider names surface as an `AlignmentError` at
alignment time rather than at configuration-load time.

---

## Alternatives Considered

- **Bundling `stable-ts` as a required dependency.** Rejected: it pulls in
  PyTorch and large model-loading machinery, violating "Offline First" for
  users who only need line-level subtitle timing, and would make automated
  tests slow and environment-dependent.
- **A single alignment provider with a `backend` flag baked into one class.**
  Rejected: it would not satisfy FR-009 (multiple interchangeable alignment
  providers) or the provider-based extensibility goals in the implementation
  plan (TC-022, NFR-034).
- **No offline default; require a configured provider.** Rejected: it removes
  a fast, dependency-free path for automated testing and for users who only
  need approximate timing.

---

## Consequences

- The framework's core pipeline remains fully functional and testable without
  any ML dependency installed.
- Adding a new alignment backend (e.g. a cloud speech API) means implementing
  `AlignmentProvider` and registering it in `AlignmentProviderFactory` without
  modifying existing providers (FR-009, NFR-034).
- The heuristic provider's timing is approximate (proportional to token
  length) and is not intended for production-quality karaoke timing; users
  who need accurate word-level timing must install and configure a
  Whisper-based provider.
- `pyproject.toml` gained two optional dependency groups (`whisper`,
  `faster-whisper`) in addition to `dev`.
