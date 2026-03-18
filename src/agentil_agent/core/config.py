"""
Configuration management for Agentil Agent Core.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


# =============================================================================
# OpenCode Configuration
# =============================================================================


class OpenCodeConfig(BaseModel):
    """OpenCode server connection settings."""

    host: str = Field(default="127.0.0.1", description="OpenCode server hostname")
    base_port: int = Field(
        default=4096, 
        description="Base port for OpenCode servers (each space gets base_port + offset)"
    )
    max_servers: int = Field(
        default=10,
        description="Maximum number of concurrent OpenCode servers (port range size)"
    )
    auto_start: bool = Field(
        default=True, description="Automatically start OpenCode server if not running"
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")
    

# =============================================================================
# Agent Backend Configuration
# =============================================================================


class AgentBackendConfig(BaseModel):
    """Agent backend settings (which AI agent implementation to use)."""

    type: str = Field(
        default="opencode",
        description="Backend agent implementation to use (e.g., opencode)",
    )
    opencode: OpenCodeConfig = Field(default_factory=OpenCodeConfig)


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
    """Assistant prompt/settings."""

    name: str = Field(default="voice-assistant", description="Assistant name")
    description: str = Field(
        default="Voice-optimized assistant for general tasks",
        description="Assistant description",
    )
    prompt: str = Field(
        default=DEFAULT_ASSISTANT_PROMPT,
        description="System prompt for the voice assistant",
    )


# =============================================================================
# Space Manager Configuration
# =============================================================================


class SpaceManagerConfig(BaseModel):
    """Space manager settings."""

    spaces_root: str = Field(
        default="~/.config/agentil-agent/spaces",
        description="Root directory for space storage",
    )
    default_space_type: str = Field(
        default="directory",
        description="Default type for new spaces",
    )
    auto_initialize: bool = Field(
        default=True,
        description="Automatically initialize SpaceManager on server startup",
    )


# =============================================================================
# MCP Manager Configuration
# =============================================================================


class MCPManagerConfig(BaseModel):
    """MCP manager settings."""

    base_path: str = Field(
        default="~/.config/agentil-agent/mcp-servers",
        description="Base directory for MCP server installations",
    )
    auto_initialize: bool = Field(
        default=True,
        description="Automatically initialize MCPManager on server startup",
    )


# =============================================================================
# Main Configuration
# =============================================================================


class CoreConfig(BaseModel):
    """Main configuration for Agentil Agent Core."""

    agent: AgentBackendConfig = Field(default_factory=AgentBackendConfig)
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    spaces: SpaceManagerConfig = Field(default_factory=SpaceManagerConfig)
    mcp: MCPManagerConfig = Field(default_factory=MCPManagerConfig)

    def get_spaces_root(self) -> Path:
        """Get the resolved spaces root directory path."""
        return Path(self.spaces.spaces_root).expanduser().resolve()

    def get_mcp_base_path(self) -> Path:
        """Get the resolved MCP servers base directory path."""
        return Path(self.mcp.base_path).expanduser().resolve()


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = CoreConfig()
    print("Default configuration:")
    print(config.to_toml())
