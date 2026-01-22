"""
OpenCode-specific exception types.

These exceptions are specific to OpenCode implementation details.
They are wrapped by BaseAgent exceptions when exposed through the agent interface.
"""

from ..exceptions import (
    AgentError,
    AgentInitializationError,
    AgentSessionError,
    AgentTimeoutError,
)


class OpenCodeError(AgentError):
    """
    Base exception for OpenCode-specific errors.
    
    Inherits from AgentError so it can be caught by general agent error handlers.
    """

    pass


class OpenCodeConnectionError(OpenCodeError, AgentInitializationError):
    """
    Connection to OpenCode server failed.
    
    Inherits from both OpenCodeError (for OpenCode-specific handling)
    and AgentInitializationError (for standard agent error handling).
    """

    pass


class OpenCodeNotInstalledError(OpenCodeError, AgentInitializationError):
    """
    OpenCode CLI is not installed.
    
    Inherits from both OpenCodeError and AgentInitializationError.
    """

    pass


class OpenCodeTimeoutError(OpenCodeError, AgentTimeoutError):
    """
    OpenCode operation timed out.
    
    Inherits from both OpenCodeError and AgentTimeoutError.
    """

    pass


class OpenCodeSessionError(OpenCodeError, AgentSessionError):
    """
    OpenCode session-related error.
    
    Inherits from both OpenCodeError and AgentSessionError.
    """

    pass
