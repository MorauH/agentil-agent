"""
Base space interface.

Defines the abstract interface that all space implementations must follow,
enabling dependency injection and pluggable space backends.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import SpaceConfig


class BaseSpace(ABC):
    """
    Abstract base class for all space implementations.

    A Space represents an isolated project environment where:
    - Sessions operate within a defined working directory
    - MCP servers can be enabled/disabled
    - Agent configurations (assistants) are defined
    
    Defines the interface that all spaces must implement,
    regardless of their underlying technology (local directory, 
    docker container, nix-jail, etc.).

    All methods that interact with the space should be async (or return async
    generators) to support non-blocking I/O and better concurrency.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the space.

        This is called once before the space is first used. Implementations
        should perform any necessary setup here:
        - Create directory structure
        - Load configuration
        - Start processes
        - Create docker container

        Raises:
            SpaceInitializationError: If initialization fails
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

    @property
    @abstractmethod
    def space_id(self) -> str:
        """
        Return the unique identifier for this space instance.

        Returns:
            Space identifier (e.g., "my-project", "default")
        """
        pass

    @property
    @abstractmethod
    def path(self) -> Path:
        """
        Return the root path of this space.

        This is the directory containing space configuration files
        (space.toml, opencode.json, etc.).

        Returns:
            Path to space root directory
        """
        pass

    @property
    @abstractmethod
    def workspace_path(self) -> Path:
        """
        Return the working directory where the agent operates.

        This is typically a subdirectory of the space root (e.g., workspace/)
        where the agent can read/write files safely.

        Returns:
            Path to agent working directory
        """
        pass

    @property
    @abstractmethod
    def config(self) -> "SpaceConfig":
        """
        Return the space configuration.

        Contains assistants, enabled MCP servers, and other settings.

        Returns:
            SpaceConfig instance
        """
        pass

    @abstractmethod
    def get_enabled_mcps(self) -> list[str]:
        """
        Get list of MCP server IDs enabled for this space.

        Returns:
            List of MCP server identifiers
        """
        pass

    @abstractmethod
    def set_enabled_mcps(self, mcp_ids: list[str]) -> None:
        """
        Update which MCP servers are enabled for this space.

        Args:
            mcp_ids: List of MCP server identifiers to enable
        """
        pass

    @abstractmethod
    def save_config(self) -> None:
        """
        Persist the current space configuration to disk.
        
        Should be called after modifying config or enabled MCPs.
        """
        pass

    @property
    def is_initialized(self) -> bool:
        """
        Check if the space has been initialized.

        Returns:
            True if initialize() has been called successfully
        """
        return False  # Subclasses should override

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
    Abstract factory for creating space instances.

    Factories allow for:
    - Late initialization
    - Configuration-based creation
    - Registration and discovery
    - Dependency injection
    """

    @abstractmethod
    def create_space(self, spaces_root: Path, space_id: str, **kwargs) -> BaseSpace:
        """
        Create and return a configured space instance.

        Args:
            spaces_root: Root directory where spaces are stored
            space_id: Unique identifier for the space
                - Used as directory name for DirectorySpace
                - Used as container name for Docker
                - etc.
            **kwargs: Additional factory-specific arguments
                (e.g., workspace_link for directory spaces)

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
            Space type identifier (e.g., "directory", "nix-jail", "docker")
        """
        pass


class SpaceCapabilities:
    """
    Optional mixin for spaces that want to declare capabilities.

    Not all spaces support all features. This allows spaces to
    declare what they can and cannot do.
    """

    def supports_isolation(self) -> bool:
        """Whether space provides file system isolation."""
        return False

    def supports_network_isolation(self) -> bool:
        """Whether space provides network isolation."""
        return False

    def supports_resource_limits(self) -> bool:
        """Whether space supports CPU/memory limits."""
        return False

