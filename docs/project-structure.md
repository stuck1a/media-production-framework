# Project Structure

**Document Version:** v0.1.0  
**Status:** Living Document

---

# Purpose

This document describes the intended directory structure of the Media Production Framework.

The objective is to keep the project organized, scalable and easy to navigate.

---

# Top-Level Structure

```
media-production-framework/
|
+-- src/
+-- tests/
+-- docs/
+-- templates/
+-- examples/
+-- assets/
+-- scripts/
+-- tools/
+-- .github/
|
+-- pyproject.toml
+-- README.md
+-- LICENSE
+-- CHANGELOG.md
+-- CONTRIBUTING.md
```

---

# Source Code

```
src/
    media_production_framework/
```

Contains the complete application source code.

No tests or documentation belong inside this directory.

---

# Tests

```
tests/
```

Contains

- unit tests
- integration tests
- end-to-end tests
- test resources

Test code should mirror the source code structure whenever practical.

---

# Documentation

```
docs/
```

Contains

- implementation plan
- ADRs
- coding standards
- developer documentation
- user documentation (future)

---

# Templates

```
templates/
```

Contains reusable YAML templates shipped with the application.

Examples

- default.yaml
- youtube.yaml
- karaoke.yaml

---

# Examples

```
examples/
```

Contains example projects demonstrating framework capabilities.

---

# Assets

```
assets/
```

Contains project assets required by the framework itself.

Examples include

- icons
- built-in fonts
- default backgrounds

User projects do not belong here.

---

# Scripts

```
scripts/
```

Contains helper scripts for development and maintenance.

These scripts are not part of the application itself.

---

# Tools

```
tools/
```

Contains standalone development utilities.

Examples

- migration tools
- benchmarking tools
- profiling tools

---

# Guiding Principles

The directory structure should remain

- shallow
- predictable
- feature-oriented
- easy to navigate

Large directories should be split only when complexity justifies the change.
