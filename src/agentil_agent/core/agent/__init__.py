"""
Agent abstraction and implementations.

Provides a common interface for different agent backends (OpenCode, LangChain, etc.)
"""

from typing import Any

from .base import BaseAgent, BaseAgentFactory, AgentCapabilities
from .types import (
    AgentSession,
    AgentMessage,
    AgentResponse,
    AgentStreamChunk,
    AgentConfig,
)
from .exceptions import (
    AgentError,
    AgentNotReadyError,
    AgentInitializationError,
    AgentSessionError,
    AgentTimeoutError,
    AgentAbortError,
    AgentConfigurationError,
    AgentAuthenticationError,
    AgentRateLimitError,
    AgentModelError,
    AgentStreamError,
    AgentNotSupportedError,
)

# Registry for agent factories
_agent_factories: dict[str, BaseAgentFactory] = {}


def register_agent_factory(factory: BaseAgentFactory) -> None:
    """
    Register an agent factory.
    
    Args:
        factory: Factory instance that creates agents
    """
    _agent_factories[factory.agent_type()] = factory


def create_agent(agent_type: str, config: Any) -> BaseAgent:
    """
    Create an agent of the specified type.
    
    Args:
        agent_type: Type of agent to create (e.g., "opencode", "langchain")
        config: Configuration object for the agent
        
    Returns:
        Configured agent instance
        
    Raises:
        ValueError: If agent_type is not registered
    """
    factory = _agent_factories.get(agent_type)
    if not factory:
        available = ", ".join(_agent_factories.keys())
        raise ValueError(
            f"Unknown agent type: {agent_type}. "
            f"Available types: {available or 'none'}"
        )
    return factory.create_agent(config)


def list_available_agents() -> list[str]:
    """
    List all registered agent types.
    
    Returns:
        List of agent type strings
    """
    return list(_agent_factories.keys())


# Auto-register available agents
try:
    from .opencode import OpenCodeAgentFactory
    register_agent_factory(OpenCodeAgentFactory())
except ImportError:
    pass

try:
    from .langchain import LangChainAgentFactory
    register_agent_factory(LangChainAgentFactory())
except ImportError:
    pass

try:
    from .mock import MockAgentFactory
    register_agent_factory(MockAgentFactory())
except ImportError:
    pass


__all__ = [
    # Base classes
    "BaseAgent",
    "AgentCapabilities",
    # Factory functions
    "create_agent",
    "list_available_agents",
    # Types
    "AgentSession",
    "AgentMessage",
    "AgentResponse",
    "AgentStreamChunk",
    "AgentConfig",
    # Exceptions
    "AgentError",
    "AgentNotReadyError",
    "AgentInitializationError",
    "AgentSessionError",
    "AgentTimeoutError",
    "AgentAbortError",
    "AgentConfigurationError",
    "AgentAuthenticationError",
    "AgentRateLimitError",
    "AgentModelError",
    "AgentStreamError",
    "AgentNotSupportedError",
]
