"""
Space configuration and interface.

Provides a common interface for different space backends 
(local directory, docker container, nix-jail, etc.).
"""

from pathlib import Path

from .base import BaseSpace, BaseSpaceFactory, SpaceCapabilities
from .config import SpaceConfig, AssistantConfig
from .exceptions import (
    SpaceError,
    SpaceNotReadyError,
    SpaceInitializationError,
)
from .manager import SpaceManager, SpaceInfo

# =============================================================================
# Space Factory Registry
# =============================================================================

_space_factories: dict[str, BaseSpaceFactory] = {}


def register_space_factory(factory: BaseSpaceFactory) -> None:
    """
    Register a space factory.

    Args:
        factory: Factory instance that creates spaces
    """
    _space_factories[factory.space_type()] = factory


def create_space(space_type: str, spaces_root: Path, space_id: str, **kwargs) -> BaseSpace:
    """
    Create a space of the specified type.

    Args:
        space_type: Type of space to create (e.g., "directory", "docker")
        spaces_root: Root directory where spaces are stored
        space_id: Unique identifier for the space
        **kwargs: Additional arguments passed to the space factory
            (e.g., workspace_link for directory spaces)

    Returns:
        Configured space instance (not yet initialized)

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
    return factory.create_space(spaces_root, space_id, **kwargs)


def list_available_space_types() -> list[str]:
    """
    List all registered space types.

    Returns:
        List of space type strings
    """
    return list(_space_factories.keys())


# =============================================================================
# Auto-register Available Space Types
# =============================================================================

# Directory space (local filesystem)
try:
    from .directory import DirectorySpaceFactory

    register_space_factory(DirectorySpaceFactory())
except ImportError:
    pass

# Nix-jail space (future)
# try:
#     from .nix_jail import NixJailSpaceFactory
#     register_space_factory(NixJailSpaceFactory())
# except ImportError:
#     pass

# Docker space (future)
# try:
#     from .docker import DockerSpaceFactory
#     register_space_factory(DockerSpaceFactory())
# except ImportError:
#     pass


# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Base classes
    "BaseSpace",
    "SpaceCapabilities",
    # Factory functions
    "create_space",
    "list_available_space_types",
    # Configuration
    "SpaceConfig",
    "AssistantConfig",
    # Manager
    "SpaceManager",
    "SpaceInfo",
    # Exceptions
    "SpaceError",
    "SpaceNotReadyError",
    "SpaceInitializationError",
]
