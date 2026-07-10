"""
Application entry point.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from media_production_framework.alignment import AlignmentError
from media_production_framework.configuration import ConfigurationError
from media_production_framework.events import ApplicationStartedEvent, PipelineStageCompletedEvent
from media_production_framework.log_config import configure_logging
from media_production_framework.metadata import MetadataError
from media_production_framework.pipeline import PipelineContext, build_core_pipeline
from media_production_framework.projects import ProjectValidationError
from media_production_framework.render_backends import (
    BACKEND_AUTO,
    BACKEND_DRY_RUN,
    BACKEND_FFMPEG,
    BACKEND_MOVIEPY,
    RenderingError,
)
from media_production_framework.subtitle_validation import SubtitleValidationError

LOG_LEVEL_CHOICES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
BACKEND_CHOICES = (BACKEND_AUTO, BACKEND_FFMPEG, BACKEND_MOVIEPY, BACKEND_DRY_RUN)


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""

    parser = argparse.ArgumentParser(
        prog="mpf",
        description="Run the Media Production Framework processing pipeline.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to a project YAML configuration file.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root used when no configuration file is provided.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVEL_CHOICES,
        type=str.upper,
        help="Python logging level to use during execution.",
    )
    parser.add_argument(
        "--render",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Render the output video when a rendering configuration is present.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Render a fast, low-resolution preview instead of the full video.",
    )
    parser.add_argument(
        "--backend",
        default=BACKEND_AUTO,
        choices=BACKEND_CHOICES,
        help="Rendering backend to use ('auto' selects the first available).",
    )
    return parser


def run_pipeline(
    configuration_path: Path | None = None,
    project_root: Path | None = None,
    log_level: str = "INFO",
    *,
    render_enabled: bool = True,
    preview: bool = False,
    render_backend: str = BACKEND_AUTO,
) -> PipelineContext:
    """Run the core processing pipeline and return its final context."""

    logger = configure_logging(log_level)
    context = PipelineContext(
        project_root=(project_root or Path.cwd()).expanduser().resolve(),
        configuration_path=configuration_path.expanduser().resolve()
        if configuration_path is not None
        else None,
        render_enabled=render_enabled,
        preview=preview,
        render_backend=render_backend,
        logger=logger,
    )
    context.event_bus.publish(ApplicationStartedEvent())

    pipeline = build_core_pipeline()
    return pipeline.execute(context)


def main(argv: Sequence[str] | None = None) -> int:
    """Command line entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        context = run_pipeline(
            configuration_path=args.config,
            project_root=args.project_root,
            log_level=args.log_level,
            render_enabled=args.render,
            preview=args.preview,
            render_backend=args.backend,
        )
    except ConfigurationError as exc:
        parser.exit(2, f"Configuration failed: {exc}\n")
    except ProjectValidationError as exc:
        parser.exit(2, f"Project validation failed: {exc}\n")
    except MetadataError as exc:
        parser.exit(2, f"Metadata parsing failed: {exc}\n")
    except AlignmentError as exc:
        parser.exit(2, f"Subtitle alignment failed: {exc}\n")
    except SubtitleValidationError as exc:
        parser.exit(2, f"Subtitle validation failed: {exc}\n")
    except RenderingError as exc:
        parser.exit(2, f"Video rendering failed: {exc}\n")

    stage_count = sum(
        1
        for event in context.event_bus.published_events
        if isinstance(event, PipelineStageCompletedEvent)
    )
    print(f"Media Production Framework pipeline completed ({stage_count} stages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
