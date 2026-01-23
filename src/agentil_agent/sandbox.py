"""
Sandbox environment management for Agentil Agent.

Manages the sandbox workspace directory and voice-assistant agent configuration.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


def get_sandbox_path(config: "Config") -> Path:
    """
    Get the sandbox workspace path.

    Args:
        config: Application configuration

    Returns:
        Resolved path to sandbox workspace
    """
    return Path(config.sandbox.path).expanduser().resolve()


def ensure_sandbox(config: "Config") -> Path:
    """
    Ensure sandbox directory exists with proper configuration.

    Creates the sandbox directory and opencode.json if they don't exist.

    Args:
        config: Application configuration

    Returns:
        Path to sandbox workspace
    """
    sandbox_path = get_sandbox_path(config)

    if not sandbox_path.exists():
        if not config.sandbox.auto_create:
            raise FileNotFoundError(
                f"Sandbox directory does not exist: {sandbox_path}\n"
                "Set sandbox.auto_create = true or create the directory manually."
            )

        logger.info(f"Creating sandbox directory: {sandbox_path}")
        sandbox_path.mkdir(parents=True, exist_ok=True)

    # Ensure opencode.json exists with voice-assistant agent
    if config.sandbox.create_opencode_json:
        opencode_json_path = sandbox_path / "opencode.json"
        if not opencode_json_path.exists():
            logger.info(f"Creating voice-assistant agent config: {opencode_json_path}")
            opencode_config = generate_opencode_json(config)
            opencode_json_path.write_text(json.dumps(opencode_config, indent=2))

    return sandbox_path


def generate_opencode_json(config: "Config") -> dict:
    """
    Generate opencode.json content with voice-assistant agent.

    Args:
        config: Application configuration

    Returns:
        Dictionary suitable for opencode.json
    """
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "github-copilot/gpt-5-mini", # TODO: temporary free model
        "agent": {
            config.assistant.name: {
                "description": config.assistant.description,
                "mode": "primary",
                "prompt": config.assistant.prompt,
                "tools": {
                    "read": True,
                    "write": True,
                    "bash": True,
                    # TODO: custom mcp servers
                }
            }
        },
        "default_agent": config.assistant.name,
    }


def update_sandbox_agent(config: "Config") -> None:
    """
    Update the voice-assistant agent in sandbox opencode.json.

    Useful when the agent configuration in agentil-agent.toml changes.

    Args:
        config: Application configuration
    """
    sandbox_path = get_sandbox_path(config)
    opencode_json_path = sandbox_path / "opencode.json"

    if not opencode_json_path.exists():
        # Just create fresh
        ensure_sandbox(config)
        return

    # Load existing config
    try:
        existing = json.loads(opencode_json_path.read_text())
    except json.JSONDecodeError:
        logger.warning("Invalid opencode.json, regenerating")
        existing = {}

    # Update agent
    if "agents" not in existing:
        existing["agents"] = {}

    existing["agents"][config.assistant.name] = {
        "description": config.assistant.description,
        "systemPrompt": config.assistant.prompt,
    }
    existing["defaultAgent"] = config.assistant.name

    opencode_json_path.write_text(json.dumps(existing, indent=2))
    logger.info(f"Updated voice-assistant agent in {opencode_json_path}")


def is_sandbox_initialized(config: "Config") -> bool:
    """
    Check if sandbox is properly initialized.

    Args:
        config: Application configuration

    Returns:
        True if sandbox directory and opencode.json exist
    """
    sandbox_path = get_sandbox_path(config)
    opencode_json_path = sandbox_path / "opencode.json"
    return sandbox_path.exists() and opencode_json_path.exists()


def get_working_directory(
    config: "Config",
    local: bool = False,
    project_path: str | None = None,
) -> Path:
    """
    Determine the working directory based on mode.

    Args:
        config: Application configuration
        local: If True, use current working directory
        project_path: If provided, use this path

    Returns:
        Path to use as working directory
    """
    if project_path:
        path = Path(project_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Project path does not exist: {path}")
        return path

    if local:
        return Path.cwd().resolve()

    # Default: sandbox mode
    return ensure_sandbox(config)


# For testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    from .config import Config

    config = Config()

    print(f"Sandbox path: {get_sandbox_path(config)}")
    print(f"Sandbox initialized: {is_sandbox_initialized(config)}")

    if "--init" in sys.argv:
        path = ensure_sandbox(config)
        print(f"Sandbox ensured at: {path}")

        opencode_json = path / "opencode.json"
        print(f"\nopencode.json contents:")
        print(opencode_json.read_text())
