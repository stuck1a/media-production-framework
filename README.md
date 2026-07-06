# Media Production Framework

A modular, extensible framework for creating lyric videos, karaoke videos and other media production workflows.

> **Project Status:** Pre-Alpha

## Overview

The Media Production Framework is an open-source Python framework focused on automated media production.

The initial development focuses on generating high-quality lyric and karaoke videos from audio recordings and song lyrics. The architecture is designed to support future extensions such as AI-assisted workflows, additional rendering backends, plugins and graphical user interfaces.

## Features

### Planned

* Forced subtitle alignment
* Subtitle export
* Karaoke generation
* Lyric video rendering
* Configurable rendering pipeline
* Background image and video support
* Metadata management
* AI provider integration
* Plugin architecture
* Command-line interface
* Graphical user interface

## Requirements

* Python 3.14 or newer
* FFmpeg (required for rendering)

## Installation

```bash
git clone <repository-url>
cd media-production-framework

pip install -e ".[dev]"
```

## Documentation

Project documentation can be found in the `docs/` directory.

Important documents include:

* `docs/implementation-plan.md`
* `docs/roadmap.md`
* `docs/developer-guide.md`
* `docs/coding-standards.md`

## Development

Run the test suite:

```bash
pytest
```

Run the application:

```bash
python -m media_production_framework
```

or

```bash
mpf
```

## License

This project is licensed under the GNU AFFERO GENERAL PUBLIC LICENSE.
