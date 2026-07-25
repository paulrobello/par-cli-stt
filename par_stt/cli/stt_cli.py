#!/usr/bin/env python
"""Command line tool for speech-to-text using multiple STT providers.

This module provides the ``par-stt`` CLI: it loads configuration, resolves a
provider + API key, reads an audio file, transcribes it, and writes/prints the
result in the requested format.
"""

import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import typer
from dotenv import load_dotenv
from rich.pretty import Pretty
from rich.table import Table

from par_stt import __version__
from par_stt.audio_input import read_audio
from par_stt.cli.completions import completion_install_instructions, generate_completion_script
from par_stt.cli.config_file import ConfigFile, ConfigManager
from par_stt.cli.console import console
from par_stt.defaults import DEFAULT_MODELS, DEFAULT_PROVIDER
from par_stt.errors import ErrorType, SttError, handle_error, set_debug_mode, validate_file_path
from par_stt.logging_config import configure_logging
from par_stt.provider_factory import create_provider
from par_stt.providers import PROVIDERS
from par_stt.providers.base import Transcript, TranscriptChunk
from par_stt.providers.registry import get_provider_plugin, get_provider_plugins
from par_stt.transcript_writer import TranscriptFormat, render_transcript, write_transcript

app = typer.Typer(help="Speech-to-text command line tool with multiple provider support")


def _run_cli() -> None:
    """Invoke the Typer app, catching SttError and translating to sys.exit().

    Library code raises :class:`SttError` instead of calling ``sys.exit`` so
    that programmatic users can handle errors gracefully.  This wrapper is the
    CLI boundary: it catches those exceptions, prints a user-friendly message,
    and exits with the appropriate code.
    """
    try:
        app()
    except SttError as exc:
        console.print(f"[red]{exc.error_type.display_name}:[/red] {exc.message}")
        sys.exit(exc.error_type.exit_code)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def handle_list_providers() -> None:
    """Display available STT providers using plugin metadata (no instantiation)."""
    console.print("[bold green]Available STT Providers:[/bold green]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Provider")
    table.add_column("Description")
    table.add_column("Default Model")

    for name, plugin in sorted(get_provider_plugins().items()):
        table.add_row(name, plugin.description, plugin.default_model)

    console.print(table)


def handle_capabilities() -> None:
    """Display provider capabilities from plugin metadata (no instantiation)."""
    console.print("[bold green]Provider Capabilities:[/bold green]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Provider", no_wrap=True)
    table.add_column("Source", no_wrap=True)
    table.add_column("Formats")
    table.add_column("Streaming", no_wrap=True)
    table.add_column("Lang Detect", no_wrap=True)
    table.add_column("Diarize", no_wrap=True)
    table.add_column("Punctuate", no_wrap=True)
    table.add_column("API Key", no_wrap=True)
    table.add_column("Default Model")

    for name, plugin in sorted(get_provider_plugins().items()):
        capabilities = plugin.capabilities
        table.add_row(
            name,
            plugin.source,
            ", ".join(capabilities.formats) or "unknown",
            _yes_no(capabilities.supports_streaming),
            _yes_no(capabilities.supports_language_detection),
            _yes_no(capabilities.supports_diarization),
            _yes_no(capabilities.supports_punctuation),
            "required" if plugin.requires_api_key else "not required",
            plugin.default_model,
        )

    console.print(table)


def handle_completion(shell: str) -> None:
    """Print a shell completion script without provider initialization."""
    sys.stdout.write(generate_completion_script(shell))


def handle_completion_install(shell: str) -> None:
    """Print shell-specific completion installation instructions."""
    console.print(completion_install_instructions(shell))


def get_api_key(provider: str, config_file: ConfigFile | None) -> str | None:
    """Resolve an API key for *provider* from the config file then environment.

    Returns None for providers that do not require a key.  Raises :class:`SttError`
    (via :func:`handle_error`, which logs the message) when a required key is
    missing everywhere.
    """
    try:
        plugin = get_provider_plugin(provider)
    except ValueError as exc:
        handle_error(str(exc), ErrorType.INVALID_PROVIDER, exception=exc)

    if not plugin.requires_api_key:
        return None

    config_field_map: dict[str, str] = {
        "elevenlabs": "elevenlabs_api_key",
        "deepgram": "deepgram_api_key",
    }
    config_field = config_field_map.get(provider)
    if config_file and config_field:
        api_key = getattr(config_file, config_field, None)
        if api_key:
            return api_key

    for env_var in plugin.api_key_env_vars:
        api_key = os.getenv(env_var)
        if api_key:
            return api_key

    if plugin.api_key_env_vars:
        primary = plugin.api_key_env_vars[0]
        alt = f" (also accepts {', '.join(plugin.api_key_env_vars[1:])})" if len(plugin.api_key_env_vars) > 1 else ""
        handle_error(
            f"{primary} not found. Set {primary}{alt} in your config file or environment.",
            ErrorType.MISSING_API_KEY,
        )

    handle_error(
        f"Provider '{provider}' requires an API key but does not declare api_key_env_vars",
        ErrorType.MISSING_API_KEY,
    )


def get_transcribe_kwargs(
    provider: str,
    *,
    diarize: bool | None,
    smart_format: bool | None,
    punctuate: bool | None,
    profanity_filter: bool | None,
    tag_audio_events: bool | None,
) -> dict[str, Any]:
    """Build provider-specific ``transcribe`` kwargs from CLI flags.

    Only keys the active provider declares in ``PROVIDER_KWARGS`` are returned,
    so a single CLI flag surface can drive both Deepgram and Scribe without
    if/elif chains.  ``None`` (unset) values are dropped so config/defaults win.
    """
    all_options: dict[str, Any] = {
        "smart_format": smart_format,
        "punctuate": punctuate,
        "profanity_filter": profanity_filter,
        "diarize": diarize,
        "filler_words": None,
        "tag_audio_events": tag_audio_events,
    }
    provider_class = PROVIDERS.get(provider)
    accepted = set(provider_class.PROVIDER_KWARGS) if provider_class and provider_class.PROVIDER_KWARGS else set()
    return {key: value for key, value in all_options.items() if key in accepted and value is not None}


def handle_dump_config(
    *,
    provider: str,
    model: str | None,
    language: str | None,
    output_format: str,
    output: Path | None,
    diarize: bool | None,
    smart_format: bool | None,
    punctuate: bool | None,
    profanity_filter: bool | None,
    tag_audio_events: bool | None,
    retry_attempts: int,
    retry_backoff: float,
    config_file: ConfigFile | None,
    config_manager: ConfigManager,
) -> None:
    """Dump the resolved configuration and exit."""
    resolved_model = model or DEFAULT_MODELS.get(provider, "default")
    config: dict[str, Any] = {
        "provider": provider,
        "model": resolved_model,
        "language": language,
        "output_format": output_format,
        "output": str(output) if output else None,
        "transcribe_kwargs": get_transcribe_kwargs(
            provider,
            diarize=diarize,
            smart_format=smart_format,
            punctuate=punctuate,
            profanity_filter=profanity_filter,
            tag_audio_events=tag_audio_events,
        ),
        "retry_attempts": retry_attempts,
        "retry_backoff": retry_backoff,
    }

    console.print("[bold cyan]Configuration:[/bold cyan]")
    console.print(Pretty(config))

    if config_file:
        console.print(f"\n[dim]Config file loaded from: {config_manager.config_file}[/dim]")
    else:
        console.print(f"\n[dim]No config file found at: {config_manager.config_file}[/dim]")
        console.print("[dim]Use --create-config to create a sample configuration file[/dim]")


def _print_transcript(transcript: Transcript, fmt: TranscriptFormat) -> None:
    """Render *transcript* in *fmt* to stdout."""
    rendered = render_transcript(transcript, fmt)
    console.print(rendered, markup=False, highlight=False)


def handle_transcription(
    *,
    audio_path: str,
    stt_provider: Any,
    provider: str,
    model: str | None,
    language: str | None,
    output_format: TranscriptFormat,
    output: Path | None,
    transcribe_kwargs: dict[str, Any],
    debug: bool,
) -> None:
    """Read *audio_path*, transcribe it, and write/print the result."""
    start_time = time.perf_counter()
    console.print("[cyan]Loading audio...[/cyan]")
    pcm_bytes = read_audio(audio_path)
    if debug:
        console.print(f"[dim]Loaded {len(pcm_bytes)} bytes of canonical PCM[/dim]")

    console.print(f"[cyan]Transcribing with {stt_provider.name}...[/cyan]")
    result = stt_provider.transcribe(pcm_bytes, language=language, model=model, **transcribe_kwargs)
    transcript = _result_to_transcript(result, language=language)

    if output:
        destination = write_transcript(transcript, output_format, output)
        console.print(f"[green]Transcript saved to: {destination}[/green]")
    else:
        _print_transcript(transcript, output_format)

    elapsed = time.perf_counter() - start_time
    chunk_count = len(transcript.chunks)
    console.print(
        "[bold cyan]Summary:[/bold cyan] "
        f"provider={stt_provider.name}, model={model or stt_provider.default_model}, "
        f"format={output_format.value}, {len(transcript.text)} chars, "
        f"{chunk_count} chunk(s), elapsed={elapsed:.2f}s"
    )
    console.print("[green]Transcription complete![/green]")


def _result_to_transcript(result: Any, *, language: str | None) -> Transcript:
    """Collapse a provider result into a :class:`Transcript`."""
    if isinstance(result, Transcript):
        return result
    if isinstance(result, (list, tuple)) or hasattr(result, "__iter__"):
        chunks: list[TranscriptChunk] = []
        iterator: Iterator[TranscriptChunk] = iter(result)
        for chunk in iterator:
            if isinstance(chunk, TranscriptChunk):
                chunks.append(chunk)
        text = (
            " ".join(chunk.text for chunk in chunks if chunk.is_final).strip()
            or " ".join(chunk.text for chunk in chunks).strip()
        )
        return Transcript(text=text, chunks=chunks, language=language)
    handle_error("Provider returned an unsupported transcription result", ErrorType.PROVIDER_ERROR)


@app.command()
def main(
    audio: Annotated[
        str | None,
        typer.Argument(help="Audio file to transcribe (wav, mp3, m4a, ogg, flac, webm)"),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option(
            "-P",
            "--provider",
            help="STT provider to use (deepgram, elevenlabs)",
            envvar="STT_PROVIDER",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "-m",
            "--model",
            help="Model to use (provider-specific)",
            envvar="STT_MODEL",
        ),
    ] = None,
    language: Annotated[
        str | None,
        typer.Option(
            "-l",
            "--language",
            help="Language hint (e.g. 'en', 'en-US'). Omit to let the provider auto-detect.",
            envvar="STT_LANGUAGE",
        ),
    ] = None,
    output_format: Annotated[
        str | None,
        typer.Option(
            "-f",
            "--format",
            help="Output format: txt, srt, vtt, json",
            envvar="STT_FORMAT",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Output file path for the transcript (omitted = stdout)",
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            help="Named config profile to apply",
        ),
    ] = None,
    # Provider-specific transcription options.
    diarize: Annotated[
        bool | None,
        typer.Option(
            "--diarize/--no-diarize",
            help="Label distinct speakers (both providers)",
        ),
    ] = None,
    smart_format: Annotated[
        bool | None,
        typer.Option(
            "--smart-format/--no-smart-format",
            help="Deepgram smart-format post-processing",
        ),
    ] = None,
    punctuate: Annotated[
        bool | None,
        typer.Option(
            "--punctuate/--no-punctuate",
            help="Deepgram automatic punctuation",
        ),
    ] = None,
    profanity_filter: Annotated[
        bool | None,
        typer.Option(
            "--profanity-filter/--no-profanity-filter",
            help="Deepgram profanity filter",
        ),
    ] = None,
    tag_audio_events: Annotated[
        bool | None,
        typer.Option(
            "--tag-audio-events/--no-tag-audio-events",
            help="ElevenLabs Scribe audio-event tagging",
        ),
    ] = None,
    # Reliability / observability.
    debug: Annotated[
        bool,
        typer.Option(
            "-d",
            "--debug",
            help="Show debug information",
        ),
    ] = False,
    structured_logs: Annotated[
        bool,
        typer.Option(
            "--structured-logs",
            help="Emit JSON logs for automation and telemetry ingestion",
        ),
    ] = False,
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        ),
    ] = None,
    retry_attempts: Annotated[
        int | None,
        typer.Option(
            "--retry-attempts",
            help="Retries after the initial provider attempt",
            min=0,
            max=10,
        ),
    ] = None,
    retry_backoff: Annotated[
        float | None,
        typer.Option(
            "--retry-backoff",
            help="Initial exponential retry backoff in seconds",
            min=0.0,
            max=60.0,
        ),
    ] = None,
    # Exit-early / utility flags.
    list_providers: Annotated[
        bool,
        typer.Option(
            "-L",
            "--list-providers",
            help="List available providers and exit",
        ),
    ] = False,
    capabilities: Annotated[
        bool,
        typer.Option(
            "--capabilities",
            help="Show provider capability matrix and exit",
        ),
    ] = False,
    dump_config: Annotated[
        bool,
        typer.Option(
            "-D",
            "--dump",
            help="Dump resolved configuration and exit",
        ),
    ] = False,
    create_config: Annotated[
        bool,
        typer.Option(
            "--create-config",
            help="Create a sample configuration file",
        ),
    ] = False,
    completion: Annotated[
        str | None,
        typer.Option(
            "--completion",
            metavar="SHELL",
            help="Print shell completion script for bash, zsh, or fish and exit",
        ),
    ] = None,
    completion_install: Annotated[
        str | None,
        typer.Option(
            "--completion-install",
            metavar="SHELL",
            help="Print shell completion installation instructions and exit",
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show version and exit",
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "-y",
            "--yes",
            help="Answer yes to confirmations (e.g. overwriting an existing config)",
        ),
    ] = False,
) -> None:
    """Transcribe an audio file to text using the specified STT provider.

    Audio is read from a file argument and converted to text using the provider
    selected via ``-P/--provider`` (or ``STT_PROVIDER``). The transcript is
    written to ``--output`` or printed to stdout in the requested ``--format``.
    """
    if version:
        console.print(f"par-stt {__version__}")
        raise typer.Exit()

    if completion:
        try:
            handle_completion(completion)
        except SttError as exc:
            console.print(f"[red]{exc.error_type.display_name}:[/red] {exc.message}")
            raise typer.Exit(code=exc.error_type.exit_code) from exc
        return

    if completion_install:
        try:
            handle_completion_install(completion_install)
        except SttError as exc:
            console.print(f"[red]{exc.error_type.display_name}:[/red] {exc.message}")
            raise typer.Exit(code=exc.error_type.exit_code) from exc
        return

    load_dotenv()

    config_manager = ConfigManager()
    if create_config:
        config_manager.create_sample_config(force=yes)
        return

    config_file = config_manager.load_config()
    if config_file and profile:
        try:
            config_file = config_manager.apply_profile(config_file, profile)
            console.print(f"[dim]Applied profile: {profile}[/dim]")
        except ValueError as exc:
            handle_error(str(exc), ErrorType.CONFIG_ERROR, exception=exc)

    # Apply config-file defaults — CLI args (non-None) always win.
    if config_file:
        provider = provider or config_file.provider
        model = model or config_file.model
        language = language if language is not None else config_file.language
        output_format = output_format or config_file.output_format
        output = output or (Path(config_file.output_dir) / "transcript.txt" if config_file.output_dir else None)
        diarize = diarize if diarize is not None else config_file.diarize
        debug = debug or config_file.debug or False
        structured_logs = structured_logs or config_file.structured_logs or False
        log_level = log_level or config_file.log_level
        retry_attempts = retry_attempts if retry_attempts is not None else config_file.retry_attempts
        retry_backoff = retry_backoff if retry_backoff is not None else config_file.retry_backoff

    # Hardcoded fallbacks for anything still unset.
    if output_format is None:
        output_format = "txt"
    if log_level is None:
        log_level = "DEBUG" if debug else "WARNING"
    if retry_attempts is None:
        retry_attempts = 0
    if retry_backoff is None:
        retry_backoff = 0.0
    if not provider:
        provider = DEFAULT_PROVIDER

    set_debug_mode(debug)
    try:
        configure_logging(structured=structured_logs, level=log_level)
    except ValueError as exc:
        handle_error(str(exc), ErrorType.CONFIG_ERROR, exception=exc)

    # Resolve the output format early so a bad value fails before network work.
    resolved_format = TranscriptFormat.from_value(output_format)

    # Exit-early metadata commands that never need an audio file or a provider.
    if list_providers:
        handle_list_providers()
        return

    if capabilities:
        handle_capabilities()
        return

    if dump_config:
        handle_dump_config(
            provider=provider,
            model=model,
            language=language,
            output_format=resolved_format.value,
            output=output,
            diarize=diarize,
            smart_format=smart_format,
            punctuate=punctuate,
            profanity_filter=profanity_filter,
            tag_audio_events=tag_audio_events,
            retry_attempts=retry_attempts,
            retry_backoff=retry_backoff,
            config_file=config_file,
            config_manager=config_manager,
        )
        return

    # Everything from here requires an audio file.
    if audio is None:
        handle_error(
            "AUDIO argument is required. Use --help for more information.",
            ErrorType.INVALID_INPUT,
        )
    validate_file_path(audio)

    api_key = get_api_key(provider, config_file)
    stt_provider = create_provider(
        provider,
        api_key=api_key,
        provider_kwargs={
            "retry_attempts": retry_attempts,
            "retry_backoff": retry_backoff,
        },
    )

    handle_transcription(
        audio_path=audio,
        stt_provider=stt_provider,
        provider=provider,
        model=model,
        language=language,
        output_format=resolved_format,
        output=output,
        transcribe_kwargs=get_transcribe_kwargs(
            provider,
            diarize=diarize,
            smart_format=smart_format,
            punctuate=punctuate,
            profanity_filter=profanity_filter,
            tag_audio_events=tag_audio_events,
        ),
        debug=debug,
    )


if __name__ == "__main__":
    _run_cli()
