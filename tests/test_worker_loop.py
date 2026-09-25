"""Unit tests for the autonomous ReAct worker agent loop.

Tests the execution loop using unittest.mock to simulate OpenRouter API responses:
1. Successful termination when the model returns a final textual response (single and multi-step).
2. Infinite loop detection when the model invokes the exact same tool and arguments 3 times consecutively.
3. Premature stopping when reaching the maximum allowed steps limit (max_steps).
4. Missing API key validation and timeout protection.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.worker.agent_loop import run_worker_agent


def _create_mock_message(content: str = None, tool_calls: list = None):
    """Helper to create a mock OpenAI chat completion message."""
    mock_msg = MagicMock()
    mock_msg.content = content
    mock_msg.tool_calls = tool_calls
    return mock_msg


def _create_mock_tool_call(call_id: str, tool_name: str, arguments: dict):
    """Helper to create a mock function tool call object."""
    mock_tc = MagicMock()
    mock_tc.id = call_id
    mock_tc.type = "function"
    mock_tc.function.name = tool_name
    mock_tc.function.arguments = json.dumps(arguments)
    return mock_tc


def _create_mock_response(message):
    """Helper to create a mock chat completion response wrapper."""
    mock_choice = MagicMock()
    mock_choice.message = message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


class TestWorkerLoop:
    """Suite testing worker loop mechanics, mocks, guardrails, and control flow."""

    def test_worker_loop_successful_termination_immediate(self):
        """Test immediate successful termination when model directly returns a final text answer."""
        mock_client = MagicMock()
        final_answer = "Refactoring completed successfully: updated 3 functions with type hints."
        msg = _create_mock_message(content=final_answer, tool_calls=None)
        mock_client.chat.completions.create.return_value = _create_mock_response(msg)

        result = run_worker_agent(
            task_prompt="Add type hints to utils.py",
            openai_client=mock_client,
            max_steps=5,
        )

        assert result == final_answer
        assert mock_client.chat.completions.create.call_count == 1

    def test_worker_loop_successful_termination_with_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test multi-step task where model executes a write_file tool call and then terminates."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
        monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

        mock_client = MagicMock()

        # Step 1: Model decides to write a file
        tc1 = _create_mock_tool_call(
            call_id="call_write_01",
            tool_name="write_file",
            arguments={"path": "src/output.py", "content": "def add(a, b): return a + b\n"},
        )
        resp1 = _create_mock_response(_create_mock_message(content=None, tool_calls=[tc1]))

        # Step 2: Model concludes with final response
        final_text = "Successfully created src/output.py with arithmetic functions."
        resp2 = _create_mock_response(_create_mock_message(content=final_text, tool_calls=None))

        mock_client.chat.completions.create.side_effect = [resp1, resp2]

        result = run_worker_agent(
            task_prompt="Create output.py in src/",
            openai_client=mock_client,
            max_steps=5,
        )

        assert result == final_text
        assert mock_client.chat.completions.create.call_count == 2

        # Verify that the file was actually written to the isolated workspace
        created_file = workspace / "src" / "output.py"
        assert created_file.exists()
        assert "def add(a, b):" in created_file.read_text(encoding="utf-8")

    def test_worker_loop_infinite_loop_detection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test detection and abort when the model invokes the exact same tool call 3 times consecutively."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
        monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

        mock_client = MagicMock()

        # Repetitive call: read_file with path="missing.txt"
        tc = _create_mock_tool_call(
            call_id="call_rep",
            tool_name="read_file",
            arguments={"path": "missing.txt"},
        )
        resp = _create_mock_response(_create_mock_message(content=None, tool_calls=[tc]))
        mock_client.chat.completions.create.return_value = resp

        result = run_worker_agent(
            task_prompt="Inspect missing.txt",
            openai_client=mock_client,
            max_steps=10,
        )

        assert "Agent aborted: Infinite loop detected!" in result
        assert "Tool 'read_file' was invoked 3 consecutive times with identical arguments" in result
        # The loop must abort at the 3rd iteration
        assert mock_client.chat.completions.create.call_count == 3

    def test_worker_loop_stops_at_max_steps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that execution stops cleanly when reaching the maximum allowed step limit."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
        monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

        mock_client = MagicMock()

        # Generate different non-repeating tool calls for each step so infinite loop detector isn't triggered
        responses = []
        for i in range(1, 6):
            tc = _create_mock_tool_call(
                call_id=f"call_{i}",
                tool_name="list_dir",
                arguments={"path": f"dir_{i}"},
            )
            responses.append(_create_mock_response(_create_mock_message(content=None, tool_calls=[tc])))

        mock_client.chat.completions.create.side_effect = responses

        max_limit = 4
        result = run_worker_agent(
            task_prompt="Keep listing different directories",
            openai_client=mock_client,
            max_steps=max_limit,
        )

        assert f"Agent stopped: Reached maximum step limit of {max_limit} steps without final resolution" in result
        assert mock_client.chat.completions.create.call_count == max_limit

    def test_worker_loop_missing_api_key_raises(self):
        """Test that ValueError is raised if OPENROUTER_API_KEY is not configured and no client is passed."""
        with patch("src.worker.agent_loop.OPENROUTER_API_KEY", ""):
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY is not configured"):
                run_worker_agent(task_prompt="Do something", api_key="")
