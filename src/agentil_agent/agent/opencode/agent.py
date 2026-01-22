"""
OpenCode agent implementation.

Adapts OpenCode's HTTP/SSE API to the BaseAgent interface.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseAgent, BaseAgentFactory
from ..types import AgentSession, AgentResponse
from ..exceptions import (
    AgentInitializationError,
    AgentNotReadyError,
    AgentSessionError,
)
from .connection import ConnectionManager, ConnectionState
from .exceptions import OpenCodeConnectionError, OpenCodeNotInstalledError
from .messages import MessageManager
from .server import ServerManager
from .session import Session, SessionManager
from .streaming import StreamManager

if TYPE_CHECKING:
    from ...config import OpenCodeConfig

logger = logging.getLogger(__name__)


class OpenCodeAgent(BaseAgent):
    """
    OpenCode agent implementation.

    Adapts OpenCode's HTTP/SSE API to the BaseAgent interface.
    Manages connection, server lifecycle, sessions, and streaming.
    """

    def __init__(
        self,
        config: "OpenCodeConfig",
        working_dir: Path | str | None = None,
    ) -> None:
        """
        Initialize OpenCode agent.

        Args:
            config: OpenCode configuration
            working_dir: Working directory for OpenCode operations
        """
        self.config = config
        self.base_url = f"http://{config.host}:{config.port}"

        # Initialize all managers
        self.connection = ConnectionManager(
            base_url=self.base_url,
            timeout=config.timeout,
        )

        self.server = ServerManager(
            connection_manager=self.connection,
            host=config.host,
            port=config.port,
            working_dir=working_dir,
        )

        self.sessions = SessionManager(
            base_url=self.base_url,
            timeout=config.timeout,
        )

        self.messages = MessageManager(
            base_url=self.base_url,
            timeout=config.timeout,
        )

        self.streams = StreamManager(
            base_url=self.base_url,
            timeout=config.timeout,
        )

        self._initialized = False

    @property
    def working_dir(self) -> Path | None:
        """Working directory for OpenCode operations."""
        return self.server.working_dir

    @working_dir.setter
    def working_dir(self, path: Path | str | None) -> None:
        """Set working directory."""
        self.server.working_dir = path

    # ========== BaseAgent Implementation ==========

    async def initialize(self) -> None:
        """
        Initialize the agent.

        Ensures OpenCode server is running and ready to handle requests.

        Raises:
            AgentInitializationError: If initialization fails
        """
        if self._initialized:
            return

        logger.info("Initializing OpenCode agent...")

        try:
            # Check if server is already running
            if not self.connection.check_connection():
                if self.config.auto_start:
                    logger.info("Starting OpenCode server...")
                    if not self.server.start_server():
                        raise AgentInitializationError(
                            f"Failed to start OpenCode server on {self.base_url}"
                        )
                else:
                    raise AgentInitializationError(
                        f"OpenCode server not running at {self.base_url}. "
                        f"Start it with: opencode serve --port {self.config.port}"
                    )

            logger.info(f"Connected to OpenCode server at {self.base_url}")
            logger.info(f"Server version: {self.connection.get_server_version()}")
            self._initialized = True

        except OpenCodeNotInstalledError as e:
            raise AgentInitializationError(str(e)) from e
        except OpenCodeConnectionError as e:
            raise AgentInitializationError(str(e)) from e

    async def shutdown(self) -> None:
        """
        Shutdown the agent and clean up resources.

        Closes HTTP clients and stops server if we started it.
        """
        logger.info("Shutting down OpenCode agent...")

        self.connection.close()
        self.sessions.close()
        self.messages.close()
        self.server.stop_server()

        self._initialized = False
        logger.info("OpenCode agent shutdown complete")

    async def create_session(self, title: str | None = None) -> AgentSession:
        """
        Create a new conversation session.

        Args:
            title: Optional session title

        Returns:
            AgentSession with standardized interface

        Raises:
            AgentNotReadyError: If agent is not initialized
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized before creating sessions")

        oc_session = self.sessions.create_session(title)

        return AgentSession(
            id=oc_session.id,
            title=oc_session.title,
            created_at=oc_session.created_at,
            metadata={
                "opencode_session": oc_session,
                "version": oc_session.version,
                "project_id": oc_session.project_id,
                "directory": oc_session.directory,
            },
        )

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted successfully

        Raises:
            AgentNotReadyError: If agent is not initialized
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")

        return self.sessions.delete_session(session_id)

    async def send_message(
        self,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Send a message and get complete response (non-streaming).

        Args:
            session_id: Session ID
            text: Message text
            **kwargs: Additional arguments (e.g., model override)

        Returns:
            AgentResponse with text and metadata

        Raises:
            AgentNotReadyError: If agent is not initialized
            AgentSessionError: If session doesn't exist
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")

        # Extract OpenCode-specific kwargs
        model = kwargs.get("model")

        try:
            # Send message (synchronous)
            response = self.messages.send_message(session_id, text, model)

            # Extract text
            response_text = self.messages.extract_text(response)

            # Get message metadata
            msg_info = self.messages.get_message_info(response)

            return AgentResponse(
                text=response_text,
                message_id=msg_info.id if msg_info else None,
                metadata={
                    "raw_response": response,
                    "model_id": msg_info.model_id if msg_info else None,
                    "provider_id": msg_info.provider_id if msg_info else None,
                },
            )
        except Exception as e:
            # Wrap OpenCode-specific exceptions in AgentSessionError
            if "session" in str(e).lower() or "not found" in str(e).lower():
                raise AgentSessionError(f"Session error: {e}") from e
            raise

    async def stream_response(
        self,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Send a message and stream response incrementally.

        Args:
            session_id: Session ID
            text: Message text
            **kwargs: Additional arguments (e.g., model override)

        Yields:
            Text deltas (incremental chunks)

        Raises:
            AgentNotReadyError: If agent is not initialized
            AgentSessionError: If session doesn't exist
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")

        # Extract OpenCode-specific kwargs
        model = kwargs.get("model")

        try:

            async def start_request() -> None:
                await self.messages.send_message_async(session_id, text, model)

            # Start listening to SSE *before* triggering the prompt to avoid
            # missing fast responses.
            async for chunk in self.streams.stream_text_response(
                session_id,
                start_request=start_request,
            ):
                yield chunk
        except Exception as e:
            # Wrap OpenCode-specific exceptions
            if "session" in str(e).lower() or "not found" in str(e).lower():
                raise AgentSessionError(f"Session error: {e}") from e
            raise

    async def abort_session(self, session_id: str) -> bool:
        """
        Abort/cancel ongoing processing in a session.

        Args:
            session_id: Session ID to abort

        Returns:
            True if aborted successfully

        Raises:
            AgentNotReadyError: If agent is not initialized
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")

        return self.sessions.abort_session(session_id)

    @property
    def is_ready(self) -> bool:
        """
        Check if agent is ready to handle requests.

        Returns:
            True if initialized and connected
        """
        return self._initialized and self.connection.is_connected()

    @property
    def agent_type(self) -> str:
        """
        Return the type/name of this agent implementation.

        Returns:
            "opencode"
        """
        return "opencode"

    # ========== Context Manager Support ==========

    def __enter__(self) -> "OpenCodeAgent":
        """Synchronous context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Synchronous context manager exit."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule shutdown
                loop.create_task(self.shutdown())
            else:
                loop.run_until_complete(self.shutdown())
        except RuntimeError:
            # No event loop, create one
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.shutdown())
            loop.close()

    async def __aenter__(self) -> "OpenCodeAgent":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.shutdown()

    # ========== Additional OpenCode-Specific Methods ==========
    # These are not part of BaseAgent but useful for OpenCode users

    def list_sessions(self) -> list[Session]:
        """
        List all OpenCode sessions.

        Note: This returns OpenCode-specific Session objects, not AgentSession.
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")
        return self.sessions.list_sessions()

    def get_session(self, session_id: str) -> Session:
        """
        Get OpenCode session details.

        Note: This returns OpenCode-specific Session object, not AgentSession.
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")
        return self.sessions.get_session(session_id)

    def ensure_session(self, title: str = "Voice Session") -> Session:
        """
        Ensure a session exists, creating if needed.

        Note: This returns OpenCode-specific Session object, not AgentSession.
        """
        if not self._initialized:
            raise AgentNotReadyError("Agent must be initialized")
        return self.sessions.ensure_session(title)

    def check_connection(self) -> bool:
        """Check if OpenCode server is reachable."""
        return self.connection.check_connection()

    def get_server_version(self) -> str | None:
        """Get OpenCode server version."""
        return self.connection.get_server_version()

    @staticmethod
    def is_opencode_installed() -> bool:
        """Check if OpenCode CLI is installed."""
        return ServerManager.is_opencode_installed()

    @staticmethod
    def get_opencode_version() -> str | None:
        """Get installed OpenCode CLI version."""
        return ServerManager.get_opencode_version()


class OpenCodeAgentFactory(BaseAgentFactory):
    """Factory for creating OpenCode agent instances."""

    def create_agent(self, config: Any) -> BaseAgent:
        """Create an OpenCode agent instance.

        This factory supports being passed either:
        - the full application `Config` (preferred), or
        - an `OpenCodeConfig` instance.
        """

        # Preferred: application Config
        opencode_cfg = getattr(getattr(config, "agent", None), "opencode", None)
        if opencode_cfg is not None:
            working_dir = config.get_working_dir()
            return OpenCodeAgent(opencode_cfg, working_dir=working_dir)

        # Fallback: OpenCodeConfig directly
        return OpenCodeAgent(config)

    def agent_type(self) -> str:
        """Return the agent type this factory creates."""
        return "opencode"
