"""
Base agent interface.

Defines the abstract interface that all agent implementations must follow,
enabling dependency injection and pluggable agent backends.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from .types import AgentSession, AgentResponse

if TYPE_CHECKING:
    from ..space import BaseSpace
    from ..mcp import MCPManager


class BaseAgent(ABC):
    """
    Abstract base class for all agent implementations.

    Defines the interface that all agents must implement,
    regardless of their underlying technology (OpenCode, LangChain,
    Claude API, local models, etc.).

    All methods that interact with the agent should be async (or return async
    generators) to support non-blocking I/O and better concurrency.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the agent.

        This is called once before the agent is first used. Implementations
        should perform any necessary setup here:
        - Connect to servers
        - Start processes
        - Load models
        - Authenticate with APIs
        - Allocate resources

        Raises:
            AgentError: If initialization fails
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean shutdown of agent resources.

        This is called when the agent is no longer needed. Implementations
        should clean up all resources:
        - Close connections
        - Stop processes
        - Free memory
        - Save state if needed

        This method should be idempotent - calling it multiple times
        should be safe.
        """
        pass

    @abstractmethod
    def set_space(self, space: "BaseSpace", mcp_manager: "MCPManager | None" = None) -> None:
        """
        Set the space this agent operates in.

        This is the primary dependency injection point for spaces. Agent
        implementations should:
        - Update their working directory appropriately (space.path for project
          root where config files live, or space.workspace_path for isolated
          file operations)
        - Create any agent-specific config files (e.g., opencode.json)
        - Configure MCP servers based on space.get_enabled_mcps()

        This may be called multiple times to switch spaces without
        restarting the agent.

        Args:
            space: The space to operate in
            mcp_manager: Optional MCP manager for resolving MCP server info
        """
        pass

    @property
    @abstractmethod
    def space(self) -> "BaseSpace | None":
        """
        Return the current space, or None if not set.

        Returns:
            Current BaseSpace instance or None
        """
        pass

    @abstractmethod
    async def create_session(self, title: str | None = None) -> AgentSession:
        """
        Create a new conversation session.

        A session represents an isolated conversation context with its own
        history and state. Different agents may implement sessions differently:
        - OpenCode: HTTP session with file context
        - LangChain: Conversation chain with memory
        - Claude API: Conversation ID
        - Local: In-memory conversation history

        Args:
            title: Optional human-readable title for the session

        Returns:
            AgentSession with unique ID and metadata

        Raises:
            AgentError: If session creation fails
            AgentNotReadyError: If agent is not initialized
        """
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and its associated data.

        Args:
            session_id: ID of session to delete

        Returns:
            True if session was deleted, False if it didn't exist

        Raises:
            AgentError: If deletion fails
        """
        pass

    @abstractmethod
    async def send_message(
        self,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Send a message and get complete response (non-streaming).

        This method blocks until the full response is ready. Use this when:
        - You need the complete response before proceeding
        - Streaming is not required
        - Simple request-response pattern is sufficient

        Args:
            session_id: Session ID to send message in
            text: Message text to send
            **kwargs: Agent-specific additional arguments (e.g., model, temperature)

        Returns:
            AgentResponse with complete text and metadata

        Raises:
            AgentError: If message sending fails
            AgentSessionError: If session doesn't exist
            AgentNotReadyError: If agent is not initialized
        """
        pass

    @abstractmethod
    def stream_response(
        self,
        session_id: str,
        text: str,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Send a message and stream response incrementally.

        This method yields text chunks as they become available. Use this when:
        - You want to show progress to users
        - Response may be long
        - Lower latency to first token is important

        The yielded chunks should be incremental deltas, not cumulative text.
        For example:
        - First yield: "Hello"
        - Second yield: " world"
        - NOT: "Hello" then "Hello world"

        Args:
            session_id: Session ID to send message in
            text: Message text to send
            **kwargs: Agent-specific additional arguments

        Yields:
            Text deltas (incremental chunks, not cumulative)

        Raises:
            AgentError: If streaming fails
            AgentSessionError: If session doesn't exist
            AgentNotReadyError: If agent is not initialized
        """
        pass

    @abstractmethod
    async def abort_session(self, session_id: str) -> bool:
        """
        Abort/cancel ongoing processing in a session.

        This should stop any in-progress message generation and return
        the session to an idle state. Not all agents may support this.

        Args:
            session_id: Session ID to abort

        Returns:
            True if abort was successful, False if not supported or failed

        Raises:
            AgentError: If abort operation fails critically
        """
        pass

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if agent is ready to handle requests.

        Returns:
            True if agent is initialized and ready, False otherwise

        This should be a fast check that doesn't perform I/O.
        """
        pass

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """
        Return the type/name of this agent implementation.

        Returns:
            Agent type identifier (e.g., "opencode", "langchain", "claude")

        This is used for logging, debugging, and agent selection.
        """
        pass

    # Optional context manager support
    async def __aenter__(self) -> "BaseAgent":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.shutdown()


class BaseAgentFactory(ABC):
    """
    Abstract factory for creating agent instances.

    Factories allow for:
    - Late initialization
    - Configuration-based creation
    - Registration and discovery
    - Dependency injection
    """

    @abstractmethod
    def create_agent(self, config: Any) -> BaseAgent:
        """
        Create and return a configured agent instance.

        Args:
            config: Configuration object specific to this agent type

        Returns:
            Configured agent instance (not yet initialized)

        Raises:
            AgentError: If agent creation fails
        """
        pass

    @abstractmethod
    def agent_type(self) -> str:
        """
        Return the agent type this factory creates.

        Returns:
            Agent type identifier (e.g., "opencode", "langchain")
        """
        pass


class AgentCapabilities:
    """
    Optional mixin for agents that want to declare capabilities.

    Not all agents support all features. This allows agents to
    declare what they can and cannot do.
    """

    def supports_streaming(self) -> bool:
        """Whether agent supports streaming responses."""
        return True

    def supports_abort(self) -> bool:
        """Whether agent supports aborting sessions."""
        return False

    def supports_tool_use(self) -> bool:
        """Whether agent supports tool/function calling."""
        return False

    def supports_file_upload(self) -> bool:
        """Whether agent supports file uploads."""
        return False

    def supports_multimodal(self) -> bool:
        """Whether agent supports images/audio input."""
        return False

    def max_context_length(self) -> int | None:
        """Maximum context length in tokens, or None if unlimited/unknown."""
        return None

    def supported_models(self) -> list[str]:
        """List of supported model identifiers."""
        return []
