"""
Directory-based space implementation.

A simple local directory serving as a project space, with no containerization
or isolation beyond file system boundaries.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseSpace, BaseSpaceFactory
from ..config import SpaceConfig
from ..exceptions import (
    SpaceInitializationError,
    SpaceNotReadyError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DirectorySpace(BaseSpace):
    """
    Directory-based space implementation.

    Structure:
        <space-root>/
        ├── workspace/       # Agent's sandboxed working directory
        ├── space.toml       # Space configuration
        └── opencode.json    # Created by agent when set_space() is called
    """

    def __init__(
        self,
        path: Path,
        space_id: str,
    ) -> None:
        """
        Initialize a directory space.

        Args:
            path: Root path of the space directory
            space_id: Unique identifier for this space
        """
        self._path = path
        self._space_id = space_id
        self._config: SpaceConfig | None = None
        self._workspace: Path | None = None
        self._initialized = False

    # ========== BaseSpace Implementation ==========

    @property
    def space_type(self) -> str:
        """Return the type/name of this space implementation."""
        return "directory"

    @property
    def space_id(self) -> str:
        """Return the unique identifier for this space instance."""
        return self._space_id

    @property
    def path(self) -> Path:
        """Return the root path of this space."""
        return self._path

    @property
    def workspace_path(self) -> Path:
        """Return the working directory where the agent operates."""
        if self._workspace is None:
            raise SpaceNotReadyError("Space not initialized - workspace not available")
        return self._workspace

    @property
    def config(self) -> SpaceConfig:
        """Return the space configuration."""
        if self._config is None:
            raise SpaceNotReadyError("Space not initialized - config not available")
        return self._config

    @property
    def is_initialized(self) -> bool:
        """Check if the space has been initialized."""
        return self._initialized

    def get_enabled_mcps(self) -> list[str]:
        """Get list of MCP server IDs enabled for this space."""
        if self._config is None:
            return []
        return self._config.enabled_mcps.copy()

    def set_enabled_mcps(self, mcp_ids: list[str]) -> None:
        """Update which MCP servers are enabled for this space."""
        if self._config is None:
            raise SpaceNotReadyError("Space not initialized")
        self._config.enabled_mcps = mcp_ids.copy()

    def save_config(self) -> None:
        """Persist the current space configuration to disk."""
        if self._config is None:
            raise SpaceNotReadyError("Space not initialized")
        self._config.save(self._path)
        logger.debug(f"Saved config for space '{self._space_id}'")

    async def initialize(self) -> None:
        """
        Initialize the space.

        Creates the directory structure and loads configuration.

        Raises:
            SpaceInitializationError: If initialization fails
        """
        if self._initialized:
            return

        logger.info(f"Initializing directory space '{self._space_id}' at {self._path}")

        try:
            # Create space root directory
            self._path.mkdir(parents=True, exist_ok=True)

            # Create workspace subdirectory
            self._workspace = self._path / "workspace"
            self._workspace.mkdir(parents=True, exist_ok=True)

            # Load or create configuration
            self._config = SpaceConfig.load(self._path)
            
            # Set name from space_id if using defaults
            if self._config.name == "default":
                self._config.name = self._space_id

            # Save config (creates space.toml if it doesn't exist)
            self._config.save(self._path)

            self._initialized = True
            logger.info(
                f"Directory space '{self._space_id}' initialized "
                f"(workspace: {self._workspace})"
            )

        except Exception as e:
            logger.exception(f"Failed to initialize space '{self._space_id}'")
            raise SpaceInitializationError(str(e)) from e

    async def shutdown(self) -> None:
        """
        Shutdown the space and clean up resources.

        For directory spaces, this just saves config and marks as uninitialized.
        The directory itself is preserved.
        """
        logger.info(f"Shutting down directory space '{self._space_id}'")

        # Save any pending config changes
        if self._config is not None and self._initialized:
            try:
                self._config.save(self._path)
            except Exception as e:
                logger.warning(f"Failed to save config on shutdown: {e}")

        self._initialized = False
        logger.info(f"Directory space '{self._space_id}' shutdown complete")

    # ========== Context Manager Support ==========

    def __enter__(self) -> "DirectorySpace":
        """Synchronous context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Synchronous context manager exit."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.shutdown())
            else:
                loop.run_until_complete(self.shutdown())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self.shutdown())
            loop.close()

    async def __aenter__(self) -> "DirectorySpace":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.shutdown()


class DirectorySpaceFactory(BaseSpaceFactory):
    """Factory for creating directory space instances."""

    def create_space(self, spaces_root: Path, space_id: str) -> DirectorySpace:
        """
        Create a directory space instance.

        Args:
            spaces_root: Root directory where all spaces are stored
            space_id: Unique identifier for this space (used as directory name)

        Returns:
            DirectorySpace instance (not yet initialized)
        """
        path = spaces_root / space_id
        return DirectorySpace(path=path, space_id=space_id)

    def space_type(self) -> str:
        """Return the space type this factory creates."""
        return "directory"
