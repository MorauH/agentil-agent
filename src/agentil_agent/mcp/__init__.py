"""
MCP (Model Context Protocol) server management.

Downloads MCP servers and connects to local or remote servers.
"""

from .types import MCPServerInfo
from .manager import MCPManager, MCP_REGISTRY_FILENAME
from .nix_installer import get_remote_repo, get_mcp_executable

__all__ = [
    # Types
    "MCPServerInfo",
    # Manager
    "MCPManager",
    "MCP_REGISTRY_FILENAME",
    # Installer utilities
    "get_remote_repo",
    "get_mcp_executable",
]
