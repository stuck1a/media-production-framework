"""
Configuration loading for the Media Production Framework.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be loaded or validated."""


@dataclass(frozen=True)
class InputConfiguration:
    """Input files used by a media production project."""

    audio: Path | None = None
    lyrics: Path | None = None
    metadata: Path | None = None
    cover: Path | None = None


@dataclass(frozen=True)
class OutputConfiguration:
    """Output files produced by a media production project."""

    video: Path | None = None


DEFAULT_SUBTITLE_PROVIDER = "heuristic"
DEFAULT_SUBTITLE_MAX_LINE_LENGTH = 42


@dataclass(frozen=True)
class SubtitleConfiguration:
    """Subtitle generation settings (FR-014 - FR-018, capability CAP-002/CAP-003).

    ``provider`` and ``model`` identify the alignment backend; interpreting
    them belongs to the Alignment Engine rather than this configuration
    object, which only carries the validated values.
    """

    enabled: bool = False
    provider: str = DEFAULT_SUBTITLE_PROVIDER
    model: str | None = None
    language: str | None = None
    file: Path | None = None
    max_line_length: int = DEFAULT_SUBTITLE_MAX_LINE_LENGTH
    audio_duration_seconds: float | None = None


# --- Rendering configuration (Milestone M3, FR-024 - FR-055) ------------------
#
# These objects only carry validated values; interpreting them (building the
# actual render command, measuring fonts, etc.) belongs to the Rendering Engine
# rather than this configuration layer. See ADR-0002.

DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_FPS = 30
DEFAULT_VIDEO_BITRATE = "8M"
DEFAULT_VIDEO_CODEC = "libx264"

BACKGROUND_TYPES = ("color", "image", "video")
DEFAULT_BACKGROUND_TYPE = "color"
DEFAULT_BACKGROUND_COLOR = "#000000"

DEFAULT_CONTAINER_WIDTH = 0.8
DEFAULT_CONTAINER_PADDING_TOP = 0.05
DEFAULT_CONTAINER_PADDING_BOTTOM = 0.08

FONT_MODES = ("auto", "fixed")
DEFAULT_FONT_NAME = "Sans"
DEFAULT_FONT_MODE = "auto"
DEFAULT_FONT_SIZE = 72
DEFAULT_FONT_MAX_LINES = 3
DEFAULT_FONT_MIN_SIZE = 42
DEFAULT_FONT_MAX_SIZE = 84

DEFAULT_TEXT_COLOR = "#FFFFFF"
VERTICAL_POSITIONS = ("top", "middle", "bottom")
HORIZONTAL_POSITIONS = ("left", "center", "right")
DEFAULT_VERTICAL_POSITION = "bottom"
DEFAULT_HORIZONTAL_POSITION = "center"

KARAOKE_STYLES = ("classic", "sweep", "glow")
DEFAULT_KARAOKE_STYLE = "classic"

FFMPEG_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)
DEFAULT_FFMPEG_PRESET = "medium"
DEFAULT_FFMPEG_CRF = 18
DEFAULT_FFMPEG_SAMPLE_RATE = 48000


@dataclass(frozen=True)
class VideoConfiguration:
    """Output video format settings (FR-024 - FR-026, FR-028)."""

    resolution: tuple[int, int] = DEFAULT_RESOLUTION
    fps: int = DEFAULT_FPS
    bitrate: str = DEFAULT_VIDEO_BITRATE
    codec: str = DEFAULT_VIDEO_CODEC

    @property
    def width(self) -> int:
        """Return the output width in pixels."""

        return self.resolution[0]

    @property
    def height(self) -> int:
        """Return the output height in pixels."""

        return self.resolution[1]


@dataclass(frozen=True)
class BackgroundConfiguration:
    """Background source settings (FR-049 - FR-055).

    ``type`` selects the source kind. For ``color`` backgrounds the validated
    hex value is stored in ``color`` and ``source`` is ``None``; for ``image``
    and ``video`` backgrounds the resolved media path is stored in ``source``
    and ``color`` is ``None``.
    """

    type: str = DEFAULT_BACKGROUND_TYPE
    color: str | None = DEFAULT_BACKGROUND_COLOR
    source: Path | None = None
    loop: bool = True


@dataclass(frozen=True)
class ContainerConfiguration:
    """Text container geometry, expressed as fractions of the video size.

    ``width`` is a fraction of the video width (FR-044); the paddings are
    fractions of the video height reserved above and below the text block.
    """

    width: float = DEFAULT_CONTAINER_WIDTH
    padding_top: float = DEFAULT_CONTAINER_PADDING_TOP
    padding_bottom: float = DEFAULT_CONTAINER_PADDING_BOTTOM


@dataclass(frozen=True)
class FontConfiguration:
    """Font family, sizing bounds and scaling mode (FR-035 - FR-040).

    ``mode`` selects between a fixed ``size`` and automatic sizing that searches
    the ``[min_size, max_size]`` range; the search itself is implemented by the
    Layout Engine, not here.
    """

    name: str = DEFAULT_FONT_NAME
    mode: str = DEFAULT_FONT_MODE
    size: int = DEFAULT_FONT_SIZE
    max_lines: int = DEFAULT_FONT_MAX_LINES
    min_size: int = DEFAULT_FONT_MIN_SIZE
    max_size: int = DEFAULT_FONT_MAX_SIZE


@dataclass(frozen=True)
class TextConfiguration:
    """Text rendering and positioning settings (FR-035 - FR-047)."""

    container: ContainerConfiguration = field(default_factory=ContainerConfiguration)
    font: FontConfiguration = field(default_factory=FontConfiguration)
    color: str = DEFAULT_TEXT_COLOR
    bold: bool = False
    italic: bool = False
    outline: int = 0
    shadow: int = 0
    vertical: str = DEFAULT_VERTICAL_POSITION
    horizontal: str = DEFAULT_HORIZONTAL_POSITION


@dataclass(frozen=True)
class KaraokeConfiguration:
    """Karaoke rendering settings.

    Karaoke *rendering* is Milestone M4; this configuration is parsed,
    validated and reserved now so the hook exists, but it is not consumed by
    the M3 rendering pipeline.
    """

    enabled: bool = False
    style: str = DEFAULT_KARAOKE_STYLE


@dataclass(frozen=True)
class RenderConfiguration:
    """Complete rendering configuration for a project (the ``rendering`` section)."""

    video: VideoConfiguration = field(default_factory=VideoConfiguration)
    background: BackgroundConfiguration = field(default_factory=BackgroundConfiguration)
    text: TextConfiguration = field(default_factory=TextConfiguration)
    karaoke: KaraokeConfiguration = field(default_factory=KaraokeConfiguration)


@dataclass(frozen=True)
class FfmpegConfiguration:
    """FFmpeg encoder settings (FR-027, encoding quality/speed trade-off)."""

    preset: str = DEFAULT_FFMPEG_PRESET
    crf: int = DEFAULT_FFMPEG_CRF
    sample_rate: int = DEFAULT_FFMPEG_SAMPLE_RATE


@dataclass(frozen=True)
class ProjectConfiguration:
    """Normalized project configuration loaded from YAML."""

    project_root: Path
    input: InputConfiguration = field(default_factory=InputConfiguration)
    output: OutputConfiguration = field(default_factory=OutputConfiguration)
    subtitles: SubtitleConfiguration = field(default_factory=SubtitleConfiguration)
    rendering: RenderConfiguration | None = None
    ffmpeg: FfmpegConfiguration = field(default_factory=FfmpegConfiguration)
    raw: Mapping[str, Any] = field(default_factory=dict)


class ConfigurationLoader:
    """Load and normalize YAML project configuration files."""

    def load(self, path: Path) -> ProjectConfiguration:
        """Load a configuration file from disk."""

        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_file():
            raise ConfigurationError(f"Configuration file does not exist: {resolved_path}")

        try:
            loaded_data = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigurationError(f"Invalid YAML configuration: {resolved_path}") from exc

        if loaded_data is None:
            loaded_data = {}

        if not isinstance(loaded_data, Mapping):
            raise ConfigurationError("Configuration root must be a mapping.")

        project_root = resolved_path.parent
        input_data = self._mapping_section(loaded_data, "input")
        output_data = self._mapping_section(loaded_data, "output")
        subtitles_data = self._mapping_section(loaded_data, "subtitles")
        ffmpeg_data = self._mapping_section(loaded_data, "ffmpeg")

        rendering = None
        if "rendering" in loaded_data and loaded_data.get("rendering") is not None:
            rendering = self._render_configuration(
                self._mapping_section(loaded_data, "rendering"),
                project_root,
            )

        return ProjectConfiguration(
            project_root=project_root,
            input=InputConfiguration(
                audio=self._optional_path(input_data, "audio", project_root),
                lyrics=self._optional_path(input_data, "lyrics", project_root),
                metadata=self._optional_path(input_data, "metadata", project_root),
                cover=self._optional_path(input_data, "cover", project_root),
            ),
            output=OutputConfiguration(
                video=self._optional_path(output_data, "video", project_root),
            ),
            subtitles=self._subtitle_configuration(subtitles_data, project_root),
            rendering=rendering,
            ffmpeg=self._ffmpeg_configuration(ffmpeg_data),
            raw=loaded_data,
        )

    @classmethod
    def _subtitle_configuration(
        cls,
        data: Mapping[str, Any],
        project_root: Path,
    ) -> SubtitleConfiguration:
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ConfigurationError("Configuration value 'subtitles.enabled' must be a boolean.")

        provider = data.get("provider", DEFAULT_SUBTITLE_PROVIDER)
        if not isinstance(provider, str) or not provider:
            raise ConfigurationError("Configuration value 'subtitles.provider' must be a string.")

        model = cls._optional_string(data, "model")
        language = cls._optional_string(data, "language")
        max_line_length = data.get("max_line_length", DEFAULT_SUBTITLE_MAX_LINE_LENGTH)
        if not isinstance(max_line_length, int) or isinstance(max_line_length, bool):
            raise ConfigurationError(
                "Configuration value 'subtitles.max_line_length' must be an integer."
            )

        duration = data.get("audio_duration_seconds")
        if duration is not None and not isinstance(duration, (int, float)):
            raise ConfigurationError(
                "Configuration value 'subtitles.audio_duration_seconds' must be a number."
            )

        return SubtitleConfiguration(
            enabled=enabled,
            provider=provider,
            model=model,
            language=language,
            file=cls._optional_path(data, "file", project_root),
            max_line_length=max_line_length,
            audio_duration_seconds=float(duration) if duration is not None else None,
        )

    @classmethod
    def _render_configuration(
        cls,
        data: Mapping[str, Any],
        project_root: Path,
    ) -> RenderConfiguration:
        return RenderConfiguration(
            video=cls._video_configuration(cls._mapping_section(data, "video")),
            background=cls._background_configuration(
                cls._mapping_section(data, "background"), project_root
            ),
            text=cls._text_configuration(cls._mapping_section(data, "text")),
            karaoke=cls._karaoke_configuration(cls._mapping_section(data, "karaoke")),
        )

    @classmethod
    def _video_configuration(cls, data: Mapping[str, Any]) -> VideoConfiguration:
        return VideoConfiguration(
            resolution=cls._parse_resolution(
                data.get("resolution", DEFAULT_RESOLUTION), "rendering.video.resolution"
            ),
            fps=cls._require_int(data, "fps", DEFAULT_FPS, "rendering.video.fps", minimum=1),
            bitrate=cls._require_nonempty_string(
                data, "bitrate", DEFAULT_VIDEO_BITRATE, "rendering.video.bitrate"
            ),
            codec=cls._require_nonempty_string(
                data, "codec", DEFAULT_VIDEO_CODEC, "rendering.video.codec"
            ),
        )

    @classmethod
    def _background_configuration(
        cls,
        data: Mapping[str, Any],
        project_root: Path,
    ) -> BackgroundConfiguration:
        bg_type = cls._require_enum(
            data, "type", BACKGROUND_TYPES, DEFAULT_BACKGROUND_TYPE, "rendering.background.type"
        )
        loop = cls._require_bool(data, "loop", True, "rendering.background.loop")
        source_value = data.get("source")

        if bg_type == "color":
            color_value = (
                source_value if source_value not in (None, "") else DEFAULT_BACKGROUND_COLOR
            )
            color = cls._parse_color(color_value, "rendering.background.source")
            return BackgroundConfiguration(type=bg_type, color=color, source=None, loop=loop)

        if source_value in (None, ""):
            raise ConfigurationError(
                f"Configuration value 'rendering.background.source' is required "
                f"for '{bg_type}' backgrounds."
            )
        if not isinstance(source_value, str):
            raise ConfigurationError(
                "Configuration value 'rendering.background.source' must be a path string."
            )
        path = Path(source_value).expanduser()
        if not path.is_absolute():
            path = project_root / path
        return BackgroundConfiguration(type=bg_type, color=None, source=path.resolve(), loop=loop)

    @classmethod
    def _text_configuration(cls, data: Mapping[str, Any]) -> TextConfiguration:
        return TextConfiguration(
            container=cls._container_configuration(cls._mapping_section(data, "container")),
            font=cls._font_configuration(cls._mapping_section(data, "font")),
            color=cls._parse_color(data.get("color", DEFAULT_TEXT_COLOR), "rendering.text.color"),
            bold=cls._require_bool(data, "bold", False, "rendering.text.bold"),
            italic=cls._require_bool(data, "italic", False, "rendering.text.italic"),
            outline=cls._require_int(data, "outline", 0, "rendering.text.outline", minimum=0),
            shadow=cls._require_int(data, "shadow", 0, "rendering.text.shadow", minimum=0),
            vertical=cls._require_enum(
                data,
                "vertical",
                VERTICAL_POSITIONS,
                DEFAULT_VERTICAL_POSITION,
                "rendering.text.vertical",
            ),
            horizontal=cls._require_enum(
                data,
                "horizontal",
                HORIZONTAL_POSITIONS,
                DEFAULT_HORIZONTAL_POSITION,
                "rendering.text.horizontal",
            ),
        )

    @classmethod
    def _container_configuration(cls, data: Mapping[str, Any]) -> ContainerConfiguration:
        width = cls._fraction(
            data.get("width", DEFAULT_CONTAINER_WIDTH),
            "rendering.text.container.width",
            include_low=False,
            include_high=True,
        )
        padding_top = cls._fraction(
            data.get("padding_top", DEFAULT_CONTAINER_PADDING_TOP),
            "rendering.text.container.padding_top",
            include_low=True,
            include_high=False,
        )
        padding_bottom = cls._fraction(
            data.get("padding_bottom", DEFAULT_CONTAINER_PADDING_BOTTOM),
            "rendering.text.container.padding_bottom",
            include_low=True,
            include_high=False,
        )
        if padding_top + padding_bottom >= 1.0:
            raise ConfigurationError(
                "Configuration values 'rendering.text.container.padding_top' and "
                "'padding_bottom' must sum to less than 100%."
            )
        return ContainerConfiguration(
            width=width, padding_top=padding_top, padding_bottom=padding_bottom
        )

    @classmethod
    def _font_configuration(cls, data: Mapping[str, Any]) -> FontConfiguration:
        min_size = cls._require_int(
            data, "min_size", DEFAULT_FONT_MIN_SIZE, "rendering.text.font.min_size", minimum=1
        )
        max_size = cls._require_int(
            data, "max_size", DEFAULT_FONT_MAX_SIZE, "rendering.text.font.max_size", minimum=1
        )
        if min_size > max_size:
            raise ConfigurationError(
                "Configuration value 'rendering.text.font.min_size' must not exceed 'max_size'."
            )
        return FontConfiguration(
            name=cls._require_nonempty_string(
                data, "name", DEFAULT_FONT_NAME, "rendering.text.font.name"
            ),
            mode=cls._require_enum(
                data, "mode", FONT_MODES, DEFAULT_FONT_MODE, "rendering.text.font.mode"
            ),
            size=cls._require_int(
                data, "size", DEFAULT_FONT_SIZE, "rendering.text.font.size", minimum=1
            ),
            max_lines=cls._require_int(
                data,
                "max_lines",
                DEFAULT_FONT_MAX_LINES,
                "rendering.text.font.max_lines",
                minimum=1,
            ),
            min_size=min_size,
            max_size=max_size,
        )

    @classmethod
    def _karaoke_configuration(cls, data: Mapping[str, Any]) -> KaraokeConfiguration:
        return KaraokeConfiguration(
            enabled=cls._require_bool(data, "enabled", False, "rendering.karaoke.enabled"),
            style=cls._require_enum(
                data, "style", KARAOKE_STYLES, DEFAULT_KARAOKE_STYLE, "rendering.karaoke.style"
            ),
        )

    @classmethod
    def _ffmpeg_configuration(cls, data: Mapping[str, Any]) -> FfmpegConfiguration:
        return FfmpegConfiguration(
            preset=cls._require_enum(
                data, "preset", FFMPEG_PRESETS, DEFAULT_FFMPEG_PRESET, "ffmpeg.preset"
            ),
            crf=cls._require_int(
                data, "crf", DEFAULT_FFMPEG_CRF, "ffmpeg.crf", minimum=0, maximum=51
            ),
            sample_rate=cls._require_int(
                data, "sample_rate", DEFAULT_FFMPEG_SAMPLE_RATE, "ffmpeg.sample_rate", minimum=1
            ),
        )

    @staticmethod
    def _require_bool(data: Mapping[str, Any], key: str, default: bool, dotted: str) -> bool:
        value = data.get(key, default)
        if not isinstance(value, bool):
            raise ConfigurationError(f"Configuration value '{dotted}' must be a boolean.")
        return value

    @staticmethod
    def _require_int(
        data: Mapping[str, Any],
        key: str,
        default: int,
        dotted: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        value = data.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigurationError(f"Configuration value '{dotted}' must be an integer.")
        if minimum is not None and value < minimum:
            raise ConfigurationError(f"Configuration value '{dotted}' must be at least {minimum}.")
        if maximum is not None and value > maximum:
            raise ConfigurationError(f"Configuration value '{dotted}' must be at most {maximum}.")
        return value

    @staticmethod
    def _require_nonempty_string(
        data: Mapping[str, Any],
        key: str,
        default: str,
        dotted: str,
    ) -> str:
        value = data.get(key, default)
        if not isinstance(value, str) or not value:
            raise ConfigurationError(f"Configuration value '{dotted}' must be a non-empty string.")
        return value

    @staticmethod
    def _require_enum(
        data: Mapping[str, Any],
        key: str,
        allowed: tuple[str, ...],
        default: str,
        dotted: str,
    ) -> str:
        value = data.get(key, default)
        if not isinstance(value, str):
            raise ConfigurationError(f"Configuration value '{dotted}' must be a string.")
        normalized = value.lower()
        if normalized not in allowed:
            raise ConfigurationError(
                f"Configuration value '{dotted}' must be one of: {', '.join(allowed)}."
            )
        return normalized

    @staticmethod
    def _parse_resolution(value: Any, dotted: str) -> tuple[int, int]:
        if isinstance(value, tuple) and len(value) == 2:
            return (int(value[0]), int(value[1]))
        if not isinstance(value, str):
            raise ConfigurationError(
                f"Configuration value '{dotted}' must be a string like '1920x1080'."
            )
        parts = value.lower().split("x")
        if len(parts) != 2:
            raise ConfigurationError(
                f"Configuration value '{dotted}' must have the form '<width>x<height>'."
            )
        try:
            width = int(parts[0].strip())
            height = int(parts[1].strip())
        except ValueError as exc:
            raise ConfigurationError(
                f"Configuration value '{dotted}' must have integer width and height."
            ) from exc
        if width <= 0 or height <= 0:
            raise ConfigurationError(
                f"Configuration value '{dotted}' must have positive width and height."
            )
        return (width, height)

    @staticmethod
    def _parse_color(value: Any, dotted: str) -> str:
        if not isinstance(value, str):
            raise ConfigurationError(
                f"Configuration value '{dotted}' must be a hex colour like '#RRGGBB'."
            )
        text = value.strip()
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
            raise ConfigurationError(
                f"Configuration value '{dotted}' must be a hex colour like '#RRGGBB'."
            )
        return "#" + text[1:].upper()

    @classmethod
    def _fraction(
        cls,
        value: Any,
        dotted: str,
        *,
        include_low: bool,
        include_high: bool,
    ) -> float:
        fraction = cls._to_fraction(value, dotted)
        low_ok = fraction >= 0.0 if include_low else fraction > 0.0
        high_ok = fraction <= 1.0 if include_high else fraction < 1.0
        if not (low_ok and high_ok):
            raise ConfigurationError(
                f"Configuration value '{dotted}' must be a percentage between 0% and 100%."
            )
        return fraction

    @staticmethod
    def _to_fraction(value: Any, dotted: str) -> float:
        if isinstance(value, str):
            text = value.strip()
            if not text.endswith("%"):
                raise ConfigurationError(
                    f"Configuration value '{dotted}' must be a percentage like '80%'."
                )
            try:
                return float(text[:-1].strip()) / 100.0
            except ValueError as exc:
                raise ConfigurationError(
                    f"Configuration value '{dotted}' must be a percentage like '80%'."
                ) from exc
        if isinstance(value, bool):
            raise ConfigurationError(
                f"Configuration value '{dotted}' must be a percentage like '80%'."
            )
        if isinstance(value, (int, float)):
            return float(value)
        raise ConfigurationError(
            f"Configuration value '{dotted}' must be a percentage like '80%'."
        )

    @staticmethod
    def _optional_string(data: Mapping[str, Any], key: str) -> str | None:
        value = data.get(key)
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ConfigurationError(f"Configuration value '{key}' must be a string.")
        return value

    @staticmethod
    def empty(project_root: Path) -> ProjectConfiguration:
        """Create an empty configuration rooted at the given directory."""

        return ProjectConfiguration(project_root=project_root.expanduser().resolve())

    @staticmethod
    def _mapping_section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
        section = data.get(key, {})
        if section is None:
            return {}
        if not isinstance(section, Mapping):
            raise ConfigurationError(f"Configuration section '{key}' must be a mapping.")
        return section

    @staticmethod
    def _optional_path(data: Mapping[str, Any], key: str, project_root: Path) -> Path | None:
        value = data.get(key)
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ConfigurationError(f"Configuration value '{key}' must be a path string.")

        path = Path(value).expanduser()
        if not path.is_absolute():
            path = project_root / path
        return path.resolve()
