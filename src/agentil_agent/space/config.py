"""
Configuration management for single workspace.

Uses Pydantic for validation and supports TOML config files.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Assistant Configuration
# =============================================================================

# Default voice-assistant prompt optimized for TTS output
DEFAULT_ASSISTANT_PROMPT = """You are a voice assistant. Your responses will be spoken aloud via text-to-speech.

Guidelines:
- Keep responses concise and conversational
- Avoid markdown formatting (tables, bullet lists, headers)
- Don't output code blocks unless specifically asked
- Use natural spoken language
- If you need to list items, use "first, second, third" etc.
- For technical content, explain verbally rather than showing code
- Avoid special characters that don't translate well to speech
"""

class AssistantConfig(BaseModel):
    """Assistant settings."""
    
    name: str = Field(default="voice-assistant", description="Assistant name")
    description: str = Field(
        default="Voice-optimized assistant for general tasks",
        description="Assistant description"
    )
    prompt: str = Field(
        default=DEFAULT_ASSISTANT_PROMPT,
        description="System prompt for the voice assistant",
    )
    tools: list[str] = Field(
        default=["read", "write"],
        description="List of tools and mcp-servers available to assistant",
    )


# =============================================================================
# Main Configuration
# =============================================================================


class SpaceConfig(BaseModel):
    """Main configuration for space."""

    assistants: list[AssistantConfig] = Field(default_factory=list[AssistantConfig])

    @classmethod
    def get_config_paths(cls) -> list[Path]:
        """Get list of config file paths to search (in priority order)."""
        paths = []

        # Project-level config
        cwd = Path.cwd()
        paths.append(cwd / "space-config.toml")
        paths.append(cwd / ".space-config.toml")

        # TODO: search parent directories until reach root sandbox space? (could merge configs, priority to lower levels)
        
        # TODO: merge with server-level space-config?
        # paths.append(server-config-directory/space-config.toml)

        return paths

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> "SpaceConfig":
        """
        Load configuration from file.

        Args:
            config_path: Optional explicit path to config file.
                        If not provided, searches default locations.

        Returns:
            Loaded configuration (or defaults if no config found)
        """
        import tomli

        # If explicit path provided, use it
        if config_path:
            path = Path(config_path)
            if path.exists():
                with open(path, "rb") as f:
                    data = tomli.load(f)
                return cls.model_validate(data)
            raise FileNotFoundError(f"Config file not found: {path}")

        # Search default locations
        for path in cls.get_config_paths():
            if path.exists():
                with open(path, "rb") as f:
                    data = tomli.load(f)
                return cls.model_validate(data)

        # No config found, return defaults
        return cls()

    def save(self, config_path: Path | str) -> None:
        """
        Save configuration to file.

        Args:
            config_path: Path to save config file
        """
        import tomli_w

        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            tomli_w.dump(self.model_dump(), f)

    def to_toml(self) -> str:
        """Export configuration as TOML string."""
        import tomli_w

        return tomli_w.dumps(self.model_dump())


# =============================================================================
# Global Config Instance
# =============================================================================

def get_space_config(path: str) -> SpaceConfig:
    """Get the space configuration instance."""
    return SpaceConfig.load(path)


def set_space_config(config: SpaceConfig, path: str) -> None:
    """Set the space configuration"""
    return config.save(path)


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = SpaceConfig()
    print("Default space configuration:")
    print(config.to_toml())
