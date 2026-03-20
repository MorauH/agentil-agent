"""
OpenCode agent implementation.

Adapts OpenCode's HTTP/SSE API to the BaseAgent interface.
"""

from .agent import OpenCodeAgentFactory

__all__ = [
    "OpenCodeAgentFactory",
]
