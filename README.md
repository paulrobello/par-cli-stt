# PAR CLI STT

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
![Runs on Linux | MacOS | Windows](https://img.shields.io/badge/runs%20on-Linux%20%7C%20MacOS%20%7C%20Windows-blue)
![Arch x86-64 | ARM | AppleSilicon](https://img.shields.io/badge/arch-x86--64%20%7C%20ARM%20%7C%20AppleSilicon-blue)

![MIT License](https://img.shields.io/badge/license-MIT-green.svg)
![Version](https://img.shields.io/pypi/v/par-cli-stt.svg)
![Development Status](https://img.shields.io/badge/status-pre--alpha-yellow.svg)

A streaming speech-to-text library and command-line tool supporting multiple STT providers (ElevenLabs Scribe and Deepgram Nova-3) with typed provider options, a plugin architecture, and flexible output formats (plain text, SRT, VTT, JSON).

**Use as a CLI** — `par-stt recording.wav`
**Use as a library** — `from par_stt import create_provider`

**Companion project:** [par-cli-tts](https://github.com/paulrobello/par-cli-tts) — the text-to-speech counterpart (ElevenLabs, OpenAI, Kokoro, Deepgram, Gemini).

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/probello3)

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [From PyPI](#installation-from-pypi-recommended)
  - [From Source](#installation-from-source)
- [Configuration](#configuration)
- [Usage](#usage)
- [Command Line Options](#command-line-options)
- [Providers](#providers)
- [Diagnostics](#diagnostics)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Publishing](#publishing)
- [License](#license)
- [Author](#author)
- [Acknowledgments](#acknowledgments)
- [Support](#support)

## Features

- **Two launch providers** - Deepgram **Nova-3** (streaming WebSocket, interim + final chunks) and ElevenLabs **Scribe** (batch, full transcript with language detection)
- **Streaming-first core** - Every provider exposes a uniform `transcribe_async()` surface; batch providers inherit a sync-wrapping default
- **Plugin registry** - Built-in providers plus third-party discovery via the `par_stt.providers` entry-point group
- **Flexible output** - Render transcripts as `txt`, `srt`, `vtt`, or `json`
- **Configuration file** - Set defaults in a YAML config file with optional named profiles, or use environment variables
- **Typed options** - `DeepgramOptions` / `ScribeOptions` dataclasses with schema introspection
- **Cost estimates** - Static per-minute pricing for quick planning
- **Retry controls** - Per-run or config-file retry/backoff settings for provider calls
- **Rich terminal output** - Colored output with post-transcription summaries
- **Security first** - API keys read from config (mode `0o600`) or environment, sanitized in debug output
- **CLI** - Typer + Rich: `--capabilities`, `--dump`, `--profile`, shell completions, and more

## Technology Stack

- **Python 3.11+** - Modern Python with type hints and async support
- **ElevenLabs SDK** - Official client for Scribe batch transcription
- **Deepgram WebSocket** - Streaming Nova-3 transcription via the `websockets` library (no SDK)
- **Typer** - Modern CLI framework with automatic help generation
- **Rich** - Terminal formatting and beautiful output
- **Pydantic** - Data validation and settings management
- **Platformdirs** - Cross-platform directory management
- **PyYAML** - Configuration file parsing
- **Python-dotenv** - Environment variable management
- **NumPy / SoundFile** - Audio loading and 16 kHz mono resampling

Builds with `hatchling`; gates with `ruff` + `pyright` + `pytest`.

## Prerequisites

To install PAR CLI STT, make sure you have Python 3.11+ installed.

### [uv](https://pypi.org/project/uv/) is recommended

#### Linux and Mac
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Windows
```bash
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

You will also need at least one provider API key:

- An **ElevenLabs** API key for Scribe (the default provider)
- And/or a **Deepgram** API key for Nova-3

`libsndfile` (bundled with the `soundfile` wheel on most platforms) is required for audio loading.

## Installation

### Installation from PyPI (Recommended)

Install the latest version using uv:

```bash
uv tool install par-cli-stt
```

Or using pip:

```bash
pip install par-cli-stt
```

After installation, you can run the tool directly:

```bash
# Transcribe a file (uses the default provider, ElevenLabs Scribe)
par-stt recording.wav

# Show help
par-stt --help
```

#### Shell completions

Generate shell completion scripts directly from the installed CLI:

```bash
par-stt --completion bash > ~/.local/share/bash-completion/completions/par-stt
par-stt --completion zsh > ~/.zfunc/_par-stt
par-stt --completion fish > ~/.config/fish/completions/par-stt.fish

# Or print shell-specific installation guidance
par-stt --completion-install bash
```

### Installation From Source

For development or to get the latest features:

1. Clone the repository:
   ```bash
   git clone https://github.com/paulrobello/par-cli-stt.git
   cd par-cli-stt
   ```

2. Install the package dependencies using uv:
   ```bash
   uv sync
   ```

3. Run using uv:
   ```bash
   uv run par-stt recording.wav
   ```

## Configuration

API keys can be provided through environment variables or the config file. The config file is the recommended store for keys and is created with mode `0o600` (owner-only read/write).

Create a sample config file:

```bash
# Create a sample config file (prompts before overwriting if one exists)
par-stt --create-config

# Skip the overwrite prompt with -y / --yes (e.g. for scripted setup)
par-stt --create-config -y

# Edit the config file
$EDITOR ~/Library/Application\ Support/par-stt/config.yaml   # macOS
$EDITOR ~/.config/par-stt/config.yaml                        # Linux
```

Example configuration file:

```yaml
# Default provider (elevenlabs, deepgram)
provider: elevenlabs

# Default model
# ElevenLabs Scribe (batch): scribe_v1
# Deepgram Nova-3 (streaming): nova-3
model: scribe_v1

# Default language hint (e.g. 'en', 'en-US'). Omit to let the provider auto-detect.
language: en

# Default output format: txt, srt, vtt, json
output_format: txt

# Default output directory for transcripts (omitted = current directory)
# output_dir: ~/Documents/transcripts

# API keys (optional - can also be set via environment variables)
elevenlabs_api_key: your-elevenlabs-api-key-here
deepgram_api_key: your-deepgram-api-key-here

# Named profiles override the base settings above when selected with --profile NAME.
profiles:
  meetings:
    provider: deepgram
    language: en
    diarize: true
  interviews:
    provider: elevenlabs
    diarize: true
```

If you already have an ElevenLabs key in `par-tts`'s config, copy the same value here — the field name is identical.

### Environment Variables

| Variable | Providers | Purpose |
|----------|-----------|---------|
| `ELEVENLABS_API_KEY` | elevenlabs | Scribe API key |
| `DEEPGRAM_API_KEY` | deepgram | Deepgram API key (`DG_API_KEY` is also accepted) |
| `STT_PROVIDER` | both | Default provider (`elevenlabs`, `deepgram`) |
| `STT_MODEL` | both | Default model override |
| `STT_LANGUAGE` | both | Default language hint |
| `STT_FORMAT` | both | Default output format (`txt`, `srt`, `vtt`, `json`) |

Precedence: CLI flags > config file > environment variables.

## Usage

### Quick Start

If installed from PyPI:
```bash
# Transcribe with the default provider (ElevenLabs Scribe)
par-stt recording.wav

# Use Deepgram Nova-3 streaming instead
par-stt recording.wav --provider deepgram

# Write an SRT subtitle file
par-stt meeting.wav --provider deepgram --format srt --output meeting.srt

# Use a profile and a language hint
par-stt interview.mp3 --profile interviews --language en

# Label distinct speakers
par-stt panel.wav --provider deepgram --diarize

# Inspect providers without making a network call
par-stt --capabilities
par-stt --list-providers
par-stt --dump
```

If running from source, prefix commands with `uv run`:
```bash
uv run par-stt recording.wav
uv run par-stt recording.wav --provider deepgram
```

### Library Usage

PAR STT can be used as a Python library in your own projects:

```python
import par_stt

print(par_stt.__version__)
print(par_stt.list_providers())  # ['deepgram', 'elevenlabs']

# Sync batch transcription (returns a Transcript)
provider = par_stt.create_provider("elevenlabs", api_key=os.environ["ELEVENLABS_API_KEY"])
pcm = par_stt.read_audio("recording.wav")          # -> 16 kHz mono int16 PCM bytes
transcript = provider.transcribe(pcm, language="en")
print(transcript.text)
print(transcript.detected_language)
```

Deepgram exposes native async streaming (interim + final chunks):

```python
import asyncio

provider = par_stt.create_provider("deepgram", api_key=os.environ["DEEPGRAM_API_KEY"])
pcm = par_stt.read_audio("recording.wav")

async def main() -> None:
    async for chunk in provider.transcribe_async(pcm):
        print(("FINAL " if chunk.is_final else "partial ") + chunk.text)

asyncio.run(main())
```

Render and write transcripts in any supported format:

```python
par_stt.write_transcript(transcript, "srt", "out.srt")
par_stt.write_transcript(transcript, "json", "out.json")
```

The `TranscriptionPipeline` keeps a provider instance plus defaults for repeated use:

```python
from par_stt import TranscriptionPipeline

pipeline = TranscriptionPipeline.from_provider_name(
    "elevenlabs", api_key=os.environ["ELEVENLABS_API_KEY"], language="en"
)
transcript = pipeline.transcribe_file("recording.wav")
```

## Command Line Options

### Core Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `AUDIO` | | Audio file to transcribe (wav, mp3, m4a, ogg, flac, webm) | Required |
| `--provider` | `-P` | STT provider (`elevenlabs`, `deepgram`) | `elevenlabs` |
| `--model` | `-m` | Model override (provider-specific) | Provider default |
| `--language` | `-l` | Language hint (e.g. `en`, `en-US`); omit for auto-detect | None |
| `--format` | `-f` | Output format (`txt`, `srt`, `vtt`, `json`) | `txt` |
| `--output` | `-o` | Output file path (omitted = stdout) | None |
| `--profile` | | Named config profile to apply | None |

### Provider Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--diarize` / `--no-diarize` | | Label distinct speakers (both providers) | Provider default |
| `--smart-format` / `--no-smart-format` | | Deepgram smart-format post-processing | `True` |
| `--punctuate` / `--no-punctuate` | | Deepgram automatic punctuation | `True` |
| `--profanity-filter` / `--no-profanity-filter` | | Deepgram profanity filter | `False` |
| `--tag-audio-events` / `--no-tag-audio-events` | | ElevenLabs audio-event tagging | `False` |

### Utility Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--debug` | `-d` | Show debug information (API keys sanitized) | False |
| `--structured-logs` | | Emit JSON logs for automation/telemetry ingestion | False |
| `--log-level` | | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) | `WARNING` (`DEBUG` with `--debug`) |
| `--retry-attempts` | | Retries after the initial provider attempt | 0 |
| `--retry-backoff` | | Initial exponential retry backoff in seconds | 0.0 |
| `--dump` | `-D` | Dump resolved configuration and exit | False |
| `--capabilities` | | Show provider capability matrix and exit | False |
| `--list-providers` | `-L` | List available STT providers and exit | False |
| `--create-config` | | Create a sample configuration file | False |
| `--completion` | | Print shell completion script for `bash`, `zsh`, or `fish` | None |
| `--completion-install` | | Print shell completion install instructions | None |
| `--version` | | Show version and exit | False |
| `--yes` | `-y` | Skip confirmation prompts (e.g. config overwrite) | False |

## Providers

### Provider plugins

Providers are discovered through plugin descriptors. The bundled providers are
registered as built-in plugins, and third-party packages can expose additional
providers with the Python entry point group `par_stt.providers`.

A plugin entry point may load one of:

- a `par_stt.providers.ProviderPlugin` object
- a zero-argument factory returning `ProviderPlugin`
- an `SttProvider` subclass with metadata attributes such as `plugin_name`,
  `plugin_description`, `plugin_capabilities`, `plugin_default_model`, and
  `plugin_requires_api_key`

Example third-party `pyproject.toml`:

```toml
[project.entry-points."par_stt.providers"]
my-provider = "my_package.stt:provider_plugin"
```

Use `par-stt --capabilities` to see built-in and installed plugin capabilities
without initializing providers or requiring API keys.

### ElevenLabs Scribe

- **Model**: `scribe_v1` (default)
- **Mode**: Batch — accepts a complete audio file and returns the full transcript with detected language and word timing
- **Features**: Language auto-detection, speaker diarization, audio-event tagging
- **Input**: Container files (wav, mp3, m4a, ogg, flac, webm) are auto-detected; raw 16 kHz mono int16 PCM is reported as `pcm_s16le_16` automatically (this is what `read_audio` emits)
- **Output Formats**: txt, srt, vtt, json
- **Streaming**: No (batch only); `transcribe_async()` yields the finalized transcript via the sync-wrapping default
- **API key**: `elevenlabs_api_key` in config, or `ELEVENLABS_API_KEY` env var
- **Cost**: ~$0.0065/min (approximate; verify against current ElevenLabs pricing)

### Deepgram Nova-3

- **Model**: `nova-3` (default)
- **Mode**: Streaming over WebSocket — emits interim partials and finalized chunks as audio is processed
- **Features**: Language auto-detection, smart format, punctuation, profanity filter, speaker diarization, filler words
- **Input**: 16 kHz mono Linear16 PCM streamed to Deepgram (the library resamples and downmixes for you via `read_audio`)
- **Output Formats**: txt, srt, vtt, json
- **Streaming**: Yes (native `transcribe_async()`)
- **API key**: `deepgram_api_key` in config, or `DEEPGRAM_API_KEY` / `DG_API_KEY` env var. Get a key at <https://console.deepgram.com>.
- **Cost**: ~$0.0043/min (= $4,300 per million minutes)

## Diagnostics

Offline environment checks are available to library consumers and the CLI — no network access required:

```python
from par_stt import collect_diagnostics

for check in collect_diagnostics():
    print(check.name, check.ok, check.detail)
```

Checks cover provider API-key environment variables, the config file, the `soundfile`/`libsndfile` audio backend, and the optional `ffmpeg` binary.

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/paulrobello/par-cli-stt.git
cd par-cli-stt

# Install dependencies
uv sync

# Run tests
uv run pytest

# Run formatting, linting, and type checks
make checkall
```

### Development Commands

```bash
# Format, lint, and type check
make checkall

# Individual commands
make format      # Format with ruff
make lint        # Lint with ruff
make typecheck   # Type check with pyright

# Build and package
make package     # Build distribution packages
make clean       # Clean build artifacts
```

### Project Structure

| Path | Purpose |
|------|---------|
| `par_stt/__init__.py` | Public library API for providers, pipelines, options, diagnostics, costs, and helpers |
| `par_stt/audio_input.py` | Audio loading, downmix, and 16 kHz mono int16 PCM resampling |
| `par_stt/cli/` | CLI entry point, config-file handling, shell completions, and console output |
| `par_stt/costs.py` | Static transcription cost estimates |
| `par_stt/defaults.py` | Provider and model defaults |
| `par_stt/diagnostics.py` | Offline diagnostic checks for audio backends, config, and API-key env vars |
| `par_stt/errors.py` | `SttError`, categorized exit codes, path validation, and user-facing error handling |
| `par_stt/http_client.py` | Shared HTTP client factory for API providers |
| `par_stt/logging_config.py` | Human-readable and structured JSON logging configuration |
| `par_stt/pipeline.py` | Reusable `TranscriptionPipeline` orchestration for library consumers |
| `par_stt/provider_factory.py` | Public provider factory that resolves provider plugins and API keys |
| `par_stt/providers/` | Built-in provider implementations, base abstractions, typed options, and plugin registry |
| `par_stt/retry.py` | Retry/backoff policy for provider transcription calls |
| `par_stt/transcript_writer.py` | txt/srt/vtt/json transcript rendering and file writing |
| `par_stt/utils.py` | Shared utility helpers |
| `tests/` | Pytest suite |
| `pyproject.toml` | Package metadata, dependencies, scripts, and build configuration |
| `Makefile` | Development, verification, and packaging commands |

## Troubleshooting

### Common Issues

1. **API Key Not Found**
   - Ensure `ELEVENLABS_API_KEY` and/or `DEEPGRAM_API_KEY` is set, or add the key to the config file under `elevenlabs_api_key:` / `deepgram_api_key:`
   - Verify environment variable names match exactly (`DG_API_KEY` is also accepted for Deepgram)

2. **"File is corrupted" / `invalid_audio` from Scribe (library use)**
   - Scribe needs to know how to decode the bytes. The CLI handles this automatically; when calling the library with raw PCM, pass `file_format="pcm_s16le_16"` or let the provider sniff it from container magic bytes.

3. **m4a / webm files fail to decode**
   - The `soundfile` (libsndfile) backend does not read m4a/webm containers. Convert to wav, mp3, flac, or ogg first (e.g. `ffmpeg -i in.m4a -ar 16000 -ac 1 out.wav`).

4. **Configuration File Issues**
   - Run `--create-config` to generate a sample config
   - Check file location: `~/Library/Application Support/par-stt/config.yaml` (macOS) or `~/.config/par-stt/config.yaml` (Linux)
   - Verify YAML syntax (use spaces, not tabs)
   - CLI arguments override config file settings

5. **Streaming errors (Deepgram)**
   - Verify network connectivity and that `DEEPGRAM_API_KEY` is valid
   - Use `--debug` to inspect the WebSocket lifecycle

### Debug Mode

Enable debug mode for detailed information:

```bash
# Show debug information during execution
par-stt recording.wav -d

# Dump resolved configuration without transcribing
par-stt --dump
```

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and checks (`make checkall`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Development Guidelines

- Use type hints for all function parameters and returns
- Follow Google-style docstrings
- Ensure all tests pass before submitting a PR
- Update documentation for new features
- Keep commits atomic and well-described

## Publishing

Releases use **GitHub Actions Trusted Publishing (OIDC)** — there is no API token on disk, and no push/tag auto-trigger. Releases are a manual workflow dispatch.

### One-time PyPI / TestPyPI Trusted Publisher setup

Before the first release, register the project as a Trusted Publisher on both indexes:

1. On **PyPI** (`https://pypi.org/manage/project/par-cli-stt/publishing/`), add a Trusted Publisher pointing at:
   - PyPI project: `par-cli-stt`
   - Owner: `paulrobello`
   - Repository: `paulrobello/par-cli-stt`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
2. Repeat on **TestPyPI** (`https://test.pypi.org/manage/project/par-cli-stt/publishing/`) with environment name `testpypi`.
3. In the GitHub repo, create the `pypi` and `testpypi` environments (Settings → Environments).

### Release flow

```bash
# 1. Bump the version in par_stt/__init__.py and commit.
# 2. Local sanity build:
make checkall && make package

# 3. Test publish (manual workflow dispatch on GitHub, or locally):
make test-publish   # uploads to TestPyPI; verify install from https://test.pypi.org

# 4. Production publish (manual workflow dispatch, or locally):
make publish        # uploads to PyPI
```

The GitHub workflow (`.github/workflows/publish.yml`) is `workflow_dispatch`-only with inputs for the publish target (`testpypi` | `pypi` | `both`), an optional GitHub Release, and a skip-tests toggle. It uses `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` (no API token secret).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Author

**Paul Robello**
Email: [probello@gmail.com](mailto:probello@gmail.com)
GitHub: [@paulrobello](https://github.com/paulrobello)

## Acknowledgments

- [ElevenLabs](https://elevenlabs.io/) for the Scribe speech-to-text API
- [Deepgram](https://deepgram.com/) for the Nova-3 streaming API
- [Typer](https://typer.tiangolo.com/) for the elegant CLI framework
- [Rich](https://rich.readthedocs.io/) for beautiful terminal formatting

## Support

If you find this tool useful, consider:
- Starring the repository
- Reporting bugs or requesting features
- Improving documentation
- [Buying me a coffee](https://buymeacoffee.com/probello3)
