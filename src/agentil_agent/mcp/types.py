"""
Common types for MCP (Model Context Protocol) servers.

These types provide a standardized interface across all MCP implementations.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class MCPServerInfo:
    """
    Information about an installed MCP server.
    
    Represents a system-level MCP server that can be enabled in spaces.
    """

    id: str
    """Unique MCP server identifier (e.g., 'rag-mcp', 'scripts-mcp')."""

    name: str
    """Human-readable name."""

    executable_path: str
    """Path to the executable binary."""

    description: str | None = None
    """Optional description of what this MCP server does."""

    version: str | None = None
    """Optional version string."""

    source_type: Literal["local", "git", "registry"] = "local"
    """How this MCP server was installed."""

    source_url: str | None = None
    """Original source URL (for git-installed servers)."""

    source_ref: str | None = None
    """Git ref (branch/tag/commit) for git-installed servers."""

    args: list[str] = field(default_factory=list)
    """Default arguments to pass to the executable."""

    env: dict[str, str] = field(default_factory=dict)
    """Environment variables to set when running."""

    def __repr__(self) -> str:
        """String representation."""
        desc = f", description='{self.description}'" if self.description else ""
        return f"MCPServerInfo(id='{self.id}', name='{self.name}'{desc})"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "executable_path": self.executable_path,
            "description": self.description,
            "version": self.version,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "source_ref": self.source_ref,
            "args": self.args,
            "env": self.env,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MCPServerInfo":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            executable_path=data["executable_path"],
            description=data.get("description"),
            version=data.get("version"),
            source_type=data.get("source_type", "local"),
            source_url=data.get("source_url"),
            source_ref=data.get("source_ref"),
            args=data.get("args", []),
            env=data.get("env", {}),
        )

    def get_opencode_config(self, enabled: bool = True) -> dict:
        """
        Generate OpenCode-compatible MCP server configuration.

        Returns:
            Dictionary suitable for OpenCode's McpLocalConfig format:
            - type: "local"
            - command: list of command and arguments
            - enabled: whether the MCP server is enabled
            - environment: optional environment variables
        """
        config: dict = {
            "type": "local",
            "command": [self.executable_path] + self.args,
            "enabled": enabled,
        }
        if self.env:
            config["environment"] = self.env
        return config
