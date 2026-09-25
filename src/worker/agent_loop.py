"""ReAct worker execution loop for mcp-ai-workforce.

Implements an autonomous reasoning-action agent loop interacting with OpenRouter
and executing filesystem tools with guardrails, infinite loop detection, step limits,
and execution timeouts.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import openai

from src.config import DEFAULT_MODEL, MAX_STEPS, OPENROUTER_API_KEY, TIMEOUT_SECONDS
from src.worker.fs_tools import worker_list_dir, worker_read_file, worker_write_file

logger = logging.getLogger("mcp_ai_workforce.worker")

# OpenAI-compatible function calling schemas
AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads the entire text content of a file within the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file from workspace root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Writes or overwrites text content to a file within the workspace. Creates parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the target file from workspace root.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full text content to write into the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lists contents and metadata of a directory within the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from workspace root. Defaults to '.' (root).",
                    }
                },
                "required": [],
            },
        },
    },
]


def _execute_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Execute a single filesystem tool by name safely.

    Args:
        tool_name: The name of the tool called by the model.
        args: Dictionary of parsed arguments.

    Returns:
        str: Output result or formatted error string.
    """
    try:
        if tool_name == "read_file":
            path = args.get("path")
            if not path:
                return "Error: 'path' argument is required for read_file."
            return worker_read_file(path)

        elif tool_name == "write_file":
            path = args.get("path")
            content = args.get("content", "")
            if not path:
                return "Error: 'path' argument is required for write_file."
            return worker_write_file(path, content)

        elif tool_name == "list_dir":
            path = args.get("path", ".")
            entries = worker_list_dir(path)
            return json.dumps(entries, indent=2)

        else:
            return f"Error: Unknown tool '{tool_name}'."

    except PermissionError as pe:
        return f"Security Guardrail Error: {pe}"
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError) as fe:
        return f"Filesystem Error: {fe}"
    except Exception as exc:
        return f"Unexpected Tool Execution Error: {exc}"


def run_worker_agent(
    task_prompt: str,
    target_files: Optional[List[str]] = None,
    model: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    max_steps: Optional[int] = None,
    api_key: Optional[str] = None,
    openai_client: Optional[openai.OpenAI] = None,
) -> str:
    """Run an autonomous ReAct worker agent using OpenRouter to complete a task.

    Args:
        task_prompt: The detailed task instructions or objective for the worker.
        target_files: Optional list of relative file paths relevant to the task.
        model: Model name/identifier (defaults to configured DEFAULT_MODEL).
        timeout_seconds: Maximum wall-clock time in seconds before terminating.
        max_steps: Maximum reasoning and tool-calling iterations.
        api_key: OpenRouter API key (defaults to configured OPENROUTER_API_KEY).
        openai_client: Optional preconfigured OpenAI client instance (useful for testing/mocking).

    Returns:
        str: Final response, report, or status summary produced by the agent.

    Raises:
        ValueError: If OPENROUTER_API_KEY is missing and no client is provided.
    """
    selected_model = model or DEFAULT_MODEL
    total_timeout = timeout_seconds if timeout_seconds is not None else TIMEOUT_SECONDS
    limit_steps = max_steps if max_steps is not None else MAX_STEPS
    effective_api_key = api_key or OPENROUTER_API_KEY

    if openai_client is None:
        if not effective_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not configured. "
                "Please configure OPENROUTER_API_KEY in the environment or .env file."
            )
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=effective_api_key,
        )
    else:
        client = openai_client

    # Build system and initial user instructions
    system_prompt = (
        "You are an expert autonomous software engineer worker operating inside the target repository workspace.\n"
        "You have access to filesystem tools (`read_file`, `write_file`, `list_dir`).\n"
        "All file paths must be relative to the workspace root.\n"
        "Work methodically: examine existing files, formulate a plan, make changes, "
        "and produce a clear, factual completion report."
    )

    user_content = task_prompt
    if target_files:
        user_content += f"\n\nTarget files relevant to this task:\n" + "\n".join(
            f"- {f}" for f in target_files
        )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    start_time = time.time()
    step_count = 0

    # Infinite loop detection state: tracks (tool_name, serialized_args) -> consecutive occurrences
    last_call_signature: Optional[Tuple[str, str]] = None
    consecutive_repeat_count = 0

    while step_count < limit_steps:
        # Check timeout limit
        elapsed = time.time() - start_time
        if elapsed >= total_timeout:
            return (
                f"Agent aborted: Execution exceeded timeout limit of {total_timeout} seconds "
                f"after {step_count} steps."
            )

        step_count += 1
        remaining_time = max(5.0, total_timeout - elapsed)

        try:
            response = client.chat.completions.create(
                model=selected_model,
                messages=messages,
                tools=AGENT_TOOLS_SCHEMA,
                timeout=remaining_time,
            )
        except Exception as api_err:
            logger.error("Error communicating with model provider: %s", api_err)
            return f"Agent provider error at step {step_count}: {api_err}"

        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None)

        # Append assistant message to history
        assistant_msg: Dict[str, Any] = {"role": "assistant"}
        if message.content is not None:
            assistant_msg["content"] = message.content
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        # If no tool calls were requested, the model has completed its task
        if not tool_calls:
            return message.content or "Task completed with no textual output."

        # Execute each requested tool call
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            raw_args = tool_call.function.arguments

            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except json.JSONDecodeError:
                parsed_args = {}

            # Infinite loop detector: check for 3 consecutive identical invocations
            call_sig = (tool_name, json.dumps(parsed_args, sort_keys=True))
            if call_sig == last_call_signature:
                consecutive_repeat_count += 1
            else:
                last_call_signature = call_sig
                consecutive_repeat_count = 1

            if consecutive_repeat_count >= 3:
                return (
                    f"Agent aborted: Infinite loop detected! Tool '{tool_name}' was invoked 3 "
                    f"consecutive times with identical arguments: {raw_args}"
                )

            # Run tool
            tool_result = _execute_tool(tool_name, parsed_args)

            # Append tool result to conversation history
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

    return (
        f"Agent stopped: Reached maximum step limit of {limit_steps} steps without final resolution.\n"
        f"Last known response: {messages[-1].get('content', 'No content')}"
    )
