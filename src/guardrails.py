"""Security guardrails for mcp-ai-workforce.

Implements boundary protection against Path Traversal vulnerabilities and blocks
potentially destructive or privileged shell commands.
"""

from os import PathLike
import os
from pathlib import Path
import re
from typing import Optional, Union

from src.config import WORKSPACE_ROOT

# Regex patterns matching destructive or privileged command invocations
# Uses negative lookbehinds to avoid matching benign command-line flags (e.g., --format)
_DESTRUCTIVE_PATTERNS = [
    re.compile(
        r"(?<![-a-zA-Z0-9_])(rm|del|erase|rmdir|rd|format|diskpart|fdisk|mkfs|sudo|su|runas|doas|shutdown|reboot|halt|poweroff|dd|shred|wipe)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![-a-zA-Z0-9_])(remove-item|clear-content|stop-computer|restart-computer|format-volume)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bdrop\s+(database|schema|table)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btruncate\s+table\b",
        re.IGNORECASE,
    ),
    re.compile(
        r":\(\)\s*\{\s*:\|:&\s*\};:",  # Fork bomb
        re.IGNORECASE,
    ),
]


def validate_safe_path(
    requested_path: Union[str, PathLike[str], Path],
    workspace_root: Optional[Union[str, PathLike[str], Path]] = None,
) -> Path:
    """Validate that a requested path strictly resides within the authorized workspace root.

    Prevents Path Traversal attacks (e.g. using `..`, symbolic link bypass, or drive hopping).

    Args:
        requested_path: Path or string to validate (relative or absolute).
        workspace_root: Canonical base directory. Defaults to configured WORKSPACE_ROOT.

    Returns:
        Path: Resolved canonical Path object within the workspace root.

    Raises:
        PermissionError: If the target path resolves outside of the authorized workspace root.
    """
    root_raw = workspace_root if workspace_root is not None else WORKSPACE_ROOT
    root_path = Path(root_raw).resolve()

    target_raw = Path(requested_path)

    # Detect Windows drive paths on POSIX systems (e.g. Linux CI runner)
    if os.name != "nt" and re.match(r"^[a-zA-Z]:", str(requested_path)):
        raise PermissionError(
            f"Access denied: Requested path '{requested_path}' contains Windows drive root, outside authorized workspace root."
        )

    if not target_raw.is_absolute():
        target_path = (root_path / target_raw).resolve()
    else:
        target_path = target_raw.resolve()

    # Normalization for cross-platform and case-insensitive file systems (such as Windows)
    norm_root = os.path.normcase(os.path.abspath(str(root_path)))
    norm_target = os.path.normcase(os.path.abspath(str(target_path)))

    # Target must either be the root directory itself or a descendant inside it
    if norm_target != norm_root and not norm_target.startswith(norm_root.rstrip(os.sep) + os.sep):
        raise PermissionError(
            f"Access denied: Requested path '{requested_path}' resolves to '{target_path}', "
            f"which is outside authorized workspace root '{root_path}'."
        )

    # Security Guardrail: Deny access to sensitive directories, credentials and git internals
    try:
        rel_parts = [p.lower() for p in target_path.relative_to(root_path).parts]
        for part in rel_parts:
            if part == ".git" or (part.startswith(".env") and part != ".env.example"):
                raise PermissionError(
                    f"Security guardrail: Access to sensitive path component '{part}' is strictly forbidden."
                )

        # Deny access to the mcp-ai-workforce internal directory itself to prevent credential theft/tampering
        if len(rel_parts) >= 2 and rel_parts[0] == ".agents" and rel_parts[1] == "mcp-ai-workforce":
            raise PermissionError(
                "Security guardrail: Access to the workforce server internal directory is forbidden."
            )

        # Deny access to cryptographic private keys
        if target_path.suffix.lower() in {".pem", ".key"} or target_path.name.lower().startswith("id_"):
            raise PermissionError(
                f"Security guardrail: Access to sensitive key file '{target_path.name}' is strictly forbidden."
            )
    except ValueError:
        pass

    return target_path


def validate_safe_command(command: str) -> None:
    """Verify that a shell command does not contain destructive or unauthorized operations.

    Blocks operations such as deletions, disk formatting, privilege escalation, and system resets.

    Args:
        command: The command-line string to inspect.

    Raises:
        PermissionError: If the command matches any destructive pattern.
    """
    cleaned_command = command.strip()
    if not cleaned_command:
        return

    for pattern in _DESTRUCTIVE_PATTERNS:
        match = pattern.search(cleaned_command)
        if match:
            raise PermissionError(
                f"Command blocked by security guardrails: Destructive token '{match.group(0)}' detected "
                f"in command: '{command}'"
            )
