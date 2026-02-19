"""
Common types for MCP (Model Context Protocol) servers.

These types provide a standardized interface across all MCP implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class MCPResourceHint:
    """A filesystem resource that an MCP server exposes to the UI.

    Declared in ``mcp-manifest.json`` under ``ui_resources``.
    Each resource maps to a directory relative to ``SPACE_DIR``
    that should be browsable/manageable through the web interface.
    """

    path: str
    """Directory path relative to SPACE_DIR (e.g. ``"documents"``)."""

    label: str
    """Human-readable label for the UI (e.g. ``"Reference Documents"``)."""

    description: str
    """Short description shown to the user."""

    file_types: list[str] = field(default_factory=list)
    """Glob patterns for allowed file types (e.g. ``["*.pdf"]``).

    An empty list means all file types are accepted.
    """

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": self.path,
            "label": self.label,
            "description": self.description,
            "file_types": self.file_types,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MCPResourceHint:
        """Create from dictionary."""
        return cls(
            path=data["path"],
            label=data["label"],
            description=data.get("description", ""),
            file_types=data.get("file_types", []),
        )


@dataclass
class MCPManifest:
    """Declarative metadata from an MCP server's ``mcp-manifest.json``.

    Read during installation and stored in the MCP registry so that
    consumers (e.g. code-report) can render appropriate UI without
    hardcoded knowledge of individual MCP servers.
    """

    name: str | None = None
    """Human-readable display name."""

    description: str | None = None
    """What this MCP server does."""

    version: str | None = None
    """Semantic version string."""

    ui_resources: list[MCPResourceHint] = field(default_factory=list)
    """Filesystem directories to expose in the web UI."""

    init_dirs: list[str] = field(default_factory=list)
    """Directories to auto-create when the MCP is enabled for a space.

    Directories starting with ``.`` are hidden infrastructure;
    others may overlap with ``ui_resources``.
    """

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "ui_resources": [r.to_dict() for r in self.ui_resources],
            "init_dirs": self.init_dirs,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MCPManifest:
        """Create from dictionary."""
        return cls(
            name=data.get("name"),
            description=data.get("description"),
            version=data.get("version"),
            ui_resources=[
                MCPResourceHint.from_dict(r) for r in data.get("ui_resources", [])
            ],
            init_dirs=data.get("init_dirs", []),
        )


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

    manifest: MCPManifest | None = None
    """Optional manifest loaded from ``mcp-manifest.json`` in the repo."""

    def __repr__(self) -> str:
        """String representation."""
        desc = f", description='{self.description}'" if self.description else ""
        return f"MCPServerInfo(id='{self.id}', name='{self.name}'{desc})"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        data: dict = {
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
        if self.manifest is not None:
            data["manifest"] = self.manifest.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> MCPServerInfo:
        """Create from dictionary."""
        manifest_data = data.get("manifest")
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
            manifest=MCPManifest.from_dict(manifest_data) if manifest_data else None,
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
