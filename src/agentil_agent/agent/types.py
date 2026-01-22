"""
Common types for agent implementations.

These types provide a standardized interface across all agent backends,
ensuring compatibility and ease of switching between implementations.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentSession:
    """
    Generic session representation across all agents.

    A session represents an isolated conversation context. Different
    agent implementations may store different metadata, but all sessions
    have at minimum an ID.
    """

    id: str
    """Unique session identifier."""

    title: str | None = None
    """Optional human-readable title."""

    created_at: str | None = None
    """ISO timestamp of when session was created."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Agent-specific metadata.
    
    Examples:
    - OpenCode: {"opencode_session": Session(...), "directory": "/path"}
    - LangChain: {"chain": ConversationChain(...), "memory": Memory(...)}
    - Claude: {"conversation_id": "...", "model": "claude-3"}
    """

    def __repr__(self) -> str:
        """String representation."""
        title_str = f", title='{self.title}'" if self.title else ""
        return f"AgentSession(id='{self.id}'{title_str})"


@dataclass
class AgentMessage:
    """
    Generic message representation.

    Represents a single message in a conversation, from either the user
    or the assistant.
    """

    id: str
    """Unique message identifier."""

    role: str
    """Message role: "user" or "assistant"."""

    text: str
    """Message text content."""

    session_id: str
    """ID of session this message belongs to."""

    created_at: str | None = None
    """ISO timestamp of when message was created."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Agent-specific metadata.
    
    Examples:
    - Model used
    - Token counts
    - Processing time
    - Tool calls made
    - Attachments
    """

    def __repr__(self) -> str:
        """String representation."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"AgentMessage(id='{self.id}', role='{self.role}', text='{text_preview}')"


@dataclass
class AgentResponse:
    """
    Response from agent (non-streaming).

    Represents a complete response from the agent after processing
    a user message.
    """

    text: str
    """Complete response text."""

    message_id: str | None = None
    """ID of the created message, if available."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Agent-specific metadata.
    
    Examples:
    - model_id: Model used for generation
    - provider_id: Provider (e.g., "openai", "anthropic")
    - tokens: Token usage statistics
    - finish_reason: Why generation stopped
    - tool_calls: Tools/functions called
    - raw_response: Original response from agent
    """

    def __repr__(self) -> str:
        """String representation."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        msg_id = f", message_id='{self.message_id}'" if self.message_id else ""
        return f"AgentResponse(text='{text_preview}'{msg_id})"

    @property
    def model(self) -> str | None:
        """Get model ID from metadata if available."""
        return self.metadata.get("model_id")

    @property
    def provider(self) -> str | None:
        """Get provider ID from metadata if available."""
        return self.metadata.get("provider_id")

    @property
    def tokens(self) -> dict[str, Any] | None:
        """Get token usage from metadata if available."""
        return self.metadata.get("tokens")

    @property
    def finish_reason(self) -> str | None:
        """Get finish reason from metadata if available."""
        return self.metadata.get("finish_reason")


@dataclass
class AgentStreamChunk:
    """
    Single chunk from a streaming response.

    Used for advanced streaming scenarios where metadata is needed
    along with text deltas.
    """

    delta: str
    """Incremental text (new text only, not cumulative)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """
    Optional metadata for this chunk.
    
    Examples:
    - chunk_index: Position in stream
    - timestamp: When chunk was generated
    - is_final: Whether this is the last chunk
    """

    def __repr__(self) -> str:
        """String representation."""
        delta_preview = self.delta[:30] + "..." if len(self.delta) > 30 else self.delta
        return f"AgentStreamChunk(delta='{delta_preview}')"


@dataclass
class AgentCapabilitiesInfo:
    """
    Information about agent capabilities.

    Used to describe what features an agent supports.
    """

    agent_type: str
    """Agent type identifier."""

    supports_streaming: bool = True
    """Whether agent supports streaming responses."""

    supports_abort: bool = False
    """Whether agent supports aborting sessions."""

    supports_tool_use: bool = False
    """Whether agent supports tool/function calling."""

    supports_file_upload: bool = False
    """Whether agent supports file uploads."""

    supports_multimodal: bool = False
    """Whether agent supports images/audio input."""

    max_context_length: int | None = None
    """Maximum context length in tokens, or None if unlimited/unknown."""

    supported_models: list[str] = field(default_factory=list)
    """List of supported model identifiers."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional agent-specific capability information."""

    def __repr__(self) -> str:
        """String representation."""
        return f"AgentCapabilities(agent_type='{self.agent_type}')"


@dataclass
class AgentConfig:
    """
    Base configuration for agents.

    Specific agent implementations should subclass this and add
    their own configuration fields.
    """

    agent_type: str
    """Type of agent (e.g., "opencode", "langchain")."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional configuration parameters specific to the agent."""

    def __repr__(self) -> str:
        """String representation."""
        return f"AgentConfig(agent_type='{self.agent_type}')"
