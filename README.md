# PAR CLI STT

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
![Runs on Linux | MacOS | Windows](https://img.shields.io/badge/runs%20on-Linux%20%7C%20MacOS%20%7C%20Windows-blue)
![Arch x86-64 | ARM | AppleSilicon](https://img.shields.io/badge/arch-x86--64%20%7C%20ARM%20%7C%20AppleSilicon-blue)
![MIT License](https://img.shields.io/badge/license-MIT-green.svg)
![Version](https://img.shields.io/pypi/v/par-cli-stt.svg)
![Development Status](https://img.shields.io/badge/status-pre--alpha-yellow.svg)

A streaming speech-to-text library and command-line tool supporting ElevenLabs Scribe and Deepgram Nova-3, with a plugin architecture, typed provider options, and flexible output formats (plain text, SRT, VTT, JSON).

**Use as a CLI** — `par-stt recording.wav`
**Use as a library** — `from par_stt import create_provider`

## Features

- **Two launch providers** — Deepgram **Nova-3** (streaming WebSocket, interim + final chunks) and ElevenLabs **Scribe** (batch, full transcript with language detection).
- **Streaming-first core** — every provider exposes a uniform `transcribe_async()` surface; batch providers inherit a sync-wrapping default.
- **Plugin registry** — built-in providers plus third-party discovery via the `par_stt.providers` entry-point group.
- **Flexible output** — render transcripts as `txt`, `srt`, `vtt`, or `json`.
- **Configuration** — YAML config file (`~/Library/Application Support/par-stt/config.yaml` on macOS) with named profiles, or environment variables.
- **Typed options** — `DeepgramOptions` / `ScribeOptions` dataclasses with schema introspection.
- **Cost estimates** — static per-minute pricing for quick planning.
- **CLI** — Typer + Rich: `--capabilities`, `--dump`, `--profile`, shell completions, and more.

## Technology Stack

Python 3.11+, `httpx`, `typer`, `rich`, `platformdirs`, `pyyaml`, `python-dotenv`, `websockets`, `soundfile`, `elevenlabs`. Builds with `hatchling`; gates with `ruff` + `pyright` + `pytest`.

## Prerequisites

- Python 3.11 or newer
- An ElevenLabs API key (for Scribe) and/or a Deepgram API key (for Nova-3)
- `libsndfile` (bundled with the `soundfile` wheel on most platforms) for audio loading

## Installation

### From PyPI (recommended)

```bash
uv tool install par-cli-stt
# or
pip install par-cli-stt
```

### From source

```bash
git clone https://github.com/paulrobello/par-cli-stt.git
cd par-cli-stt
uv sync
make checkall
```

Run from the checkout with `uv run par-stt --help`.

## Configuration

API keys can be provided through environment variables or the config file. The config file is the recommended store for keys and is created with mode `0o600` (owner-only read/write).

| Variable | Providers | Purpose |
|---|---|---|
| `ELEVENLABS_API_KEY` | elevenlabs | Scribe API key |
| `DEEPGRAM_API_KEY` | deepgram | Deepgram API key (also accepts `DG_API_KEY`) |
| `STT_PROVIDER` | both | Default provider (`deepgram`, `elevenlabs`) |
| `STT_MODEL` | both | Default model override |
| `STT_LANGUAGE` | both | Default language hint |
| `STT_FORMAT` | both | Default output format (`txt`, `srt`, `vtt`, `json`) |

Create a sample config file:

```bash
par-stt --create-config
```

This writes `~/Library/Application Support/par-stt/config.yaml` (macOS) or `~/.config/par-stt/config.yaml` (Linux). Add your keys under `elevenlabs_api_key:` / `deepgram_api_key:`. **If you already have an ElevenLabs key in `par-tts`'s config, copy the same value here** — the field name is identical.

Example config:

```yaml
provider: deepgram
model: nova-3
language: en
output_format: txt
# output_dir: ~/Documents/transcripts

# API keys (optional — env vars work too)
elevenlabs_api_key: your-elevenlabs-api-key-here
deepgram_api_key: your-deepgram-api-key-here

# Named profiles selected with --profile NAME
profiles:
  meetings:
    provider: deepgram
    language: en
    diarize: true
  interviews:
    provider: elevenlabs
    diarize: true
```

Precedence: CLI flags > config file > environment variables.

## Usage

### CLI

Transcribe a file and print text to stdout:

```bash
par-stt recording.wav --provider deepgram
```

Write an SRT subtitle file:

```bash
par-stt meeting.wav --provider deepgram --format srt --output meeting.srt
```

Use a profile and a language hint:

```bash
par-stt interview.mp3 --profile interviews --language en
```

Inspect providers without making a network call:

```bash
par-stt --capabilities
par-stt --list-providers
par-stt --dump
```

### Library

```python
import par_stt

print(par_stt.__version__)
print(par_stt.list_providers())  # ['deepgram', 'elevenlabs']

# Sync batch transcription (returns a Transcript)
provider = par_stt.create_provider("deepgram", api_key=os.environ["DEEPGRAM_API_KEY"])
pcm = par_stt.read_audio("recording.wav")
transcript = provider.transcribe(pcm, language="en")
print(transcript.text)

# Native async streaming (interim + final chunks)
async for chunk in provider.transcribe_async(pcm):
    print(chunk.text, chunk.is_final)

# Render and write
par_stt.write_transcript(transcript, "srt", "out.srt")
```

The `TranscriptionPipeline` keeps a provider instance plus defaults for repeated use:

```python
from par_stt import TranscriptionPipeline

pipeline = TranscriptionPipeline.from_provider_name(
    "deepgram", api_key=os.environ["DEEPGRAM_API_KEY"], language="en"
)
transcript = pipeline.transcribe_file("recording.wav")
```

## Provider Options

Typed option dataclasses are validated and converted to provider `transcribe` kwargs via `options_to_kwargs`.

| Provider | Option | Default | Effect |
|---|---|---|---|
| deepgram | `smart_format` | `True` | Smart-format post-processing |
| deepgram | `punctuate` | `True` | Automatic punctuation |
| deepgram | `profanity_filter` | `False` | Mask profanity |
| deepgram | `diarize` | `False` | Label distinct speakers |
| deepgram | `filler_words` | `False` | Keep filler words |
| elevenlabs | `language_code` | `None` | ISO-639 language hint |
| elevenlabs | `diarize` | `False` | Label distinct speakers |
| elevenlabs | `tag_audio_events` | `False` | Tag non-speech events |

CLI equivalents: `--diarize/--no-diarize`, `--smart-format/--no-smart-format`, `--punctuate/--no-punctuate`, `--profanity-filter/--no-profanity-filter`, `--tag-audio-events/--no-tag-audio-events`.

## Diagnostics

Offline environment checks are available to library consumers and the CLI:

```python
from par_stt import collect_diagnostics

for check in collect_diagnostics():
    print(check.name, check.ok, check.detail)
```

Checks cover provider API-key env vars, the config file, the `soundfile`/`libsndfile` audio backend, and the optional `ffmpeg` binary — all without network access.

## Development

```bash
make checkall   # format + lint + typecheck + test (with coverage)
make test       # pytest only
make fmt        # ruff format
make package    # build wheel
```

The gate is `make checkall` (ruff format, ruff check, pyright, pytest with coverage). Shell completions: `par-stt --completion bash` (also `zsh`, `fish`).

## Publishing

Releases use **GitHub Actions Trusted Publishing (OIDC)** — there is no API token on disk, and no push/tag auto-trigger. Releases are a manual workflow dispatch.

### One-time PyPI / TestPyPI Trusted Publisher setup

Before the first release, register the project as a Trusted Publisher on both indexes:

1. On **PyPI** (`https://pypi.org/manage/project/par-cli-stt/publishing/`), add a Trusted Publisher pointing at:
   - PyPI project: `par-cli-stt`
   - Repository: `paulrobello/par-cli-stt`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
2. Repeat on **TestPyPI** (`https://test.pypi.org/manage/project/par-cli-stt/publishing/`) with environment name `testpypi`.
3. In the GitHub repo, create the `pypi` and `testpypi` environments (Settings → Environments).

### Release flow

```bash
# 1. Bump par_stt/__version__.py and commit.
# 2. Local sanity build:
make checkall && make package

# 3. Test publish (manual workflow dispatch on GitHub, or locally):
make test-publish   # uploads to TestPyPI; verify install from https://test.pypi.org

# 4. Production publish (manual workflow dispatch, or locally):
make publish        # uploads to PyPI
```

The GitHub workflow (`.github/workflows/publish.yml`) is `workflow_dispatch`-only with inputs for the publish target (`testpypi` | `pypi` | `both`), an optional GitHub Release, and a skip-tests toggle. It uses `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` (no API token secret).

## License

MIT — see [LICENSE](LICENSE).

## Author

**Paul Robello** — [paulrobello](https://github.com/paulrobello) — probello@gmail.com
