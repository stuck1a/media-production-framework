# Media Production Framework

A modular, extensible framework for creating lyric videos, karaoke videos and other media production workflows.

> **Project Status:** Pre-Alpha

## Overview

The Media Production Framework is an open-source Python framework focused on automated media production.

The initial development focuses on generating high-quality lyric and karaoke videos from audio recordings and song lyrics. The architecture is designed to support future extensions such as AI-assisted workflows, additional rendering backends, plugins and graphical user interfaces.

## Features

* Forced subtitle alignment
* Subtitle export
* Lyric video rendering
* Configurable rendering pipeline
* Background image and video support
* Metadata management
* AI provider integration
* Plugin architecture
* Command-line interface

### Planned

* Karaoke generation (Milestone M4)
* Graphical user interface (Milestone M7)

## Requirements

* Python 3.14 (recommended, as tuned for it) or newer

Basically optional, but to get way better results in less time
* For rendering: fFmpeg or moviepy
* For lyrics alignment: whisper or faster-whisper

## Installation

### Windows

To get the minimalistic CLI-only setup without any pre-insatlled plugins, execute

```bat
git clone <repository-url>
cd media-production-framework
```


To support full functionality, execute following afterwards as well

```bat
.venv/Scripts/python.exe -m pip install --upgrade pip -q && .venv/Scripts/python.exe -m pip install -e ".[render,moviepy,whisper,faster-whisper]"
```


For development purposes, it's higly recommended to install all dev requirements into the virtual environment as well

```bash
.venv/Scripts/python.exe -m pip install --upgrade pip -q && .venv/Scripts/python.exe -m pip install -e ".[dev]"
```

## Documentation

Project documentation can be found in the `docs/` directory.

Important documents include:

* `docs/implementation-plan.md`
* `docs/roadmap.md`
* `docs/coding-standards.md`


### Where to start reading the documentation (agents)

Basically, the document `docs/developer-guide.md` can be understood as an entrypoint to dive in.

Its optimised to be a "Start to read here" document for AI agents, but should also work for developers.

## Usage

### Windows

(a) As virtual environment (recommended)

Either activate the env and execute `mpf.exe` like this
```bat
.venv/Scripts/activate.bat
mpf --config templates/yourConfig.yaml
.venv/Scripts/deactivate.bat
```


Or call `mpf.exe` directly (this will use your local python installation instead)
```bat
".venv/Scripts/mpf.exe" --config templates/yourConfig.yaml
```


(b) As module

```bat
py -m pip install -e .
py -m media_production_framework.main --config templates/yourConfig.yaml
```


## License

This project is licensed under the GNU AFFERO GENERAL PUBLIC LICENSE.
