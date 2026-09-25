"""Unit tests for filesystem worker tools."""

from pathlib import Path
import pytest

from src.worker.fs_tools import (
    worker_list_dir,
    worker_read_file,
    worker_write_file,
)


def test_worker_write_and_read_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test creating, writing, and reading files within workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Patch WORKSPACE_ROOT in config and modules to point to temporary workspace
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    # Write a new file with parent directories
    rel_path = "nested/dir/test_file.txt"
    content = "Hello from MCP AI Workforce!"
    write_msg = worker_write_file(rel_path, content)

    assert "Successfully wrote" in write_msg
    assert (workspace / "nested" / "dir" / "test_file.txt").exists()

    # Read the file back
    read_content = worker_read_file(rel_path)
    assert read_content == content


def test_worker_read_nonexistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test reading a non-existent file raises FileNotFoundError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    with pytest.raises(FileNotFoundError):
        worker_read_file("nonexistent.txt")


def test_worker_write_traversal_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test writing outside workspace is blocked by PermissionError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    with pytest.raises(PermissionError):
        worker_write_file("../forbidden.txt", "exploit")


def test_worker_list_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test listing directory contents."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    # Create dummy structure
    (workspace / "dir_a").mkdir()
    (workspace / "dir_b").mkdir()
    (workspace / "file1.txt").write_text("abc", encoding="utf-8")
    (workspace / "file2.py").write_text("print(1)", encoding="utf-8")

    entries = worker_list_dir(".")
    names = [e["name"] for e in entries]

    assert "dir_a" in names
    assert "dir_b" in names
    assert "file1.txt" in names
    assert "file2.py" in names

    # Check directory entry attributes
    dir_entry = next(e for e in entries if e["name"] == "dir_a")
    assert dir_entry["type"] == "directory"

    # Check file entry attributes
    file_entry = next(e for e in entries if e["name"] == "file1.txt")
    assert file_entry["type"] == "file"
    assert file_entry["size_bytes"] == 3
