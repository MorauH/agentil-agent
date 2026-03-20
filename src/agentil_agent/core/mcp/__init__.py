"""
MCP (Model Context Protocol) server management.

Downloads MCP servers and connects to local or remote servers.
"""

from .types import MCPManifest, MCPResourceHint, MCPServerInfo, MCPSubgroup
from .manager import MCPManager

__all__ = [
    # Types
    "MCPManifest",
    "MCPResourceHint",
    "MCPServerInfo",
    "MCPSubgroup",
    # Manager
    "MCPManager",
]
