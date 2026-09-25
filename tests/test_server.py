"""Unit tests for the FastMCP server tools in mcp-ai-workforce.

Tests the invocation of:
1. workforce_models_status: configuration status, recommended models, API key check.
2. workforce_audit_diff: unstaged and staged git diff execution, clean workspace detection, and error handling.
3. workforce_delegate: agent task dispatch and graceful exception handling.
"""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch
import pytest

from src.server import (
    mcp,
    workforce_audit_diff,
    workforce_delegate,
    workforce_models_status,
)


class TestServerTools:
    """Suite testing FastMCP server tools invocation and responses."""

    def test_workforce_models_status_ready_state(self, monkeypatch: pytest.MonkeyPatch):
        """Test workforce_models_status when OPENROUTER_API_KEY is configured."""
        monkeypatch.setattr("src.server.OPENROUTER_API_KEY", "sk-or-v1-valid-fake-key")

        status = workforce_models_status()

        assert isinstance(status, dict)
        assert status["status"] == "ready"
        assert status["openrouter_api_key_configured"] is True
        assert "default_model" in status
        assert "workspace_root" in status
        assert "max_steps" in status
        assert "timeout_seconds" in status
        assert isinstance(status["recommended_models"], list)
        assert "qwen/qwen-2.5-coder-32b-instruct" in status["recommended_models"]
        assert "deepseek/deepseek-chat" in status["recommended_models"]

    def test_workforce_models_status_needs_configuration(self, monkeypatch: pytest.MonkeyPatch):
        """Test workforce_models_status when OPENROUTER_API_KEY is missing or empty."""
        monkeypatch.setattr("src.server.OPENROUTER_API_KEY", "")

        status = workforce_models_status()

        assert isinstance(status, dict)
        assert status["status"] == "needs_configuration"
        assert status["openrouter_api_key_configured"] is False

    def test_workforce_audit_diff_clean_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test workforce_audit_diff reporting clean working directory when no diff exists."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.server.WORKSPACE_ROOT", workspace)

        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = subprocess.CompletedProcess(
                args=["git", "diff"],
                returncode=0,
                stdout="",
                stderr="",
            )

            # Test unstaged
            res_unstaged = workforce_audit_diff(staged=False)
            assert "Clean workspace: No unstaged git changes detected" in res_unstaged
            assert "diff" in mock_subproc.call_args[0][0]
            assert "--staged" not in mock_subproc.call_args[0][0]

            # Test staged
            mock_subproc.return_value.stdout = ""
            res_staged = workforce_audit_diff(staged=True)
            assert "Clean workspace: No staged git changes detected" in res_staged
            assert "--staged" in mock_subproc.call_args[0][0]

    def test_workforce_audit_diff_with_modifications(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test workforce_audit_diff returning the unified patch output when changes exist."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.server.WORKSPACE_ROOT", workspace)

        fake_diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1 +1,2 @@\n"
            "+def new_feature():\n"
            "+    return True\n"
        )

        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = subprocess.CompletedProcess(
                args=["git", "diff"],
                returncode=0,
                stdout=fake_diff,
                stderr="",
            )

            diff_result = workforce_audit_diff(staged=False)
            assert "diff --git a/src/app.py b/src/app.py" in diff_result
            assert "+def new_feature():" in diff_result

    def test_workforce_audit_diff_git_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test workforce_audit_diff reporting non-zero exit codes from git."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.server.WORKSPACE_ROOT", workspace)

        with patch("subprocess.run") as mock_subproc:
            mock_subproc.return_value = subprocess.CompletedProcess(
                args=["git", "diff"],
                returncode=128,
                stdout="",
                stderr="fatal: not a git repository (or any of the parent directories): .git",
            )

            result = workforce_audit_diff(staged=False)
            assert "Git diff exited with code 128:" in result
            assert "fatal: not a git repository" in result

    def test_workforce_audit_diff_missing_git_binary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test workforce_audit_diff handling FileNotFoundError if git is not on PATH."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.server.WORKSPACE_ROOT", workspace)

        with patch("subprocess.run", side_effect=FileNotFoundError("git executable missing")):
            result = workforce_audit_diff(staged=False)
            assert "Error: 'git' executable not found on system PATH." in result

    async def test_workforce_delegate_success(self):
        """Test workforce_delegate dispatches to run_worker_agent and returns result."""
        with patch("src.server.run_worker_agent", return_value="Refactor completed.") as mock_run:
            res = await workforce_delegate(
                task_prompt="Optimize sorting function",
                target_files=["utils/sort.py"],
                model="deepseek/deepseek-chat",
                timeout_seconds=120,
            )

            assert res == "Refactor completed."
            mock_run.assert_called_once_with(
                task_prompt="Optimize sorting function",
                target_files=["utils/sort.py"],
                model="deepseek/deepseek-chat",
                timeout_seconds=120,
            )

    async def test_workforce_delegate_handles_exception(self):
        """Test workforce_delegate captures unexpected exceptions into formatted message."""
        with patch("src.server.run_worker_agent", side_effect=ConnectionError("OpenRouter unreachable")):
            res = await workforce_delegate("Sample task")
            assert "Workforce delegation failed with error: OpenRouter unreachable" in res
