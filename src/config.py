"""Configuration management for mcp-ai-workforce.

Loads environment variables from .env files or the system environment and exposes
validated configuration settings with strict typing and sensible defaults.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Automatically locate and load .env file from project root or parent workspace
_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CURRENT_DIR.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.is_file():
    load_dotenv(dotenv_path=_ENV_FILE)
else:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable application settings for mcp-ai-workforce.

    Attributes:
        openrouter_api_key: API key used to authenticate with OpenRouter.
        default_model: Model identifier requested by default for worker loops.
        workspace_root: Canonical root path for workspace guardrails and file tools.
        max_steps: Maximum reasoning and tool-calling iterations before aborting.
        timeout_seconds: Maximum execution duration in seconds for an agent task.
    """

    openrouter_api_key: str
    default_model: str
    workspace_root: Path
    max_steps: int
    timeout_seconds: int


def _resolve_workspace_root(env_val: Optional[str]) -> Path:
    """Resolve and validate the canonical workspace root path.

    Args:
        env_val: Value provided in the environment, if any.

    Returns:
        Canonical absolute Path to the workspace root. Defaults to current working directory.
    """
    if env_val and env_val.strip():
        return Path(env_val.strip()).resolve()
    return Path.cwd().resolve()


def get_settings() -> Settings:
    """Retrieve the application settings instance populated from the environment.

    Returns:
        Settings: Validated dataclass instance containing all configuration parameters.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    model = os.getenv("DEFAULT_MODEL", "qwen/qwen-2.5-coder-32b-instruct").strip()
    root_path = _resolve_workspace_root(os.getenv("WORKSPACE_ROOT"))
    
    try:
        max_steps = int(os.getenv("MAX_STEPS", "15"))
    except ValueError:
        max_steps = 15

    try:
        timeout_seconds = int(os.getenv("TIMEOUT_SECONDS", "300"))
    except ValueError:
        timeout_seconds = 300

    return Settings(
        openrouter_api_key=api_key,
        default_model=model,
        workspace_root=root_path,
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
    )


# Module-level exports for direct import convenience
SETTINGS = get_settings()
OPENROUTER_API_KEY: str = SETTINGS.openrouter_api_key
DEFAULT_MODEL: str = SETTINGS.default_model
WORKSPACE_ROOT: Path = SETTINGS.workspace_root
MAX_STEPS: int = SETTINGS.max_steps
TIMEOUT_SECONDS: int = SETTINGS.timeout_seconds
