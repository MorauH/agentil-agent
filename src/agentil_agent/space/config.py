"""
Configuration management for individual spaces.

Uses Pydantic for validation and supports TOML config files (space.toml).
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# =============================================================================
# Space Configuration File Name
# =============================================================================

SPACE_CONFIG_FILENAME = "space.toml"


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
    """Configuration for a single assistant within a space."""

    name: str = Field(default="voice-assistant", description="Assistant name")
    description: str = Field(
        default="Voice-optimized assistant for general tasks",
        description="Assistant description",
    )
    prompt: str = Field(
        default=DEFAULT_ASSISTANT_PROMPT,
        description="System prompt for the assistant",
    )
    mode: str = Field(
        default="primary",
        description="Assistant mode (primary, secondary, etc.)",
    )
    tools: dict[str, bool] = Field(
        default_factory=lambda: {"read": True, "write": True, "bash": True},
        description="Tools enabled for this assistant (tool_name: enabled)",
    )


# =============================================================================
# Main Space Configuration
# =============================================================================


class SpaceConfig(BaseModel):
    """
    Configuration for a single space.
    
    Stored in space.toml within the space directory.
    """

    # Space metadata
    name: str = Field(default="default", description="Human-readable space name")
    description: str | None = Field(
        default=None, description="Optional space description"
    )

    # Assistants available in this space
    assistants: list[AssistantConfig] = Field(
        default_factory=lambda: [AssistantConfig()],
        description="Assistants configured for this space",
    )

    # Default assistant to use
    default_assistant: str = Field(
        default="voice-assistant",
        description="Name of the default assistant to use",
    )

    # MCP servers enabled for this space (by ID)
    enabled_mcps: list[str] = Field(
        default_factory=list,
        description="MCP server IDs enabled for this space",
    )

    @classmethod
    def get_config_path(cls, space_path: Path) -> Path:
        """Get the config file path for a space directory."""
        return space_path / SPACE_CONFIG_FILENAME

    @classmethod
    def load(cls, space_path: Path) -> "SpaceConfig":
        """
        Load configuration from space.toml in the given directory.

        Args:
            space_path: Path to the space directory

        Returns:
            Loaded configuration (or defaults if no config found)
        """
        import tomli

        config_file = cls.get_config_path(space_path)

        if config_file.exists():
            try:
                with open(config_file, "rb") as f:
                    data = tomli.load(f)
                return cls.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to load {config_file}: {e}, using defaults")
                return cls()

        # No config found, return defaults
        return cls()

    def save(self, space_path: Path) -> None:
        """
        Save configuration to space.toml in the given directory.

        Args:
            space_path: Path to the space directory
        """
        import tomli_w

        config_file = self.get_config_path(space_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, "wb") as f:
            tomli_w.dump(self.model_dump(exclude_none=True), f)

        logger.debug(f"Saved space config to {config_file}")

    def to_toml(self) -> str:
        """Export configuration as TOML string."""
        import tomli_w

        return tomli_w.dumps(self.model_dump(exclude_none=True))

    def get_assistant(self, name: str | None = None) -> AssistantConfig | None:
        """
        Get an assistant by name.

        Args:
            name: Assistant name, or None for default

        Returns:
            AssistantConfig or None if not found
        """
        target_name = name or self.default_assistant
        for assistant in self.assistants:
            if assistant.name == target_name:
                return assistant
        return None


# =============================================================================
# Utility Functions
# =============================================================================


def get_space_config(space_path: Path | str) -> SpaceConfig:
    """
    Load space configuration from a directory.

    Args:
        space_path: Path to space directory

    Returns:
        SpaceConfig instance
    """
    return SpaceConfig.load(Path(space_path))


def save_space_config(config: SpaceConfig, space_path: Path | str) -> None:
    """
    Save space configuration to a directory.

    Args:
        config: SpaceConfig to save
        space_path: Path to space directory
    """
    config.save(Path(space_path))


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = SpaceConfig()
    print("Default space configuration:")
    print(config.to_toml())
