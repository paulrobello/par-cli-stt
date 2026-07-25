"""CLI behavior tests for par-stt (no real provider/network calls)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from par_stt.cli import stt_cli
from par_stt.cli.completions import generate_completion_script
from par_stt.cli.config_file import ConfigManager
from par_stt.providers.base import Transcript, TranscriptChunk


@pytest.fixture(autouse=True)
def isolate_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep CLI tests independent from the developer's real config file."""
    monkeypatch.setattr(
        "par_stt.cli.config_file.platformdirs.user_config_dir",
        lambda name: str(tmp_path / name),
    )


class FakeProvider:
    """Provider test double for CLI tests."""

    PROVIDER_KWARGS: dict[str, Any] = {
        "smart_format": True,
        "punctuate": True,
        "profanity_filter": False,
        "diarize": False,
        "filler_words": False,
        "tag_audio_events": False,
    }

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        self.api_key = api_key
        self.transcribe_calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "Fake STT"

    @property
    def supported_formats(self) -> list[str]:
        return ["wav", "mp3"]

    @property
    def default_model(self) -> str:
        return "fake-model"

    @property
    def supports_streaming(self) -> bool:
        return True

    def transcribe(
        self,
        audio: bytes | Iterator[bytes],
        *,
        language: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> Transcript:
        self.transcribe_calls.append({"language": language, "model": model, "kwargs": kwargs})
        chunk = TranscriptChunk(text="hello world", start_ms=0.0, end_ms=1500.0, is_final=True)
        return Transcript(text="hello world", chunks=[chunk], language=language, detected_language="eng")


def _install_fake_provider(monkeypatch: pytest.MonkeyPatch, fake: FakeProvider) -> None:
    """Route ``create_provider`` in the CLI to *fake* and set a dummy key."""
    monkeypatch.setattr(stt_cli, "create_provider", lambda *args, **kwargs: fake)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake-deepgram-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-elevenlabs-key")


def test_help_lists_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    """``par-stt --help`` should exit 0 and describe transcription."""
    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--help"])
    assert result.exit_code == 0
    assert "transcribe" in result.output.lower() or "audio" in result.output.lower()


def test_version_prints_package_version() -> None:
    """``par-stt --version`` should print the package version and exit 0."""
    from par_stt import __version__

    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "par-stt" in result.output


def test_capabilities_prints_matrix_without_creating_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--capabilities`` should inspect plugin metadata without provider side effects."""
    from rich.console import Console

    # Render wide so provider names are not truncated by Rich's column packing
    # in the narrow default test terminal.
    monkeypatch.setattr(stt_cli, "console", Console(width=200))

    def fail_create_provider(*args: Any, **kwargs: Any) -> FakeProvider:
        raise AssertionError("capabilities should not create a provider")

    monkeypatch.setattr(stt_cli, "create_provider", fail_create_provider)

    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--capabilities"])

    assert result.exit_code == 0
    assert "Provider Capabilities" in result.output
    assert "deepgram" in result.output
    assert "elevenlabs" in result.output
    assert "Streaming" in result.output


def test_list_providers_uses_plugin_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--list-providers`` should not instantiate providers."""

    def fail_create_provider(*args: Any, **kwargs: Any) -> FakeProvider:
        raise AssertionError("list-providers should not create a provider")

    monkeypatch.setattr(stt_cli, "create_provider", fail_create_provider)

    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--list-providers"])

    assert result.exit_code == 0
    assert "Available STT Providers" in result.output
    assert "deepgram" in result.output
    assert "elevenlabs" in result.output


def test_transcribe_happy_path_prints_text(
    monkeypatch: pytest.MonkeyPatch,
    temp_audio_file: Path,
) -> None:
    """A normal transcription should print the transcript text and a summary."""
    runner = CliRunner()
    fake = FakeProvider()
    _install_fake_provider(monkeypatch, fake)

    result = runner.invoke(stt_cli.app, [str(temp_audio_file), "--provider", "deepgram", "--format", "txt"])

    assert result.exit_code == 0, result.output
    assert "hello world" in result.output
    assert "Summary" in result.output
    assert len(fake.transcribe_calls) == 1
    assert fake.transcribe_calls[0]["language"] is None


def test_transcribe_writes_output_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    temp_audio_file: Path,
) -> None:
    """``--output`` should write the rendered transcript to the given path."""
    runner = CliRunner()
    fake = FakeProvider()
    _install_fake_provider(monkeypatch, fake)

    out_path = tmp_path / "out.json"
    result = runner.invoke(
        stt_cli.app,
        [str(temp_audio_file), "--provider", "deepgram", "--format", "json", "--output", str(out_path)],
    )

    assert result.exit_code == 0, result.output
    assert "Transcript saved to" in result.output
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "hello world" in content
    # JSON format includes chunk timing.
    assert "chunks" in content


def test_transcribe_passes_language_and_diarize(
    monkeypatch: pytest.MonkeyPatch,
    temp_audio_file: Path,
) -> None:
    """Language and diarize flags should reach the provider."""
    runner = CliRunner()
    fake = FakeProvider()
    _install_fake_provider(monkeypatch, fake)

    result = runner.invoke(
        stt_cli.app,
        [str(temp_audio_file), "--provider", "deepgram", "--language", "en", "--diarize"],
    )

    assert result.exit_code == 0, result.output
    assert fake.transcribe_calls[0]["language"] == "en"
    assert fake.transcribe_calls[0]["kwargs"]["diarize"] is True


def test_missing_api_key_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    temp_audio_file: Path,
) -> None:
    """A missing key for a key-requiring provider should exit non-zero with a clear message."""
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("DG_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(stt_cli.app, [str(temp_audio_file), "--provider", "deepgram"])

    assert result.exit_code != 0
    assert "DEEPGRAM_API_KEY" in result.output


def test_unknown_provider_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    temp_audio_file: Path,
) -> None:
    """An unknown provider should exit non-zero and surface the name."""
    runner = CliRunner()
    result = runner.invoke(stt_cli.app, [str(temp_audio_file), "--provider", "nope"])

    assert result.exit_code != 0
    assert "nope" in result.output


def test_bad_output_format_fails_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    temp_audio_file: Path,
) -> None:
    """An unsupported format should exit non-zero before any provider work."""
    runner = CliRunner()
    result = runner.invoke(
        stt_cli.app,
        [str(temp_audio_file), "--provider", "deepgram", "--format", "xyz"],
    )

    assert result.exit_code != 0
    assert "Unknown transcript format" in result.output


def test_missing_audio_argument_fails_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invocation with no audio and no exit-early flag should error."""
    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--provider", "deepgram"])

    assert result.exit_code != 0
    assert "AUDIO" in result.output or "required" in result.output.lower()


def test_dump_config_exits_without_provider_or_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--dump`` should print resolved config without creating a provider."""

    def fail_create_provider(*args: Any, **kwargs: Any) -> FakeProvider:
        raise AssertionError("dump-config should not create a provider")

    monkeypatch.setattr(stt_cli, "create_provider", fail_create_provider)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "fake-key")

    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--dump", "--provider", "deepgram"])

    assert result.exit_code == 0, result.output
    assert "Configuration" in result.output
    assert "deepgram" in result.output
    assert "nova-3" in result.output


def test_create_config_writes_restrictive_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--create-config`` should write a 0o600 config file in the isolated dir."""
    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--create-config"])

    assert result.exit_code == 0, result.output
    manager = ConfigManager()
    assert manager.config_file.exists()
    assert (manager.config_file.stat().st_mode & 0o777) == 0o600
    text = manager.config_file.read_text(encoding="utf-8")
    assert "elevenlabs_api_key" in text
    assert "deepgram_api_key" in text


def test_load_config_tightens_permissions_and_parses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``load_config`` should chmod 0o600 a permissive file and parse fields."""
    manager = ConfigManager()
    manager.config_dir.mkdir(parents=True, exist_ok=True)
    config_path = manager.config_file
    config_path.write_text(
        "provider: elevenlabs\nmodel: scribe_v1\nlanguage: en\noutput_format: srt\n"
        "deepgram_api_key: dg-secret\nelevenlabs_api_key: el-secret\n",
        encoding="utf-8",
    )
    os.chmod(config_path, 0o644)

    loaded = manager.load_config()

    assert loaded is not None
    assert loaded.provider == "elevenlabs"
    assert loaded.model == "scribe_v1"
    assert loaded.output_format == "srt"
    assert loaded.deepgram_api_key == "dg-secret"
    assert (config_path.stat().st_mode & 0o777) == 0o600


def test_config_rejects_unknown_provider(tmp_path: Path) -> None:
    """Config validation should reject an unknown provider."""
    manager = ConfigManager()
    manager.config_dir.mkdir(parents=True, exist_ok=True)
    manager.config_file.write_text("provider: nope\n", encoding="utf-8")

    loaded = manager.load_config()

    assert loaded is None  # invalid config is rejected and warning printed
    assert manager.config_file.exists()


def test_completion_generation_produces_script() -> None:
    """``--completion bash`` should print the typer completion script."""
    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--completion", "bash"])

    assert result.exit_code == 0
    assert result.output == generate_completion_script("bash")
    assert "_PAR_STT_COMPLETE" in result.output


def test_completion_rejects_unknown_shell() -> None:
    """An unsupported shell should exit non-zero and list supported shells."""
    runner = CliRunner()
    result = runner.invoke(stt_cli.app, ["--completion", "powershell"])

    assert result.exit_code != 0
    assert "Unsupported shell" in result.output
    assert "bash" in result.output
