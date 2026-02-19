"""
OpenCode agent implementation.

Adapts OpenCode's HTTP/SSE API to the BaseAgent interface.
"""

from __future__ import annotations

import json
import logging
import shutil
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
from .server_pool import ServerPool, ServerInstance
from .session import Session, SessionManager
from .streaming import StreamManager

if TYPE_CHECKING:
    from ...config import Config, OpenCodeConfig
    from ...space import BaseSpace
    from ...mcp import MCPManager

logger = logging.getLogger(__name__)


class OpenCodeAgent(BaseAgent):
    """
    OpenCode agent implementation.

    Adapts OpenCode's HTTP/SSE API to the BaseAgent interface.
    Manages connection, server lifecycle, sessions, and streaming.
    
    Each space gets its own OpenCode server on a dedicated port, since
    OpenCode servers are bound to their working directory at startup.
    """

    def __init__(
        self,
        config: "OpenCodeConfig | None",
        working_dir: Path | str | None = None,
    ) -> None:
        """
        Initialize OpenCode agent.

        Args:
            config: OpenCode configuration
            working_dir: Working directory for OpenCode operations (deprecated, use set_space)
        """
        self._config_missing = False
        self._space: "BaseSpace | None" = None
        self._mcp_manager: "MCPManager | None" = None
        self._current_server: ServerInstance | None = None
        
        if config is None:
            self._config_missing = True
            return
        
        self.config = config
        
        # Server pool manages multiple OpenCode servers (one per space)
        self._server_pool = ServerPool(config)
        
        # Initialize managers with a placeholder URL (will be updated on connect)
        # Using base_port as default
        initial_url = f"http://{config.host}:{config.base_port}"
        
        self.connection = ConnectionManager(
            base_url=initial_url,
            timeout=config.timeout,
        )

        self.sessions = SessionManager(
            base_url=initial_url,
            timeout=config.timeout,
        )

        self.messages = MessageManager(
            base_url=initial_url,
            timeout=config.timeout,
        )

        self.streams = StreamManager(
            base_url=initial_url,
            timeout=config.timeout,
        )

        self._initialized = False

    def _update_managers_base_url(self, base_url: str) -> None:
        """Update all managers to use a new base URL."""
        logger.debug(f"Updating managers to use {base_url}")
        self.connection.base_url = base_url
        self.sessions.base_url = base_url
        self.messages.base_url = base_url
        self.streams.base_url = base_url

    @property
    def working_dir(self) -> Path | None:
        """Working directory for OpenCode operations."""
        if self._current_server:
            return self._current_server.working_dir
        return None

    @property
    def space(self) -> "BaseSpace | None":
        """Return the current space, or None if not set."""
        return self._space

    def set_space(self, space: "BaseSpace", mcp_manager: "MCPManager | None" = None) -> None:
        """
        Set the space this agent operates in.

        Updates the working directory to the space's root path (where opencode.json
        is located) and generates the opencode.json configuration file.
        
        Note: This does NOT start the server. Call initialize() after set_space()
        to start/connect to the appropriate server for this space.

        Args:
            space: The space to operate in
            mcp_manager: Optional MCP manager for resolving MCP server info
        """
        logger.info(f"Setting space to '{space.space_id}' for OpenCode agent")

        self._space = space
        self._mcp_manager = mcp_manager

        # Generate opencode.json in the space root
        self._write_opencode_json()

        logger.info(f"OpenCode agent configured for space '{space.space_id}'")
        logger.info(f"OpenCode working directory will be: {space.workspace_path}")

    def _write_opencode_json(self) -> None:
        """
        Generate opencode.json configuration file for the current space.

        Creates the configuration with:
        - Assistants from space config
        
        Note: MCP servers are NOT included here. They are registered dynamically
        via the POST /mcp API after connecting to the OpenCode server.
        """
        if self._space is None:
            logger.warning("Cannot write opencode.json: no space set")
            return

        space = self._space
        config = space.config

        # Build agents section from assistants
        agents_config: dict[str, Any] = {}
        default_agent: str | None = None

        for assistant in config.assistants:
            agent_config: dict[str, Any] = {
                "description": assistant.description,
                "mode": assistant.mode,
                "prompt": assistant.prompt,
                "tools": assistant.tools.copy(),
            }

            # Add MCP tool patterns for enabled MCPs
            for mcp_id in space.get_enabled_mcps():
                # Enable all tools from this MCP server
                agent_config["tools"][f"{mcp_id}_*"] = True

            agents_config[assistant.name] = agent_config

            # Track default agent
            if assistant.name == config.default_assistant:
                default_agent = assistant.name

        # If no default set, use first assistant
        if not default_agent and config.assistants:
            default_agent = config.assistants[0].name

        # Build final config (no MCP section - registered via API)
        opencode_config: dict[str, Any] = {
            "$schema": "https://opencode.ai/config.json",
            "model": "github-copilot/claude-opus-4.6",# gpt-5-mini", # TODO: temporary free model
        }

        if agents_config:
            opencode_config["agent"] = agents_config

        if default_agent:
            opencode_config["default_agent"] = default_agent

        # Write to space root
        opencode_json_path = space.path / "opencode.json"
        opencode_json_path.write_text(json.dumps(opencode_config, indent=2))
        logger.info(f"Wrote opencode.json to {opencode_json_path}")

        # Create symlink in workspace so OpenCode finds the config when running there
        workspace_link = space.workspace_path / "opencode.json"
        if workspace_link.is_symlink():
            workspace_link.unlink()
        elif workspace_link.exists():
            # Don't overwrite a real file in the user's repo
            logger.warning(
                f"opencode.json already exists in workspace at {workspace_link}, "
                "not creating symlink"
            )
            return
        
        try:
            workspace_link.symlink_to(opencode_json_path)
            logger.info(f"Created symlink {workspace_link} -> {opencode_json_path}")
        except OSError as e:
            logger.warning(f"Could not create opencode.json symlink in workspace: {e}")

    async def _register_mcp_servers(self) -> None:
        """
        Register all enabled MCP servers with the OpenCode server via API.

        This is called after connecting to ensure MCP servers are available
        regardless of when the server was started or whether opencode.json
        was present at startup time.

        MCPs that are already registered and connected are skipped.
        Failures are logged but don't prevent other MCPs from being registered.
        """
        if not self._space or not self._mcp_manager:
            logger.debug("No space or MCP manager, skipping MCP registration")
            return

        enabled_mcps = self._space.get_enabled_mcps()
        if not enabled_mcps:
            logger.debug("No enabled MCPs for this space")
            return

        # Get currently registered MCPs to avoid duplicates
        try:
            current_mcps = await self.connection.get_mcp_servers()
        except Exception as e:
            logger.warning(f"Failed to get current MCP servers: {e}")
            current_mcps = {}

        for mcp_id in enabled_mcps:
            # Skip if already registered and connected
            if mcp_id in current_mcps:
                status = current_mcps[mcp_id].get("status")
                if status == "connected":
                    logger.debug(f"MCP '{mcp_id}' already registered and connected")
                    continue
                # If it exists but isn't connected, we'll try to re-register
                logger.info(f"MCP '{mcp_id}' exists but status is '{status}', re-registering")

            # Get MCP server info from our registry
            info = self._mcp_manager.get_server(mcp_id)
            if not info:
                logger.warning(f"MCP server '{mcp_id}' not found in registry, skipping")
                continue

            # Build config and register
            config = info.get_opencode_config(enabled=True)
            try:
                result = await self.connection.register_mcp_server(mcp_id, config)
                status = result.get("status", "unknown")
                logger.info(f"Registered MCP server '{mcp_id}': status={status}")
            except Exception as e:
                logger.error(f"Failed to register MCP server '{mcp_id}': {e}")
                # Continue with other MCPs - don't fail the whole initialization

    # ========== BaseAgent Implementation ==========

    async def initialize(self) -> None:
        """
        Initialize the agent.

        Gets or starts an OpenCode server for the current space.
        Each space has its own server on a dedicated port.

        Raises:
            AgentInitializationError: If initialization fails
        """
        if self._initialized:
            # If already initialized, check if we need to switch servers (space changed)
            if self._space and self._current_server:
                expected_dir = Path(self._space.workspace_path).resolve()
                current_dir = self._current_server.working_dir
                
                if expected_dir != current_dir:
                    logger.info(
                        f"Space changed from {current_dir} to {expected_dir}, "
                        "reconnecting to appropriate server..."
                    )
                    self._initialized = False
                else:
                    return
            else:
                return

        logger.info("Initializing OpenCode agent...")
        
        if self._config_missing:
            raise AgentInitializationError("Config invalid")

        if self._space is None:
            raise AgentInitializationError(
                "No space set. Call set_space() before initialize()."
            )

        try:
            # Get or start server for this space
            # Use workspace_path (the actual project directory) so the agent has
            # access to .git and other project files. opencode.json is symlinked there.
            server = self._server_pool.get_or_start_server(
                space_id=self._space.space_id,
                working_dir=self._space.workspace_path,
                timeout=self.config.timeout,
            )
            
            self._current_server = server
            
            # Update all managers to point to this server
            self._update_managers_base_url(server.base_url)

            logger.info(f"Connected to OpenCode server at {server.base_url}")
            logger.info(f"Server version: {self.connection.get_server_version()}")
            
            # Log the actual project path for debugging
            project_path = self.connection.get_current_project_path()
            if project_path:
                logger.info(f"OpenCode project path: {project_path}")
            
            self._initialized = True

            # Register MCP servers dynamically via API
            # This ensures MCPs are available regardless of when server started
            await self._register_mcp_servers()

        except OpenCodeNotInstalledError as e:
            raise AgentInitializationError(str(e)) from e
        except OpenCodeConnectionError as e:
            raise AgentInitializationError(str(e)) from e
        except RuntimeError as e:
            raise AgentInitializationError(str(e)) from e

    async def shutdown(self) -> None:
        """
        Shutdown the agent and clean up resources.

        Closes HTTP clients. Does NOT stop servers in the pool (they may be
        reused). Use shutdown_all() to stop all servers.
        """
        logger.info("Shutting down OpenCode agent...")

        self.connection.close()
        self.sessions.close()
        self.messages.close()
        
        self._current_server = None
        self._initialized = False
        logger.info("OpenCode agent shutdown complete")

    def shutdown_all_servers(self) -> None:
        """Stop all OpenCode servers in the pool."""
        self._server_pool.stop_all()

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

    def get_server_pool_stats(self) -> dict:
        """Get statistics about the server pool."""
        return self._server_pool.get_stats()

    @staticmethod
    def is_opencode_installed() -> bool:
        """Check if OpenCode CLI is installed."""
        return shutil.which("opencode") is not None

    @staticmethod
    def get_opencode_version() -> str | None:
        """Get installed OpenCode CLI version."""
        return ServerManager.get_opencode_version()


class OpenCodeAgentFactory(BaseAgentFactory):
    """Factory for creating OpenCode agent instances."""

    def create_agent(self, config: "Config") -> BaseAgent:
        """Create an OpenCode agent instance.

        Args:
            config: the full application `Config`
        
        Note:
            The working directory is intentionally not set here.
            It will be configured via set_space() before initialize()
            is called, ensuring the OpenCode server starts in the
            correct space directory.
        """

        opencode_cfg = getattr(getattr(config, "agent", None), "opencode", None)
        # Don't set working_dir here - it will be set by set_space() before initialize()
        return OpenCodeAgent(opencode_cfg, working_dir=None)

    def agent_type(self) -> str:
        """Return the agent type this factory creates."""
        return "opencode"
