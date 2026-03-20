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
DEFAULT_ASSISTANT_PROMPT = """You are an assistant. Your responses will be spoken aloud via text-to-speech.

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
    """Configuration for a single assistant within a space.

    Each assistant has its own tool permissions, MCP server access list,
    and optional model override.  These are written into the agent backend's
    configuration (e.g. ``opencode.json``) so each agent can have a
    distinct capability set.
    """

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
    enabled_mcps: list[str] = Field(
        default_factory=list,
        description="MCP server IDs enabled for this assistant",
    )
    model: str | None = Field(
        default=None,
        description="Model identifier (e.g. 'anthropic/claude-sonnet-4'). "
        "None means use the space or global default.",
    )


# =============================================================================
# Main Space Configuration
# =============================================================================


class SpaceConfig(BaseModel):
    """Configuration for a single space.

    Stored in ``space.toml`` within the space directory.

    MCP server access is configured **per-assistant** via
    ``AssistantConfig.enabled_mcps``.  The convenience property
    :pyattr:`all_enabled_mcps` returns the deduplicated union across
    all assistants (useful for bulk registration with the agent backend).
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

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------

    @property
    def all_enabled_mcps(self) -> list[str]:
        """Deduplicated union of MCP *server IDs* across all assistants.

        Entries in ``AssistantConfig.enabled_mcps`` may use the subgroup
        format ``"server_id/subgroup"`` — this property strips the
        subgroup suffix so that callers get bare server IDs suitable for
        server-level operations (e.g. registration, installation checks).

        Returns:
            Ordered list of unique MCP server IDs referenced by any
            assistant in this space.
        """
        seen: set[str] = set()
        result: list[str] = []
        for assistant in self.assistants:
            for mcp_entry in assistant.enabled_mcps:
                server_id = mcp_entry.split("/", 1)[0]
                if server_id not in seen:
                    seen.add(server_id)
                    result.append(server_id)
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @classmethod
    def get_config_path(cls, space_path: Path) -> Path:
        """Get the config file path for a space directory."""
        return space_path / SPACE_CONFIG_FILENAME

    @classmethod
    def load(cls, space_path: Path) -> "SpaceConfig":
        """Load configuration from space.toml in the given directory.

        Includes a migration step: if the legacy top-level
        ``enabled_mcps`` key is present it is pushed into every
        assistant and removed from the top level.

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

                # --- Migration: top-level enabled_mcps → per-assistant ---
                legacy_mcps = data.pop("enabled_mcps", None)
                if legacy_mcps:
                    for asst in data.get("assistants", []):
                        existing = asst.get("enabled_mcps", [])
                        merged = list(dict.fromkeys(existing + legacy_mcps))
                        asst["enabled_mcps"] = merged
                    logger.info(
                        "Migrated top-level enabled_mcps %s into assistants",
                        legacy_mcps,
                    )

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
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = SpaceConfig()
    print("Default space configuration:")
    print(config.to_toml())
