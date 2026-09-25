"""Unit tests for the ReAct agent loop, tool dispatch, and infinite loop detection."""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.worker.agent_loop import _execute_tool, run_worker_agent


def test_execute_tool_read_and_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _execute_tool dispatch for read_file, write_file, and list_dir."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    # write_file
    res_write = _execute_tool("write_file", {"path": "hello.txt", "content": "world"})
    assert "Successfully wrote" in res_write

    # read_file
    res_read = _execute_tool("read_file", {"path": "hello.txt"})
    assert res_read == "world"

    # list_dir
    res_list = _execute_tool("list_dir", {"path": "."})
    entries = json.loads(res_list)
    assert any(e["name"] == "hello.txt" for e in entries)


def test_execute_tool_guardrail_protection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test _execute_tool traps security violations and returns formatted error string."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    res = _execute_tool("read_file", {"path": "../secret.env"})
    assert "Security Guardrail Error" in res


def test_infinite_loop_detector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that agent aborts if the model repeatedly calls the same tool with identical args."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    # Create dummy file
    (workspace / "stuck.txt").write_text("content", encoding="utf-8")

    # Mock OpenAI client that returns the exact same tool call every time
    mock_client = MagicMock()

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function.name = "read_file"
    mock_tool_call.function.arguments = json.dumps({"path": "stuck.txt"})

    mock_msg = MagicMock()
    mock_msg.content = None
    mock_msg.tool_calls = [mock_tool_call]

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    output = run_worker_agent(
        task_prompt="Read stuck.txt",
        openai_client=mock_client,
        max_steps=10,
    )

    assert "Infinite loop detected" in output
    assert "read_file" in output


def test_agent_max_steps_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test that agent halts when reaching max_steps without concluding."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("src.worker.fs_tools.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("src.guardrails.WORKSPACE_ROOT", workspace)

    mock_client = MagicMock()

    # Model calls different files so loop detector is not triggered
    counter = {"i": 0}

    def mock_create(*args, **kwargs):
        counter["i"] += 1
        path = f"file_{counter['i']}.txt"
        (workspace / path).write_text("data", encoding="utf-8")

        tc = MagicMock()
        tc.id = f"call_{counter['i']}"
        tc.function.name = "read_file"
        tc.function.arguments = json.dumps({"path": path})

        msg = MagicMock()
        msg.content = f"Reading step {counter['i']}"
        msg.tool_calls = [tc]

        choice = MagicMock()
        choice.message = msg

        resp = MagicMock()
        resp.choices = [choice]
        return resp

    mock_client.chat.completions.create.side_effect = mock_create

    output = run_worker_agent(
        task_prompt="Keep reading files",
        openai_client=mock_client,
        max_steps=4,
    )

    assert "Reached maximum step limit" in output


def test_agent_normal_completion():
    """Test that agent returns direct textual output when no tool calls are made."""
    mock_client = MagicMock()

    mock_msg = MagicMock()
    mock_msg.content = "Analysis completed successfully. All components are operational."
    mock_msg.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_msg

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client.chat.completions.create.return_value = mock_response

    output = run_worker_agent(
        task_prompt="Check status",
        openai_client=mock_client,
    )

    assert output == "Analysis completed successfully. All components are operational."
