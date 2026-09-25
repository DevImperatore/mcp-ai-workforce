"""Filesystem worker tools for mcp-ai-workforce.

Provides secure filesystem access primitives for worker agents, guaranteeing all
operations are constrained to the workspace root via security guardrails.
"""

from pathlib import Path
from typing import Any, Dict, List

from src.config import WORKSPACE_ROOT
from src.guardrails import validate_safe_path


def worker_read_file(relative_path: str) -> str:
    """Read the contents of a file within the workspace.

    Args:
        relative_path: Relative path to the file from the workspace root.

    Returns:
        str: UTF-8 decoded content of the file.

    Raises:
        PermissionError: If path resolves outside authorized workspace root.
        FileNotFoundError: If the target file does not exist.
        IsADirectoryError: If the target path points to a directory.
    """
    safe_path = validate_safe_path(relative_path, WORKSPACE_ROOT)

    if not safe_path.exists():
        raise FileNotFoundError(f"File not found: '{relative_path}' (resolved: '{safe_path}')")

    if not safe_path.is_file():
        raise IsADirectoryError(f"Path is not a regular file: '{relative_path}'")

    return safe_path.read_text(encoding="utf-8", errors="replace")


def worker_write_file(relative_path: str, content: str) -> str:
    """Write content to a file within the workspace, creating parent directories if needed.

    Args:
        relative_path: Relative path to the target file from the workspace root.
        content: String content to write into the file.

    Returns:
        str: Success confirmation message with written character count.

    Raises:
        PermissionError: If path resolves outside authorized workspace root.
        IsADirectoryError: If the target path exists and is a directory.
    """
    safe_path = validate_safe_path(relative_path, WORKSPACE_ROOT)

    if safe_path.exists() and safe_path.is_dir():
        raise IsADirectoryError(f"Cannot overwrite directory with file content: '{relative_path}'")

    # Ensure parent directories exist before writing
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    safe_path.write_text(content, encoding="utf-8")
    return f"Successfully wrote {len(content)} characters to '{relative_path}'."


def worker_list_dir(relative_path: str = ".") -> List[Dict[str, Any]]:
    """List the contents of a directory within the workspace.

    Args:
        relative_path: Relative path to the directory from workspace root. Defaults to root ('.').

    Returns:
        List[Dict[str, Any]]: Structured metadata for entries containing 'name', 'type',
        'size_bytes', and 'relative_path'.

    Raises:
        PermissionError: If path resolves outside authorized workspace root.
        FileNotFoundError: If directory does not exist.
        NotADirectoryError: If target path is a file, not a directory.
    """
    safe_path = validate_safe_path(relative_path, WORKSPACE_ROOT)

    if not safe_path.exists():
        raise FileNotFoundError(f"Directory not found: '{relative_path}' (resolved: '{safe_path}')")

    if not safe_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: '{relative_path}'")

    entries: List[Dict[str, Any]] = []

    # Sort directories first, then alphabetical by name
    sorted_items = sorted(
        safe_path.iterdir(),
        key=lambda item: (not item.is_dir(), item.name.lower()),
    )

    for item in sorted_items:
        try:
            is_dir = item.is_dir()
            size = item.stat().st_size if not is_dir else 0
            rel_to_root = item.relative_to(WORKSPACE_ROOT).as_posix()
            entries.append(
                {
                    "name": item.name,
                    "type": "directory" if is_dir else "file",
                    "size_bytes": size,
                    "relative_path": rel_to_root,
                }
            )
        except (PermissionError, FileNotFoundError):
            # Gracefully skip items with locked permissions or broken symlinks
            continue

    return entries
