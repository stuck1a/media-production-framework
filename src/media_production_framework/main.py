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
from media_production_framework.subtitle_validation import SubtitleValidationError

LOG_LEVEL_CHOICES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


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
    return parser


def run_pipeline(
    configuration_path: Path | None = None,
    project_root: Path | None = None,
    log_level: str = "INFO",
) -> PipelineContext:
    """Run the M1 core pipeline and return its final context."""

    logger = configure_logging(log_level)
    context = PipelineContext(
        project_root=(project_root or Path.cwd()).expanduser().resolve(),
        configuration_path=configuration_path.expanduser().resolve()
        if configuration_path is not None
        else None,
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

    stage_count = sum(
        1
        for event in context.event_bus.published_events
        if isinstance(event, PipelineStageCompletedEvent)
    )
    print(f"Media Production Framework pipeline completed ({stage_count} stages).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
