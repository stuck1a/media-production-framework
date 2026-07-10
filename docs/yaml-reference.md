# YAML Configuration Reference

**Document Version:** v0.1.0
**Status:** Living Document

---

# Purpose

Every project processed by the framework is described by a single YAML configuration
file (see `templates/` for ready-to-copy starting points such as
[`default.yaml`](../templates/default.yaml), [`youtube.yaml`](../templates/youtube.yaml)
and [`karaoke.yaml`](../templates/karaoke.yaml)).

This document is the authoritative reference for every key such a file can contain:
what it means, which values are allowed, and what the default is when the key is
omitted. It is loaded and validated by `ConfigurationLoader`
([`configuration.py`](../src/media_production_framework/configuration.py)).

All keys are optional unless stated otherwise — a minimal file only needs `input.audio`
for most workflows. Paths are resolved relative to the configuration file's directory
unless given as absolute paths.

---

# Full Example

```yaml
input:
  audio: MySong.wav                    # supported: wav, mp3, flac, m4a, ogg, opus, aac, wma, ...
  lyrics: MySong_lyrics.txt            # one line = one subtitle segment
  metadata: metadata.txt               # optional FFMETADATA1 file, embedded into the output
  cover: cover.jpg                     # optional cover artwork, embedded into the output

output:
  video: MySong (Lyricsvideo).mp4      # supported: mp4, mkv, mov

subtitles:
  enabled: true                        # generate a subtitle file alongside the video
  provider: stable-whisper             # heuristic | stable-whisper | faster-whisper
  model: "D:/models/large-v3.pt"       # path to a Whisper model (*.pt); required by stable-whisper/faster-whisper
  language: de                         # ISO-639-1 language code (de, en, fr, es, it, ...)
  file: MySong.de_DE.srt               # output subtitle file (SRT)
  max_line_length: 42                  # max characters per subtitle line before wrapping (default: 42)
  options:                             # opaque passthrough to the alignment provider, ignored by "heuristic"
    vad: true                          # Silero VAD instead of volume-threshold silence detection (better for busy backing tracks)
    word_dur_factor: 3.0               # looser local max-word-duration before re-alignment kicks in (default 2.0)
    max_word_dur: 4.0                  # looser global cap (default 3.0)
    nonspeech_skip: 3.0                # skip silent gaps >=3s instead of 5s (default 5.0)

rendering:                             # omit the whole section to skip video rendering entirely
  video:
    resolution: 1920x1080              # "<width>x<height>"; common: 1280x720 / 1920x1080 / 2560x1440 / 3840x2160
    fps: 30                            # e.g. 24 / 25 / 30 / 50 / 60 (default: 30)
    bitrate: 320K                      # examples: 320K / 8M / 12M / 20M (default: 8M)
    codec: libx264                     # video codec passed to ffmpeg (default: libx264)
  background:
    type: video                        # color | image | video
    source: background_loop.mp4        # image/video path; ignored (or "#RRGGBB") when type=color
    loop: true                         # loop the background if shorter than the audio (video only, default: true)
  text:
    container:
      width: 80%                       # text block width as a percentage of video width (default: 80%)
      padding_top: 5%                  # reserved space above the text block, % of video height (default: 5%)
      padding_bottom: 8%               # reserved space below the text block, % of video height (default: 8%)
                                        # padding_top + padding_bottom must sum to less than 100%
    font:
      name: Montserrat                 # font family name (default: Sans)
      mode: auto                       # auto | fixed — auto searches [min_size, max_size] to fit max_lines
      size: 72                         # fixed font size in points; ignored when mode=auto (default: 72)
      max_lines: 3                     # max number of text lines before triggering auto-sizing (default: 3)
      min_size: 42                     # lower bound for auto-sizing (default: 42)
      max_size: 84                     # upper bound for auto-sizing (default: 84)
    color: "#FFFFFF"                   # text color as hex RRGGBB (default: #FFFFFF)
    bold: true                         # default: false
    italic: false                      # default: false
    outline: 4                         # outline thickness in pixels, 0 disables it (default: 0)
    shadow: 2                          # drop shadow size in pixels, 0 disables it (default: 0)
    vertical: bottom                   # top | middle | bottom (default: bottom)
    horizontal: center                 # left | center | right (default: center)
  karaoke:
    enabled: false                     # reserved for Milestone M4; parsed and validated, not yet rendered
    style: sweep                       # classic | sweep | glow (default: classic)

ffmpeg:
  preset: slow                        # ultrafast | superfast | veryfast | faster | fast | medium | slow | slower | veryslow (default: medium)
  crf: 18                             # 0-51, lower = higher quality and larger file size (default: 18)
  sample_rate: 48000                  # output audio sample rate in Hz, e.g. 44100 / 48000 (default: 48000)
```

---

# Key Reference

## `input`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `audio` | path | — | Source audio file. Supported formats: wav, mp3, flac, m4a, ogg, opus, aac, wma and other ffmpeg-readable formats. |
| `lyrics` | path | — | Plain-text lyrics file. One line equals one subtitle segment. |
| `metadata` | path | — | Optional FFMETADATA1 file embedded into the rendered output. |
| `cover` | path | — | Optional cover artwork embedded into the rendered output. |

## `output`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `video` | path | — | Destination video file. Supported containers: mp4, mkv, mov. |

## `subtitles`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `enabled` | bool | `false` | Whether to generate a subtitle file. |
| `provider` | enum | `heuristic` | Alignment backend: `heuristic` (offline, deterministic, no ML dependency) \| `stable-whisper` \| `faster-whisper`. |
| `model` | string | — | Path to a Whisper model file (`*.pt`). Required by `stable-whisper`/`faster-whisper`. |
| `language` | string | — | ISO-639-1 language code (e.g. `de`, `en`, `fr`). |
| `file` | path | — | Destination subtitle file (SRT). |
| `max_line_length` | int | `42` | Maximum characters per subtitle line before wrapping. |
| `options` | mapping | `{}` | Opaque passthrough to the alignment provider. Ignored by `heuristic`; see [Alignment Provider Options](#alignment-provider-options) below. |

## `rendering`

Omit the entire `rendering` section to skip video rendering (subtitle-only projects).

### `rendering.video`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `resolution` | string | `1920x1080` | `<width>x<height>`. |
| `fps` | int | `30` | Output frame rate. |
| `bitrate` | string | `8M` | Video bitrate, e.g. `320K`, `8M`. |
| `codec` | string | `libx264` | Video codec passed to ffmpeg. |

### `rendering.background`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `type` | enum | `color` | `color` \| `image` \| `video`. |
| `source` | path or hex color | `#000000` | Image/video path for `image`/`video` types; hex color (`#RRGGBB`) for `type: color`. Required for `image`/`video`. |
| `loop` | bool | `true` | Loop the background video if it is shorter than the audio. Only relevant for `type: video`. |

### `rendering.text.container`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `width` | percentage | `80%` | Text block width, as a fraction of video width (0% exclusive – 100% inclusive). |
| `padding_top` | percentage | `5%` | Reserved space above the text block, as a fraction of video height. |
| `padding_bottom` | percentage | `8%` | Reserved space below the text block, as a fraction of video height. `padding_top + padding_bottom` must be less than 100%. |

### `rendering.text.font`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `name` | string | `Sans` | Font family name. |
| `mode` | enum | `auto` | `auto` \| `fixed`. `auto` searches `[min_size, max_size]` for the largest size that fits within `max_lines`; `fixed` always uses `size`. |
| `size` | int | `72` | Fixed font size in points. Ignored when `mode: auto`. |
| `max_lines` | int | `3` | Maximum number of text lines before the auto-sizing search kicks in. |
| `min_size` | int | `42` | Lower bound for auto-sizing. Must not exceed `max_size`. |
| `max_size` | int | `84` | Upper bound for auto-sizing. |

### `rendering.text`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `color` | hex color | `#FFFFFF` | Text color (`#RRGGBB`). |
| `bold` | bool | `false` | |
| `italic` | bool | `false` | |
| `outline` | int | `0` | Outline thickness in pixels; `0` disables it. |
| `shadow` | int | `0` | Drop shadow size in pixels; `0` disables it. |
| `vertical` | enum | `bottom` | `top` \| `middle` \| `bottom`. |
| `horizontal` | enum | `center` | `left` \| `center` \| `right`. |

### `rendering.karaoke`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `enabled` | bool | `false` | Reserved for Milestone M4. Parsed and validated now, but not yet consumed by the rendering pipeline. |
| `style` | enum | `classic` | `classic` \| `sweep` \| `glow`. |

## `ffmpeg`

| Key | Type | Default | Description |
|-----|------|---------|--------------|
| `preset` | enum | `medium` | `ultrafast` \| `superfast` \| `veryfast` \| `faster` \| `fast` \| `medium` \| `slow` \| `slower` \| `veryslow`. Trades encoding speed for compression efficiency. |
| `crf` | int | `18` | Constant Rate Factor, `0`-`51`. Lower means higher quality and larger file size. |
| `sample_rate` | int | `48000` | Output audio sample rate in Hz. |

---

# Alignment Provider Options

The `subtitles.options` mapping is passed through, unmodified, to the alignment
provider named in `subtitles.provider`. The `heuristic` provider ignores it entirely.
For `stable-whisper` and `faster-whisper`, it maps directly onto the keyword arguments
of `stable_whisper`'s `align()` call, which performs word-level forced alignment of
plain text (or tokens) against the audio.

Because alignment is significantly faster than full transcription, this is the
efficient way to iterate on timing/wrapping settings without re-transcribing, and can
also produce more accurate timing for a transcript that Whisper's own decoding gets
wrong.

## Parameters

- `remove_instant_words` (bool, default `False`) — Truncate any words with zero duration.
- `token_step` (int, default `100`) — Max number of tokens to align per pass. Higher values reduce the chance of misalignment. Values below 1 fall back to the model's maximum (`n_text_ctx - 6`, typically 442).
- `original_split` (bool, default `False`) — Preserve the original segment groupings (lines) instead of Whisper's own regrouping.
- `max_word_dur` (float or `None`, default `3.0`) — Global maximum word duration in seconds; words exceeding it are re-aligned.
- `word_dur_factor` (float or `None`, default `2.0`) — Factor used to compute the *local* maximum word duration (`word_dur_factor * local median word duration`). Words needing re-alignment are constrained to `<=` the local/global maximum.
- `nonspeech_skip` (float or `None`, default `5.0`) — Skip non-speech gaps `>=` this many seconds. `None` disables skipping.
- `fast_mode` (bool, default `False`) — Speed up alignment via re-alignment using local/global max word duration. Works best when `text` is accurate and there are no large speechless gaps.
- `stream` (bool or `None`, default `None`) — Load audio in 30-second chunks until EOF. If `None`, defaults to `True` when `audio` is a path string.
- `failure_threshold` (float, optional) — Abort alignment once the percentage of zero-duration words exceeds this threshold.
- `verbose` (bool or `None`, default `False`) — `True` prints decoded text, `False` shows a progress bar, `None` prints nothing.
- `regroup` (bool or str, default `True`) — Customize or disable (`False`) the default regrouping algorithm. Ignored if word timestamps are disabled or if `original_split=True`.
- `suppress_silence` (bool, default `True`) — Adjust timestamps based on detected silence.
- `suppress_word_ts` (bool, default `True`) — Adjust word-level timestamps based on detected silence. Only applies when `suppress_silence=True`.
- `use_word_position` (bool, default `True`) — Use a word's position within its segment (first/last) to decide whether to keep its start or end timestamp during adjustment.
- `q_levels` (int, default `20`) — Quantization levels for the timestamp-suppression mask; ignored when `vad=true`. Fewer levels raise the volume threshold for marking sound as silent.
- `k_size` (int, default `5`) — Kernel size for average-pooling the waveform when building the suppression mask; ignored when `vad=true`. Recommended: 3 or 5; larger values reduce detected silence.
- `denoiser` (str, optional) — Denoiser to apply to `audio` before alignment. See `stable_whisper.audio.SUPPORTED_DENOISERS`.
- `denoiser_options` (dict, optional) — Keyword options for `denoiser`.
- `vad` (bool or dict, default `False`) — Use Silero VAD instead of volume-threshold silence detection (better for busy backing tracks). Pass a dict to forward keyword arguments to the VAD. Requires PyTorch 1.12.0+.
- `vad_threshold` (float, default `0.35`) — Speech-detection threshold for Silero VAD; lower values reduce false-positive silence.
- `min_word_dur` (float or `None`, default provider default) — Shortest duration a word may be shrunk to during silence suppression.
- `min_silence_dur` (float, optional) — Shortest silence duration eligible for suppression.
- `nonspeech_error` (float, default `0.1`) — Relative error tolerance for non-speech sections appearing inside a word, during silence suppression.
- `only_voice_freq` (bool, default `False`) — Restrict analysis to 200-5000 Hz, where most human speech lives.
- `prepend_punctuations` / `append_punctuations` (str or `None`) — Punctuation characters merged onto the following/preceding word.
- `progress_callback` (callable, optional) — `fn(seconds_transcribed: float, total_seconds: float)`, called as alignment progresses.
- `ignore_compatibility` (bool, default `False`) — Suppress warnings about Whisper version compatibility.
- `extra_models` (list of Whisper models, optional) — Additional models used alongside `model` when computing word timestamps.
- `presplit` (bool or list of str, default `True`) — Ending punctuation used to segment `text` for `gap_padding`. Does not affect final segmentation unless `original_split=True`. Ignored for faster-whisper models.
- `gap_padding` (str, default `' ...'`) — Prepended to each segment (when `presplit=True`) to reduce the chance of predicted timestamps landing before the first utterance. Ignored for faster-whisper models.
- `dynamic_heads` (bool, int or str, optional) — Search for optimal cross-attention heads at runtime instead of using the predefined ones. Pass a head count, `True` for the default of 6, or `"<heads>,<iterations>"` (e.g. `"8,3"`) to control both.

## Notes

- `regroup` is ignored entirely when `original_split=True`.
- Model-specific reference: `stable_whisper.result.WhisperResult` is returned on success (all timestamps, words and probabilities from alignment), or `None` if alignment fails and `remove_instant_words=True`.

## Example (direct API usage, for reference)

```python
>>> import stable_whisper
>>> model = stable_whisper.load_model('base')
>>> result = model.align('helloworld.mp3', 'Hello, World!', 'English')
>>> result.to_srt_vtt('helloworld.srt')
Saved 'helloworld.srt'
```
