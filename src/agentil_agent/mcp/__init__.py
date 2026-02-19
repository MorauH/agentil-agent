"""
MCP (Model Context Protocol) server management.

Downloads MCP servers and connects to local or remote servers.
"""

from .types import MCPServerInfo
from .manager import MCPManager, MCP_REGISTRY_FILENAME
from .nix_installer import (
    delete_repo_clone,
    get_clone_dir,
    get_mcp_executable,
    get_remote_repo,
    update_remote_repo,
)

__all__ = [
    # Types
    "MCPServerInfo",
    # Manager
    "MCPManager",
    "MCP_REGISTRY_FILENAME",
    # Installer utilities
    "get_remote_repo",
    "get_mcp_executable",
    "update_remote_repo",
    "delete_repo_clone",
    "get_clone_dir",
]
