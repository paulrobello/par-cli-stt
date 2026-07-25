"""Configuration file support for PAR CLI STT.

The config file lives at ``~/Library/Application Support/par-stt/config.yaml``
on macOS (``~/.config/par-stt/config.yaml`` on Linux) and is the recommended
store for API keys.  It is created with mode ``0o600`` (owner-only read/write)
and re-tightened on every load if the permissions drift.
"""

import os
from pathlib import Path
from typing import Any

import platformdirs
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from rich.prompt import Confirm

from par_stt.cli.console import console
from par_stt.logging_config import normalize_log_level
from par_stt.transcript_writer import TranscriptFormat

VALID_PROVIDERS = {"deepgram", "elevenlabs"}
VALID_OUTPUT_FORMATS = {member.value for member in TranscriptFormat}


class ConfigProfile(BaseModel):
    """Named profile schema for overriding base configuration settings."""

    provider: str | None = Field(None, description="Default STT provider (deepgram, elevenlabs)")
    model: str | None = Field(None, description="Default model")
    language: str | None = Field(None, description="Default language hint (e.g. 'en')")
    output_format: str | None = Field(None, description="Default output format: txt, srt, vtt, json")
    output_dir: str | None = Field(None, description="Default output directory for transcripts")

    # API keys (optional — can also be set via environment variables).
    elevenlabs_api_key: str | None = Field(None, description="ElevenLabs API key")
    deepgram_api_key: str | None = Field(None, description="Deepgram API key")

    # Transcription options shared across providers.
    diarize: bool | None = Field(None, description="Label distinct speakers")

    # Reliability / observability settings.
    debug: bool | None = Field(None, description="Enable debug output")
    structured_logs: bool | None = Field(None, description="Emit JSON logs for automation and telemetry ingestion")
    log_level: str | None = Field(None, description="Python logging level")
    retry_attempts: int | None = Field(None, ge=0, le=10, description="Retries after the initial provider attempt")
    retry_backoff: float | None = Field(None, ge=0.0, le=60.0, description="Initial retry backoff in seconds")

    model_config = ConfigDict(extra="forbid")

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in VALID_PROVIDERS:
            raise ValueError(f"Unknown provider '{v}'. Valid: {sorted(VALID_PROVIDERS)}")
        return v

    @field_validator("output_format")
    @classmethod
    def _validate_output_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalized = v.strip().lower().lstrip(".")
        if normalized == "txt":  # accepted alias for "text"
            return "txt"
        if normalized not in VALID_OUTPUT_FORMATS:
            raise ValueError(f"Unknown output format '{v}'. Valid: txt, {sorted(VALID_OUTPUT_FORMATS)}")
        return normalized

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return normalize_log_level(v)


class ConfigFile(ConfigProfile):
    """Configuration file schema."""

    profiles: dict[str, ConfigProfile] | None = Field(None, description="Named config profiles")


class ConfigManager:
    """Manages configuration file loading, merging, and creation."""

    def __init__(self, app_name: str = "par-stt") -> None:
        """Initialize configuration manager.

        Args:
            app_name: Application name for directory creation.
        """
        self.app_name = app_name
        self.config_dir = Path(platformdirs.user_config_dir(app_name))
        self.config_file = self.config_dir / "config.yaml"
        self.config_data: ConfigFile | None = None

    def load_config(self) -> ConfigFile | None:
        """Load configuration from file.

        Returns:
            ConfigFile object if a valid config exists, None otherwise.
        """
        if not self.config_file.exists():
            return None

        # Ensure restrictive permissions on existing config (may contain API keys).
        try:
            current_mode = self.config_file.stat().st_mode & 0o777
            if current_mode != 0o600:
                os.chmod(self.config_file, 0o600)
        except OSError:
            pass

        try:
            with open(self.config_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            self.config_data = ConfigFile(**data)
            console.print(f"[dim]Loaded config from {self.config_file}[/dim]")
            return self.config_data

        except ValidationError as e:
            console.print(f"[yellow]Warning: Invalid config file: {e}[/yellow]")
            return None
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load config: {e}[/yellow]")
            return None

    def apply_profile(self, config: ConfigFile, profile_name: str) -> ConfigFile:
        """Apply a named profile over a loaded base configuration.

        Args:
            config: Loaded base configuration.
            profile_name: Name of the profile to apply.

        Returns:
            A new ConfigFile with profile values overriding base values.

        Raises:
            ValueError: If the requested profile does not exist.
        """
        if not config.profiles or profile_name not in config.profiles:
            available = ", ".join(sorted(config.profiles or {})) or "none"
            raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

        base_data = config.model_dump(exclude_none=True)
        profiles = base_data.pop("profiles", None)
        profile_data = config.profiles[profile_name].model_dump(exclude_none=True)
        merged = {**base_data, **profile_data}
        if profiles is not None:
            merged["profiles"] = profiles
        return ConfigFile(**merged)

    def create_sample_config(self, force: bool = False) -> bool:
        """Create a sample configuration file.

        Args:
            force: If True, overwrite an existing config without prompting.

        Returns:
            True if the file was written, False if the user declined to overwrite.
        """
        sample_lines = [
            "# PAR CLI STT Configuration File",
            "# Uncomment and modify settings as needed",
            "",
            "# Default provider (deepgram, elevenlabs)",
            "# provider: deepgram",
            "",
            "# Default model",
            "# Deepgram Nova-3 (streaming): nova-3",
            "# ElevenLabs Scribe (batch): scribe_v1",
            "# model: nova-3",
            "",
            "# Default language hint (e.g. 'en', 'en-US'). Omit to let the provider auto-detect.",
            "# language: en",
            "",
            "# Default output format: txt, srt, vtt, json",
            "# output_format: txt",
            "",
            "# Default output directory for transcripts (omitted = current directory)",
            "# output_dir: ~/Documents/transcripts",
            "",
            "# Named profiles override the base settings above when selected with --profile NAME.",
            "# profiles:",
            "#   meetings:",
            "#     provider: deepgram",
            "#     language: en",
            "#     diarize: true",
            "#   interviews:",
            "#     provider: elevenlabs",
            "#     model: scribe_v1",
            "#     diarize: true",
            "",
            "# API keys (optional — can also be set via environment variables)",
            "# elevenlabs_api_key: your-elevenlabs-api-key-here",
            "# deepgram_api_key: your-deepgram-api-key-here",
            "",
            "# Shared transcription options",
            "# diarize: false  # Label distinct speakers",
            "",
            "# Behavior settings",
            "# debug: false",
            "",
            "# Reliability / observability",
            "# structured_logs: false  # Emit JSON logs for automation/telemetry ingestion",
            "# log_level: WARNING      # DEBUG, INFO, WARNING, ERROR, or CRITICAL",
            "# retry_attempts: 0       # Retries after the initial provider attempt",
            "# retry_backoff: 0.25     # Initial exponential backoff in seconds",
        ]

        # Confirm before clobbering an existing config.
        if self.config_file.exists() and not force:
            console.print(f"[yellow]Config already exists at {self.config_file}[/yellow]")
            if not Confirm.ask("Overwrite?", default=False):
                console.print("[dim]Aborted — existing config preserved.[/dim]")
                return False

        # Create config directory if it doesn't exist.
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Write sample config with restrictive permissions (owner-only read/write).
        fd = os.open(str(self.config_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for line in sample_lines:
                    f.write(f"{line}\n")
        except Exception:
            os.close(fd)
            raise

        console.print(f"[green]✓ Created sample config at {self.config_file}[/green]")
        console.print("[dim]Edit this file to set your default preferences[/dim]")
        return True

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Configuration key.
            default: Default value if not found.

        Returns:
            Configuration value or default.
        """
        if self.config_data:
            return getattr(self.config_data, key, default)
        return default
