# Developer Guide

**Document Version:** v0.1.0  
**Status:** Living Document

---

# Purpose

This document provides a minimal entry point for developers and AI agents.

It summarizes the project structure and points to the authoritative documentation.

It intentionally avoids duplicating information maintained elsewhere.

---

# Read Order

For architecture-related work:

1. `docs/implementation-plan.md`
2. Relevant ADRs (`docs/adr/`)
3. `docs/coding-standards.md`

For implementation work:

1. `docs/project-structure.md`
2. `docs/testing.md`
3. `CONTRIBUTING.md`

---

# Project Principles

Always prioritize

- readability
- maintainability
- extensibility
- deterministic behaviour
- pragmatic engineering

Avoid unnecessary complexity.

---

# Architecture Summary

The framework consists of

- Foundation Components
- Domain Engines
- Domain Objects
- Processing Pipelines
- Provider Interfaces
- Event System

Business logic belongs inside engines.

Infrastructure remains behind providers.

Communication occurs through

- public APIs
- domain objects
- events

---

# Development Workflow

Before implementing a feature

1. Verify whether the Implementation Plan already defines the architecture.
2. Check for existing ADRs.
3. Reuse existing domain objects whenever practical.
4. Extend existing engines before creating new ones.

When architecture changes

- update the Implementation Plan
- create an ADR if the decision is significant
- update affected documentation

---

# Code Guidelines

- English only
- Type hints required
- Prefer dataclasses for business data
- Avoid hardcoded values
- Prefer provider abstractions
- Use structured logging
- Write tests for business logic

See `docs/coding-standards.md` for details.

---

# Testing

Every new business feature should include appropriate tests.

Avoid unit tests which doesn't bring a real benefit for coverage only.

Prefer

- unit tests
- deterministic behaviour
- isolated dependencies

See `docs/testing.md`.

---

# Documentation Ownership

| Document | Purpose |
|----------|---------|
| `docs/implementation-plan.md` | Architecture |
| `docs/capabilities.md` | Functional capabilities |
| `docs/coding-standards.md` | Coding conventions |
| `CONTRIBUTING.md` | Development workflow |
| `docs/testing.md` | Testing strategy |
| `docs/project-structure.md` | Repository organization |
| `docs/release-process.md` | Versioning and releases |
| `docs/adr/*` | Architectural decisions |

---

# Guiding Principle

When in doubt

- keep the architecture simple
- extend existing solutions
- document significant decisions
- optimize for long-term maintainability

---

# AI Agent Notes

When implementing new functionality

- prefer existing patterns over introducing new ones
- search for reusable domain objects before creating new classes
- search for existing providers before adding dependencies
- avoid duplicate utilities
- preserve architectural consistency over local optimization

If implementation and documentation disagree, the documentation is authoritative until explicitly revised.

---

# Current Development Phase

The authoritative development roadmap is maintained in `docs/roadmap.md`.

When working on the project

- implement features belonging to the current milestone
- avoid feature creep
- do not skip prerequisite infrastructure
- prefer completing existing milestones over starting future ones

Future milestone features may only be implemented when explicitly requested or when necessary to prepare the architecture.
