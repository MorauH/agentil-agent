"""
Common types for mcp.

These types provide a standardized interface across all mcp-implementations
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPServer:
    """
    Generic server representation
    """

    id: str
    """Unique mcp-server identifier."""

    description: str | None = None
    """Optional human-readable description."""

    type: str | None = None
    """local or remote or installable"""

    def __repr__(self) -> str:
        """String representation."""
        title_str = f", description='{self.description}'" if self.description else ""
        return f"MCP-Server(id='{self.id}'{title_str})"

