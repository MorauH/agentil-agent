"""
Mock agent implementation.

Provides a simple mock agent for testing without external dependencies.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..base import BaseAgent, BaseAgentFactory
from ..types import AgentSession, AgentResponse

if TYPE_CHECKING:
    from ...config import Config
    from ...space import BaseSpace
    from ...mcp import MCPManager

logger = logging.getLogger(__name__)


class MockAgent(BaseAgent):
    """
    Mock agent for testing.

    Returns canned responses without connecting to any external service.
    """

    def __init__(self, response_prefix: str = "Mock response to: ") -> None:
        """
        Initialize mock agent.

        Args:
            response_prefix: Prefix for mock responses
        """
        self._response_prefix = response_prefix
        self._initialized = False
        self._sessions: dict[str, AgentSession] = {}
        self._space: "BaseSpace | None" = None
        self._mcp_manager: "MCPManager | None" = None

    @property
    def space(self) -> "BaseSpace | None":
        """Return the current space, or None if not set."""
        return self._space

    def set_space(self, space: "BaseSpace", mcp_manager: "MCPManager | None" = None) -> None:
        """
        Set the space this agent operates in.

        For mock agent, this just stores the reference.

        Args:
            space: The space to operate in
            mcp_manager: Optional MCP manager for resolving MCP server info
        """
        logger.info(f"Mock agent: set_space called with '{space.space_id}'")
        self._space = space
        self._mcp_manager = mcp_manager

    async def initialize(self) -> None:
        """Initialize the agent."""
        logger.info("Mock agent initializing...")
        self._initialized = True
        logger.info("Mock agent initialized")

    async def shutdown(self) -> None:
        """Shutdown the agent."""
        logger.info("Mock agent shutting down...")
        self._initialized = False
        self._sessions.clear()
        logger.info("Mock agent shutdown complete")

    async def create_session(self, title: str | None = None) -> AgentSession:
        """Create a new mock session."""
        session_id = str(uuid.uuid4())
        session = AgentSession(
            id=session_id,
            title=title or "Mock Session",
            created_at=datetime.now(),
            metadata={"mock": True},
        )
        self._sessions[session_id] = session
        return session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a mock session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def send_message(
        self,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> AgentResponse:
        """Send a message and get mock response."""
        response_text = f"{self._response_prefix}{text}"
        return AgentResponse(
            text=response_text,
            message_id=str(uuid.uuid4()),
            metadata={"mock": True},
        )

    async def stream_response(
        self,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Stream mock response."""
        response = f"{self._response_prefix}{text}"
        # Simulate streaming by yielding word by word
        for word in response.split():
            yield word + " "

    async def abort_session(self, session_id: str) -> bool:
        """Abort mock session (no-op)."""
        return True

    @property
    def is_ready(self) -> bool:
        """Check if mock agent is ready."""
        return self._initialized

    @property
    def agent_type(self) -> str:
        """Return agent type."""
        return "mock"


class MockAgentFactory(BaseAgentFactory):
    """Factory for creating mock agent instances."""

    def create_agent(self, config: "Config") -> BaseAgent:
        """Create a mock agent instance."""
        return MockAgent()

    def agent_type(self) -> str:
        """Return the agent type this factory creates."""
        return "mock"
