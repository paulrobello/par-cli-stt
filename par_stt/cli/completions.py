"""Shell completion helpers for the par-stt CLI."""

from __future__ import annotations

import typer.completion

from par_stt.errors import ErrorType, SttError

SUPPORTED_SHELLS = ("bash", "zsh", "fish")


def normalize_shell(shell: str) -> str:
    """Normalize and validate a requested shell name.

    Raises:
        SttError: If *shell* is not one of the supported shells.
    """
    normalized = shell.strip().lower()
    if normalized not in SUPPORTED_SHELLS:
        supported = ", ".join(SUPPORTED_SHELLS)
        raise SttError(
            f"Unsupported shell '{shell}'. Supported shells: {supported}",
            ErrorType.INVALID_INPUT,
        )
    return normalized


def _completion_env_var(program_name: str) -> str:
    normalized_program = program_name.replace("-", "_").upper()
    return f"_{normalized_program}_COMPLETE"


def generate_completion_script(shell: str, program_name: str = "par-stt") -> str:
    """Return a shell completion script for bash, zsh, or fish."""
    normalized_shell = normalize_shell(shell)
    completion_script = getattr(typer.completion, "get_completion_script")
    return completion_script(
        prog_name=program_name,
        complete_var=_completion_env_var(program_name),
        shell=normalized_shell,
    )


def completion_install_instructions(shell: str) -> str:
    """Return concrete installation instructions for a supported shell."""
    normalized_shell = normalize_shell(shell)
    if normalized_shell == "bash":
        return "\n".join(
            [
                "Bash completion for par-stt:",
                "  mkdir -p ~/.local/share/bash-completion/completions",
                "  par-stt --completion bash > ~/.local/share/bash-completion/completions/par-stt",
                "  # Restart your shell or source the generated file.",
            ]
        )
    if normalized_shell == "zsh":
        return "\n".join(
            [
                "Zsh completion for par-stt:",
                "  mkdir -p ~/.zfunc",
                "  par-stt --completion zsh > ~/.zfunc/_par-stt",
                "  # Add this to ~/.zshrc if needed: fpath=(~/.zfunc $fpath); autoload -Uz compinit; compinit",
            ]
        )
    return "\n".join(
        [
            "Fish completion for par-stt:",
            "  mkdir -p ~/.config/fish/completions",
            "  par-stt --completion fish > ~/.config/fish/completions/par-stt.fish",
            "  # Fish will load the completion automatically for new shells.",
        ]
    )
