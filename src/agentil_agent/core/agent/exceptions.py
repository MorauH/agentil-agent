"""
Exception types for agent implementations.

Provides a hierarchy of exceptions that all agents should use,
enabling consistent error handling across different backends.
"""


class AgentError(Exception):
    """
    Base exception for all agent errors.

    All agent-specific exceptions should inherit from this,
    allowing callers to catch all agent errors with a single except clause.
    """

    pass


class AgentNotReadyError(AgentError):
    """
    Agent is not ready to handle requests.

    Raised when attempting to use an agent that hasn't been initialized,
    or that has been shut down.

    Example:
        agent = OpenCodeAgent(config)
        # Forgot to call await agent.initialize()
        await agent.send_message(...)  # Raises AgentNotReadyError
    """

    pass


class AgentInitializationError(AgentError):
    """
    Agent failed to initialize.

    Raised when agent.initialize() fails due to:
    - Connection errors
    - Missing dependencies
    - Configuration problems
    - Authentication failures

    Example:
        agent = OpenCodeAgent(config)
        await agent.initialize()  # Server not running -> AgentInitializationError
    """

    pass


class AgentSessionError(AgentError):
    """
    Session-related error.

    Raised when operations on a session fail:
    - Session not found
    - Session in invalid state
    - Session creation failed
    - Session deletion failed

    Example:
        await agent.send_message("invalid_session_id", "Hello")
        # Raises AgentSessionError: Session not found
    """

    pass


class AgentTimeoutError(AgentError):
    """
    Operation timed out.

    Raised when an agent operation takes too long:
    - Response generation timeout
    - Connection timeout
    - Streaming timeout

    Example:
        async for chunk in agent.stream_response(...):
            # If no chunks arrive for too long -> AgentTimeoutError
    """

    pass


class AgentAbortError(AgentError):
    """
    Operation was aborted.

    Raised when an operation is cancelled/aborted:
    - User requested abort
    - Session was aborted
    - Streaming was cancelled

    Example:
        await agent.abort_session(session_id)
        # Any in-progress operations raise AgentAbortError
    """

    pass


class AgentConfigurationError(AgentError):
    """
    Invalid agent configuration.

    Raised when agent configuration is invalid:
    - Missing required parameters
    - Invalid parameter values
    - Incompatible settings

    Example:
        config = OpenCodeConfig(port=-1)  # Invalid port
        agent = OpenCodeAgent(config)
        await agent.initialize()  # Raises AgentConfigurationError
    """

    pass


class AgentAuthenticationError(AgentError):
    """
    Authentication or authorization failed.

    Raised when:
    - API key is invalid
    - Token expired
    - Insufficient permissions

    Example:
        agent = ClaudeAgent(api_key="invalid")
        await agent.initialize()  # Raises AgentAuthenticationError
    """

    pass


class AgentRateLimitError(AgentError):
    """
    Rate limit exceeded.

    Raised when too many requests are made:
    - API rate limit hit
    - Quota exceeded
    - Throttling active

    Example:
        for i in range(1000):
            await agent.send_message(...)  # Eventually AgentRateLimitError
    """

    pass


class AgentModelError(AgentError):
    """
    Model-related error.

    Raised when:
    - Model not found
    - Model not supported
    - Model failed to load

    Example:
        await agent.send_message(
            session_id,
            "Hello",
            model="nonexistent-model"
        )  # Raises AgentModelError
    """

    pass


class AgentStreamError(AgentError):
    """
    Streaming-related error.

    Raised when streaming fails:
    - Stream interrupted
    - Invalid stream data
    - Stream parsing error

    Example:
        async for chunk in agent.stream_response(...):
            # Connection drops -> AgentStreamError
    """

    pass


class AgentNotSupportedError(AgentError):
    """
    Feature not supported by this agent.

    Raised when attempting to use a feature the agent doesn't support:
    - Streaming (if not supported)
    - Abort (if not supported)
    - File upload (if not supported)
    - Tool use (if not supported)

    Example:
        if not agent.supports_abort():
            raise AgentNotSupportedError("Abort not supported")
    """

    pass


# Convenience type for catching any agent error
AgentException = AgentError
