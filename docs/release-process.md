# Release Process

**Document Version:** v0.1.0  
**Status:** Living Document

---

# Purpose

This document defines the versioning and release strategy of the Media Production Framework.

---

# Versioning

The project follows Semantic Versioning.

```
MAJOR.MINOR.PATCH
```

Examples

```
0.1.0
0.4.3
1.0.0
2.1.1
```

---

# Version Increment Rules

## MAJOR

Increment when introducing breaking changes that are not backward compatible.

Examples

- incompatible API changes
- incompatible project format changes
- incompatible configuration changes

---

## MINOR

Increment when introducing significant new functionality while maintaining backward compatibility.

Examples

- new rendering capabilities
- new provider categories
- major new user-facing features

---

## PATCH

Increment for

- bug fixes
- small improvements
- documentation updates
- minor features
- internal refactorings

PATCH releases shall remain backward compatible.

---

# Pre-1.0 Development

Before version **1.0.0**

- architecture may evolve rapidly
- backward compatibility is not guaranteed
- migration effort is considered acceptable

Maintaining a clean architecture takes precedence over compatibility.

---

# Changelog

The project follows the principles of **Keep a Changelog**.

User-visible changes should be documented.

Internal implementation details may be omitted unless relevant to contributors.

---

# Release Checklist

Before creating a release

- update the changelog
- update version numbers
- execute automated tests
- verify documentation
- verify example projects
- verify templates
- verify packaging

---

# Release Artifacts

Future releases may include

- Python package
- standalone executables
- documentation bundle
- example projects

---

# Guiding Principle

Releases should prioritize stability, reproducibility and clear documentation over release frequency.
