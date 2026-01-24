"""
Base space interface.

Defines the abstract interface that all space implementations must follow,
enabling dependency injection and pluggable space backends.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any


class BaseSpace(ABC):
    """
    Abstract base class for all space implementations.

    Defines the interface that all spaces must implement,
    regardless of their underlying technology 

    All methods that interact with the space should be async (or return async
    generators) to support non-blocking I/O and better concurrency.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the space.

        This is called once before the space is first used. Implementations
        should perform any necessary setup here:
        - Create directory
        - Start processes
        - Create docker container

        Raises:
            SpaceError: If initialization fails
        """
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Clean shutdown of space resources.

        This is called when the space is no longer needed. Implementations
        should clean up all resources:
        - Close connections
        - Stop processes
        - Free memory
        - Save state if needed

        This method should be idempotent - calling it multiple times
        should be safe.
        """
        pass

    @property
    @abstractmethod
    def space_type(self) -> str:
        """
        Return the type/name of this space implementation.

        Returns:
            Space type identifier (e.g., "directory", "docker")

        This is used for logging, debugging, and space selection.
        """
        pass

    # Optional context manager support
    async def __aenter__(self) -> "BaseSpace":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.shutdown()


class BaseSpaceFactory(ABC):
    """
    Abstract factory for creating spcae instances.

    Factories allow for:
    - Late initialization
    - Configuration-based creation
    - Registration and discovery
    - Dependency injection
    """

    @abstractmethod
    def create_space(self, config: Any, identifier: str) -> BaseSpace:
        """
        Create and return a configured space instance.

        Args:
            config: Full app config
            identifier: Identifier for space type
                - Path relative workspace for DirectorySpace
                - Path relative workspace for nix-jail
                - Name for docker

        Returns:
            Configured space instance (not yet initialized)

        Raises:
            SpaceError: If space creation fails
        """
        pass

    @abstractmethod
    def space_type(self) -> str:
        """
        Return the space type this factory creates.

        Returns:
            Agent type identifier (e.g., "directory", "nix-jail", "docker")
        """
        pass


class SpaceCapabilities:
    """
    Optional mixin for spaces that want to declare capabilities.

    Not all spaces support all features. This allows spaces to
    declare what they can and cannot do.
    """

    # TODO: May be relevant later if have different space-implementations

