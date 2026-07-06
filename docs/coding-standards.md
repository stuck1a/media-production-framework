# Coding Standards

**Document Version:** v0.1.0  
**Status:** Living Document

---

# 1. Purpose

This document defines the coding conventions used throughout the Media Production Framework.

The goal is to improve

- readability
- maintainability
- consistency
- extensibility

Whenever possible, existing Python standards should be followed instead of introducing project-specific rules.

---

# 2. General Principles

The codebase should prioritize

- readability
- simplicity
- maintainability
- explicitness
- consistency

Clever code is discouraged unless it provides measurable value.

Code is written for humans first and computers second.

---

# 3. Language

All source code shall be written in English.

This includes

- variable names
- function names
- class names
- comments
- documentation
- log messages
- exception messages

User-facing output may be localized in the future.

---

# 4. Naming Conventions

Follow standard Python naming conventions.

| Element | Convention | Example |
|----------|------------|---------|
| Module | snake_case | `subtitle_renderer.py` |
| Package | snake_case | `rendering` |
| Class | PascalCase | `SubtitleRenderer` |
| Function | snake_case | `render_video()` |
| Variable | snake_case | `subtitle_document` |
| Constant | UPPER_SNAKE_CASE | `DEFAULT_FONT_SIZE` |
| Enum | PascalCase | `RendererType` |
| Enum Member | UPPER_SNAKE_CASE | `CPU` |

Names should describe intent rather than implementation.

Avoid unnecessary abbreviations.

---

# 5. Project Structure

The project shall follow a feature-oriented structure.

Related classes should remain close together.

Avoid

- utility dumping grounds
- excessively large modules
- deep package hierarchies

Prefer cohesive modules over many tiny files.

---

# 6. SOLID Principles

SOLID principles should guide architectural decisions.

They shall not be applied dogmatically.

In particular

- avoid duplicated logic
- separate unrelated responsibilities
- depend on abstractions where practical
- prefer composition over inheritance

Small pragmatic violations are acceptable when they significantly simplify the implementation.

---

# 7. DRY

Duplicate business logic should be eliminated whenever practical.

Common functionality should be extracted into reusable components.

Do not introduce abstractions solely to eliminate a few repeated lines.

---

# 8. Type Hints

Type hints shall be used throughout the project.

Public APIs should always be fully typed.

Avoid using

- `Any`
- loosely typed dictionaries
- untyped collections

Prefer dedicated domain objects over primitive parameter lists.

---

# 9. Dataclasses

Business data should primarily be represented using dataclasses.

Domain objects should

- be strongly typed
- use meaningful field names
- remain serialization-friendly

Immutable dataclasses should be preferred whenever practical.

---

# 10. Functions

Functions should

- perform one primary task
- have descriptive names
- avoid unnecessary side effects

Avoid excessively long parameter lists.

Prefer domain objects when several related values belong together.

---

# 11. Classes

Classes should have one primary responsibility.

Very small helper classes are discouraged if they only wrap a few lines of code.

Likewise, excessively large classes should be decomposed into smaller components.

Pragmatism takes precedence over strict metrics.

---

# 12. Error Handling

Errors shall never fail silently.

Exceptions should

- provide meaningful messages
- preserve useful context
- avoid leaking implementation details

Recoverable errors should be handled close to their source.

---

# 13. Logging

Logging shall be used instead of print statements.

Log messages should

- describe what happened
- include relevant context
- avoid excessive verbosity

Sensitive information shall never be written to log files.

---

# 14. Configuration

Avoid hardcoded values.

Configuration should originate from

- YAML configuration
- constants
- provider configuration

Magic numbers should be replaced by named constants whenever practical.

---

# 15. Dependencies

External dependencies should remain isolated behind provider interfaces whenever practical.

Business logic should never directly depend on third-party libraries if an abstraction already exists.

---

# 16. Comments

Good code should be largely self-explanatory.

Comments should explain

- why something exists
- why a particular solution was chosen
- non-obvious implementation details

Comments should not describe what obvious code already expresses.

---

# 17. Documentation

Every public class, function and module should include concise documentation.

Documentation should explain intent rather than implementation.

Long implementation explanations belong in the implementation plan or ADRs.

---

# 18. Testing

Business logic should be testable without external services.

Whenever practical

- unit tests should isolate dependencies
- providers should be mockable
- deterministic behaviour should be preferred

---

# 19. Preferred Design Patterns

The project encourages established design patterns where they improve clarity.

Typical examples include

- Facade
- Factory
- Strategy
- Adapter
- Builder
- Observer
- Template Method
- Dependency Injection
- Repository (where appropriate)

Patterns should never be introduced solely for their own sake.

---

# 20. Code Review Checklist

Before submitting changes, verify that

- the code is readable
- naming is meaningful
- duplication has been minimized
- type hints are complete
- logging is appropriate
- configuration is not hardcoded
- tests have been updated where necessary
- documentation has been updated if architecture changed

---

# 21. Guiding Philosophy

The project values pragmatic engineering over theoretical purity.

The primary objective is to build software that remains understandable, maintainable and extensible for many years.

Every abstraction, dependency and design decision should provide measurable long-term value.

When in doubt, prefer the simpler solution.
