"""
Space manager for managing multiple spaces.

Handles space creation, persistence, discovery, and lifecycle management.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import BaseSpace
from .config import SpaceConfig
from .exceptions import SpaceError, SpaceInitializationError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default space ID
DEFAULT_SPACE_ID = "default"

# Registry filename
SPACES_REGISTRY_FILENAME = "spaces.json"


class SpaceInfo:
    """Information about a registered space."""

    def __init__(
        self,
        space_id: str,
        space_type: str,
        name: str,
        description: str | None = None,
        path: str | None = None,
    ) -> None:
        self.space_id = space_id
        self.space_type = space_type
        self.name = name
        self.description = description
        self.path = path

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "space_id": self.space_id,
            "space_type": self.space_type,
            "name": self.name,
            "description": self.description,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpaceInfo":
        """Create from dictionary."""
        return cls(
            space_id=data["space_id"],
            space_type=data["space_type"],
            name=data["name"],
            description=data.get("description"),
            path=data.get("path"),
        )


class SpaceManager:
    """
    Manages multiple spaces for the application.

    Responsibilities:
    - Create and initialize spaces
    - Persist space registry
    - Discover existing spaces
    - Track active space
    - Provide default space
    """

    def __init__(
        self,
        spaces_root: Path,
        default_space_type: str = "directory",
    ) -> None:
        """
        Initialize the space manager.

        Args:
            spaces_root: Root directory where spaces are stored
            default_space_type: Default type for new spaces
        """
        self._spaces_root = spaces_root
        self._default_space_type = default_space_type
        self._registry: dict[str, SpaceInfo] = {}
        self._active_spaces: dict[str, BaseSpace] = {}  # space_id -> initialized space
        self._initialized = False

    @property
    def spaces_root(self) -> Path:
        """Root directory where spaces are stored."""
        return self._spaces_root

    @property
    def registry_path(self) -> Path:
        """Path to the spaces registry file."""
        return self._spaces_root / SPACES_REGISTRY_FILENAME

    async def initialize(self) -> None:
        """
        Initialize the space manager.

        Creates the spaces root directory and loads the registry.
        """
        if self._initialized:
            return

        logger.info(f"Initializing space manager at {self._spaces_root}")

        # Create spaces root directory
        self._spaces_root.mkdir(parents=True, exist_ok=True)

        # Load existing registry
        self._load_registry()

        # Discover spaces from filesystem (in case registry is out of sync)
        self._discover_spaces()

        # Ensure default space exists
        if DEFAULT_SPACE_ID not in self._registry:
            await self.create_space(DEFAULT_SPACE_ID)

        self._initialized = True
        logger.info(
            f"Space manager initialized with {len(self._registry)} spaces"
        )

    async def shutdown(self) -> None:
        """Shutdown all active spaces and save registry."""
        logger.info("Shutting down space manager")

        # Shutdown all active spaces
        for space_id, space in list(self._active_spaces.items()):
            try:
                await space.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down space '{space_id}': {e}")

        self._active_spaces.clear()

        # Save registry
        self._save_registry()

        self._initialized = False
        logger.info("Space manager shutdown complete")

    def _load_registry(self) -> None:
        """Load space registry from disk."""
        if not self.registry_path.exists():
            self._registry = {}
            return

        try:
            with open(self.registry_path) as f:
                data = json.load(f)

            self._registry = {
                info["space_id"]: SpaceInfo.from_dict(info)
                for info in data.get("spaces", [])
            }
            logger.debug(f"Loaded {len(self._registry)} spaces from registry")

        except Exception as e:
            logger.warning(f"Failed to load spaces registry: {e}")
            self._registry = {}

    def _save_registry(self) -> None:
        """Save space registry to disk."""
        try:
            data = {
                "spaces": [info.to_dict() for info in self._registry.values()]
            }
            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self._registry)} spaces to registry")

        except Exception as e:
            logger.warning(f"Failed to save spaces registry: {e}")

    def _discover_spaces(self) -> None:
        """Discover spaces from filesystem not in registry."""
        if not self._spaces_root.exists():
            return

        for path in self._spaces_root.iterdir():
            if not path.is_dir():
                continue
            if path.name.startswith("."):
                continue
            if path.name == SPACES_REGISTRY_FILENAME.replace(".json", ""):
                continue

            space_id = path.name

            # Skip if already in registry
            if space_id in self._registry:
                continue

            # Check if it looks like a space (has space.toml or workspace dir)
            space_toml = path / "space.toml"
            workspace_dir = path / "workspace"

            if space_toml.exists() or workspace_dir.exists():
                # Load config to get name
                try:
                    config = SpaceConfig.load(path)
                    self._registry[space_id] = SpaceInfo(
                        space_id=space_id,
                        space_type="directory",
                        name=config.name,
                        description=config.description,
                        path=str(path),
                    )
                    logger.info(f"Discovered space '{space_id}' at {path}")
                except Exception as e:
                    logger.warning(f"Failed to load discovered space '{space_id}': {e}")

    def list_spaces(self) -> list[SpaceInfo]:
        """
        List all registered spaces.

        Returns:
            List of SpaceInfo objects
        """
        return list(self._registry.values())

    def get_space_info(self, space_id: str) -> SpaceInfo | None:
        """
        Get information about a space.

        Args:
            space_id: Space identifier

        Returns:
            SpaceInfo or None if not found
        """
        return self._registry.get(space_id)

    async def create_space(
        self,
        space_id: str,
        space_type: str | None = None,
        name: str | None = None,
        description: str | None = None,
        **kwargs,
    ) -> BaseSpace:
        """
        Create a new space.

        Args:
            space_id: Unique identifier for the space
            space_type: Type of space (default: directory)
            name: Human-readable name (default: space_id)
            description: Optional description
            **kwargs: Additional arguments passed to the space factory
                (e.g., workspace_link for directory spaces)

        Returns:
            Initialized BaseSpace instance

        Raises:
            SpaceError: If space already exists or creation fails
        """
        from . import create_space as factory_create_space

        if space_id in self._registry:
            raise SpaceError(f"Space '{space_id}' already exists")

        space_type = space_type or self._default_space_type
        name = name or space_id

        logger.info(f"Creating space '{space_id}' (type: {space_type})")

        # Create space using factory
        space = factory_create_space(space_type, self._spaces_root, space_id, **kwargs)

        # Initialize it
        await space.initialize()

        # Update config with provided name/description
        if name and name != space.config.name:
            space.config.name = name
        if description:
            space.config.description = description
        space.save_config()

        # Register it
        self._registry[space_id] = SpaceInfo(
            space_id=space_id,
            space_type=space_type,
            name=name,
            description=description,
            path=str(space.path),
        )
        self._save_registry()

        # Track as active
        self._active_spaces[space_id] = space

        logger.info(f"Created space '{space_id}' at {space.path}")
        return space

    async def get_space(self, space_id: str) -> BaseSpace:
        """
        Get an initialized space by ID.

        If the space is not currently active, it will be loaded and initialized.

        Args:
            space_id: Space identifier

        Returns:
            Initialized BaseSpace instance

        Raises:
            SpaceError: If space doesn't exist
        """
        from . import create_space as factory_create_space

        # Return active space if available
        if space_id in self._active_spaces:
            space = self._active_spaces[space_id]
            if space.is_initialized:
                return space

        # Check if space is registered
        info = self._registry.get(space_id)
        if not info:
            raise SpaceError(f"Space '{space_id}' not found")

        # Create and initialize
        space = factory_create_space(info.space_type, self._spaces_root, space_id)
        await space.initialize()

        # Track as active
        self._active_spaces[space_id] = space

        return space

    async def get_default_space(self) -> BaseSpace:
        """
        Get the default space.

        Creates it if it doesn't exist.

        Returns:
            Initialized default space
        """
        if DEFAULT_SPACE_ID not in self._registry:
            return await self.create_space(DEFAULT_SPACE_ID)
        return await self.get_space(DEFAULT_SPACE_ID)

    async def delete_space(self, space_id: str, delete_files: bool = False) -> bool:
        """
        Delete a space.

        Args:
            space_id: Space identifier
            delete_files: If True, also delete the space directory

        Returns:
            True if deleted

        Raises:
            SpaceError: If trying to delete default space
        """
        if space_id == DEFAULT_SPACE_ID:
            raise SpaceError("Cannot delete the default space")

        if space_id not in self._registry:
            return False

        # Shutdown if active
        if space_id in self._active_spaces:
            await self._active_spaces[space_id].shutdown()
            del self._active_spaces[space_id]

        info = self._registry[space_id]

        # Optionally delete files
        if delete_files and info.path:
            import shutil
            path = Path(info.path)
            if path.exists():
                shutil.rmtree(path)
                logger.info(f"Deleted space directory: {path}")

        # Remove from registry
        del self._registry[space_id]
        self._save_registry()

        logger.info(f"Deleted space '{space_id}'")
        return True

    def is_space_active(self, space_id: str) -> bool:
        """Check if a space is currently active (initialized)."""
        return space_id in self._active_spaces and self._active_spaces[space_id].is_initialized
