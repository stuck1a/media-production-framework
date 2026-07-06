# Contributing

**Document Version:** v0.1.0  
**Status:** Living Document

---

# 1. Purpose

This document describes the development workflow for contributors to the Media Production Framework.

Its objective is to ensure a consistent development process while keeping the workflow lightweight and pragmatic.

---

# 2. Development Philosophy

Contributions should prioritize

- correctness
- maintainability
- readability
- consistency

Large architectural changes should be discussed before implementation whenever practical.

---

# 3. Branching Strategy

The project follows a lightweight Git workflow.

Typical branches include

- `main`
- feature branches
- bugfix branches
- hotfix branches (future)

Examples

```

feature/render-preview
feature/faster-whisper
bugfix/font-scaling

```

Feature branches should remain focused on a single topic.

---

# 4. Commits

Commits should represent one logical change.

Avoid combining unrelated modifications.

Commit messages should be concise and descriptive.

Examples

```

Add automatic font scaling

Fix subtitle timing export

Refactor rendering pipeline

```

---

# 5. Pull Requests

Pull requests should

- solve one problem
- remain reasonably small
- include updated documentation when required
- include tests whenever practical

Large pull requests should be split whenever possible.

---

# 6. Documentation

Documentation is part of the implementation.

Whenever architecture changes

- update the Implementation Plan
- update ADRs if necessary
- update affected documentation

Code and documentation should evolve together.

---

# 7. Versioning

The project follows Semantic Versioning.

```
MAJOR.MINOR.PATCH
```

During the pre-alpha phase (`0.x.y`), backward compatibility is not guaranteed.

Version numbers should only change when a meaningful project milestone has been reached.

They are **not** tied to the number of commits.

---

# 8. Changelog

The project follows the principles of **Keep a Changelog**.

User-visible changes should be recorded.

Internal refactorings may be omitted unless they affect developers.

---

# 9. Code Review

Reviews should focus on

- correctness
- readability
- maintainability
- architecture
- unnecessary complexity

Personal coding preferences should not dominate reviews.

---

# 10. Guiding Principle

Prefer constructive discussion over strict rules.

The objective is long-term project quality rather than rigid process compliance.
