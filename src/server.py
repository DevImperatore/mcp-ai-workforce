"""FastMCP server implementation for mcp-ai-workforce.

Exposes tools for task delegation to autonomous ReAct workers, model provider status
inspection, and workspace git diff auditing.
"""

from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    # Backward/forward compatibility for mcp>=2.0 where FastMCP was renamed to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

from src.config import (
    DEFAULT_MODEL,
    MAX_STEPS,
    OPENROUTER_API_KEY,
    TIMEOUT_SECONDS,
    WORKSPACE_ROOT,
)
from src.worker.agent_loop import run_worker_agent

# Initialize FastMCP server
mcp = FastMCP(
    name="mcp-ai-workforce",
    instructions=(
        "mcp-ai-workforce provides tools for autonomous AI agent delegation, "
        "workspace change auditing, and model status monitoring."
    ),
)


import asyncio
import os

@mcp.tool()
async def workforce_delegate(
    task_prompt: str,
    target_files: Optional[List[str]] = None,
    model: Optional[str] = None,
    timeout_seconds: int = 300,
) -> str:
    """Delegate a software engineering task to an autonomous ReAct worker agent.

    The worker operates with filesystem tools under strict guardrails to inspect,
    read, modify, and create workspace files safely.

    Args:
        task_prompt: Comprehensive description of the task or feature to implement.
        target_files: Optional list of relevant workspace-relative file paths.
        model: OpenRouter model to utilize (defaults to DEFAULT_MODEL).
        timeout_seconds: Execution timeout limit in seconds (default: 300).

    Returns:
        str: Final completion summary or diagnostic output from the worker agent.
    """
    try:
        return await asyncio.to_thread(
            run_worker_agent,
            task_prompt=task_prompt,
            target_files=target_files,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        return f"Workforce delegation failed with error: {exc}"


@mcp.tool()
def workforce_models_status() -> Dict[str, Any]:
    """Inspect current configuration, supported models, and OpenRouter readiness.

    Returns:
        Dict[str, Any]: Configuration status including API key presence, default model,
        configured workspace root, and suggested coding models.
    """
    recommended_models = [
        "qwen/qwen-2.5-coder-32b-instruct",
        "deepseek/deepseek-chat",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "meta-llama/llama-3.3-70b-instruct",
    ]

    has_api_key = bool(OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip())

    return {
        "status": "ready" if has_api_key else "needs_configuration",
        "openrouter_api_key_configured": has_api_key,
        "default_model": DEFAULT_MODEL,
        "workspace_root": str(WORKSPACE_ROOT),
        "max_steps": MAX_STEPS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "recommended_models": recommended_models,
    }


@mcp.tool()
def workforce_audit_diff(staged: bool = False) -> str:
    """Execute a git diff inspection across the workspace to audit worker modifications.

    Args:
        staged: If True, inspect staged changes (`git diff --staged`);
                otherwise inspect unstaged workspace modifications (`git diff`).

    Returns:
        str: The unified git diff output or an informative message if no changes exist.
    """
    cmd = [
        "git",
        "--no-pager",
        "diff",
        "--no-ext-diff",
        "--no-color",
    ]
    if staged:
        cmd.append("--staged")

    safe_env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}

    try:
        result = subprocess.run(
            cmd,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=safe_env,
        )

        if result.returncode != 0:
            return f"Git diff exited with code {result.returncode}:\n{result.stderr.strip()}"

        diff_output = result.stdout.strip()
        if not diff_output:
            scope = "staged" if staged else "unstaged"
            return f"Clean workspace: No {scope} git changes detected in '{WORKSPACE_ROOT}'."

        return diff_output

    except FileNotFoundError:
        return "Error: 'git' executable not found on system PATH."
    except Exception as exc:
        return f"Error executing git diff: {exc}"


def main() -> None:
    """Run the FastMCP server with stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
