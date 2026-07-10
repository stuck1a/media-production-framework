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
from media_production_framework.progress_view import RenderProgressView
from media_production_framework.projects import ProjectValidationError
from media_production_framework.render_backends import RenderingError
from media_production_framework.subtitle_import import SrtImportError
from media_production_framework.subtitle_validation import SubtitleValidationError

LOG_LEVEL_CHOICES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser.

    Rendering behaviour (whether to render and which backend to use) now lives
    in the project's YAML ``rendering`` section, so the CLI only carries the
    per-invocation switches: the configuration file, the log level and preview.
    """

    parser = argparse.ArgumentParser(
        prog="mpf",
        description="Run the Media Production Framework processing pipeline.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to a project YAML configuration file.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVEL_CHOICES,
        type=str.upper,
        help="Python logging level to use during execution.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Render a fast, low-resolution preview instead of the full video.",
    )
    return parser


def run_pipeline(
    configuration_path: Path,
    log_level: str = "INFO",
    *,
    preview: bool = False,
) -> PipelineContext:
    """Run the core processing pipeline and return its final context."""

    logger = configure_logging(log_level)
    resolved_config = configuration_path.expanduser().resolve()
    context = PipelineContext(
        project_root=resolved_config.parent,
        configuration_path=resolved_config,
        preview=preview,
        logger=logger,
    )
    RenderProgressView().subscribe(context.event_bus)
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
            log_level=args.log_level,
            preview=args.preview,
        )
    except ConfigurationError as exc:
        parser.exit(2, f"Configuration failed: {exc}\n")
    except ProjectValidationError as exc:
        parser.exit(2, f"Project validation failed: {exc}\n")
    except MetadataError as exc:
        parser.exit(2, f"Metadata parsing failed: {exc}\n")
    except AlignmentError as exc:
        parser.exit(2, f"Subtitle alignment failed: {exc}\n")
    except SrtImportError as exc:
        parser.exit(2, f"Subtitle import failed: {exc}\n")
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
