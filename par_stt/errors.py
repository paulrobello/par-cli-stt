"""Error handling utilities for PAR CLI STT."""

import logging
import sys
from contextvars import ContextVar
from enum import Enum
from typing import NoReturn

_logger = logging.getLogger(__name__)

# Thread-safe, library-safe debug flag.  The CLI sets this at startup;
# library callers can also toggle it via ``set_debug_mode()``.
_debug_mode: ContextVar[bool] = ContextVar("_debug_mode", default=False)


def set_debug_mode(enabled: bool) -> None:
    """Set the global debug mode flag (thread-safe via ContextVar)."""
    _debug_mode.set(enabled)


class ErrorType(Enum):
    """Types of errors for consistent handling."""

    INVALID_INPUT = (1, "Invalid Input")
    FILE_NOT_FOUND = (1, "File Not Found")
    INVALID_AUDIO = (1, "Invalid Audio")
    MISSING_API_KEY = (1, "Missing API Key")
    INVALID_PROVIDER = (1, "Invalid Provider")

    NETWORK_ERROR = (2, "Network Error")
    API_ERROR = (2, "API Error")
    PROVIDER_ERROR = (2, "Provider Error")

    PERMISSION_ERROR = (3, "Permission Denied")
    DISK_FULL = (3, "Disk Full")
    WRITE_ERROR = (3, "Write Error")

    CONFIG_ERROR = (4, "Configuration Error")
    CACHE_ERROR = (4, "Cache Error")

    def __init__(self, exit_code: int, display_name: str):
        self.exit_code = exit_code
        self.display_name = display_name


class SttError(Exception):
    """Base exception for PAR CLI STT errors."""

    def __init__(self, message: str, error_type: ErrorType = ErrorType.PROVIDER_ERROR):
        self.message = message
        self.error_type = error_type
        super().__init__(self.message)


def handle_error(
    message: str,
    error_type: ErrorType = ErrorType.PROVIDER_ERROR,
    exception: Exception | None = None,
    exit_on_error: bool = False,
) -> NoReturn:
    """Log an error and raise SttError (or sys.exit in legacy mode).

    In library mode (default), raises SttError so callers can catch and handle
    errors programmatically.  When *exit_on_error* is True the process calls
    ``sys.exit()`` instead -- this is retained for the CLI layer's use.

    Args:
        message: Human-readable error description.
        error_type: Categorised error type carrying an exit-code.
        exception: Optional original exception for debug logging.
        exit_on_error: If True, call ``sys.exit()`` instead of raising.

    Raises:
        SttError: Always, unless *exit_on_error* is True.
    """
    _logger.error("%s: %s", error_type.display_name, message)

    if exception and _debug_mode.get():
        _logger.debug("Debug: %s: %s", type(exception).__name__, exception)

    if exit_on_error:
        sys.exit(error_type.exit_code)

    raise SttError(message, error_type)


def validate_api_key(api_key: str | None, provider: str) -> None:
    """Validate that an API key is provided for cloud providers.

    A missing or empty key raises SttError with ErrorType.MISSING_API_KEY.

    Args:
        api_key: The API key string, or None if not provided.
        provider: Provider identifier (e.g. ``"deepgram"``, ``"elevenlabs"``).

    Raises:
        SttError: If *api_key* is falsy.
    """
    if not api_key:
        handle_error(
            f"API key required for {provider}. Set environment variable or check .env file.",
            ErrorType.MISSING_API_KEY,
        )


def validate_file_path(file_path: str, must_exist: bool = True) -> None:
    """Validate a file path for security and existence.

    Resolves the path to an absolute form and optionally checks that it
    exists on disk.  Invalid or missing paths raise SttError.

    Args:
        file_path: The file path string to validate.
        must_exist: If True (default), raise an error when the file does
            not exist on disk.

    Raises:
        SttError: If the path is invalid or the file is not found.
    """
    from pathlib import Path

    path = Path(file_path)

    try:
        path = path.resolve()
    except Exception as e:
        handle_error(f"Invalid file path: {file_path}", ErrorType.INVALID_INPUT, exception=e)

    if must_exist and not path.exists():
        handle_error(f"File not found: {file_path}", ErrorType.FILE_NOT_FOUND)
