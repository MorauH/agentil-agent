"""
OpenCode agent implementation.

Adapts OpenCode's HTTP/SSE API to the BaseAgent interface.
"""

from .agent import OpenCodeAgent, OpenCodeAgentFactory
from .connection import ConnectionManager, ConnectionState
from .events import EventType, MessagePart, SSEEvent, SessionStatus
from .exceptions import (
    OpenCodeConnectionError,
    OpenCodeError,
    OpenCodeNotInstalledError,
    OpenCodeSessionError,
    OpenCodeTimeoutError,
)
from .messages import Message, MessageManager
from .server import ServerManager
from .server_pool import ServerPool, ServerInstance, PortAllocation
from .session import Session, SessionManager
from .streaming import StreamManager

__all__ = [
    # Agent
    "OpenCodeAgent",
    "OpenCodeAgentFactory",
    # Managers
    "ConnectionManager",
    "ServerManager",
    "ServerPool",
    "SessionManager",
    "MessageManager",
    "StreamManager",
    # Models
    "Session",
    "Message",
    "MessagePart",
    "SSEEvent",
    "ServerInstance",
    "PortAllocation",
    # Types
    "ConnectionState",
    "EventType",
    "SessionStatus",
    # Exceptions
    "OpenCodeError",
    "OpenCodeConnectionError",
    "OpenCodeNotInstalledError",
    "OpenCodeTimeoutError",
    "OpenCodeSessionError",
]
