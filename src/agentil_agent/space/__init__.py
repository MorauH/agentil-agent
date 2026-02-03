"""
Space configuration and interface

Provides a common interface for different space backends (Local directory, docker container, etc.)
"""

from typing import Any

from .base import BaseSpace, BaseSpaceFactory, SpaceCapabilities

from .config import SpaceConfig

from .exceptions import (
    SpaceError,
    SpaceNotReadyError,
    SpaceInitializationError,
)

_space_factories: dict[str, BaseSpaceFactory] = {}

def register_space_factory(factory: BaseSpaceFactory) -> None:
    """
    Register an space factory.
    
    Args:
        factory: Factory instance that creates spaces
    """
    _space_factories[factory.space_type()] = factory


def create_space(space_type: str, config: Any) -> BaseSpace:
    """
    Create an space of the specified type.
    
    Args:
        space_type: Type of space to create (e.g., "nix-jail", "docker")
        config: Configuration object for the space
        
    Returns:
        Configured space instance
        
    Raises:
        ValueError: If space_type is not registered
    """
    factory = _space_factories.get(space_type)
    if not factory:
        available = ", ".join(_space_factories.keys())
        raise ValueError(
            f"Unknown space type: {space_type}. "
            f"Available types: {available or 'none'}"
        )
    return factory.create_space(config)


def list_available_spaces() -> list[str]:
    """
    List all registered space types.
    
    Returns:
        List of space type strings
    """
    return list(_space_factories.keys())


# Auto-register available spaces
try:
    from .directory import DirectorySpaceFactory
    register_space_factory(DirectorySpaceFactory())
except ImportError:
    pass

try:
    from .nix-jail import NixJailSpaceFactory
    register_space_factory(NixJailSpaceFactory())
except ImportError:
    pass

try:
    from .docker import DockerSpaceFactory
    register_space_factory(DockerSpaceFactory())
except ImportError:
    pass


__all__ = [
    # Base classes
    "BaseSpace",
    "BaseSpaceFactory",
    "SpaceCapabilities",
    # Types
    #"SpaceSession",
    #"SpaceMessage",
    #"SpaceResponse",
    #"SpaceStreamChunk",
    #"SpaceCapabilitiesInfo",
    #"SpaceConfig",
    # Exceptions
    "SpaceError",
    "SpaceNotReadyError",
    "SpaceInitializationError",
    # Factory functions
    "create_space",
    "register_space_factory",
    "list_available_spaces",
    # Configuration
    "SpaceConfig"
]
