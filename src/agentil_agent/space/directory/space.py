"""
Sets up a basic directory
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseSpace, BaseSpaceFactory
#from ..types import 
from ..exceptions import (
    SpaceInitializationError,
    SpaceNotReadyError,
)

if TYPE_CHECKING:
    from ...config import Config
    from ..config import SpaceConfig, get_space_config

logger = logging.getLogger(__name__)


class DirectorySpace(BaseSpace):
    """
    Nix-Jail space implementation.
    """

    def __init__(
        self,
        path: Path,
    ) -> None:
        """
        Loads configuration

        Args:
            path: path to space root
        """

        self._path = path
        self._config = None
        self._workspace = None

        self._initialized = False

    @property
    def working_dir(self) -> Path | None:
        """Working directory for operations."""
        return self._workspace

    @working_dir.setter # TODO: Should be possible?
    def working_dir(self, path: Path | None) -> None:
        """Set working directory."""
        self._workspace = path

    # ========== BaseSpace Implementation ==========

    async def initialize(self) -> None:
        """
        Initialize the space.

        Ensures space is set up.

        Raises:
            SpaceInitializationError: If initialization fails
        """
        if self._initialized:
            return

        logger.info("Initializing directory space...")
        

        try:
            # Load configuration
            self._config = get_space_config(self._path)
            
            # Create workspace (agent file sandbox)
            self._workspace = self._path / "workspace"
            self._workspace.mkdir(parents=True, exist_ok=True)

            self._initialized = True

        except Exception as e:
            raise SpaceInitializationError(str(e)) from e

    async def shutdown(self) -> None:
        """
        Shutdown the space and clean up resources and temporary files.
        """
        logger.info("Shutting down directory space...")

        self._initialized = False
        logger.info("Directory space shutdown complete")


    @property
    def space_type(self) -> str:
        """
        Return the type/name of this space implementation.

        Returns:
            "directory"
        """
        return "directory"

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
                # If loop is running, schedule shutdown
                loop.create_task(self.shutdown())
            else:
                loop.run_until_complete(self.shutdown())
        except RuntimeError:
            # No event loop, create one
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
    """Factory for creating direcotry space instances."""

    def create_space(self, config: "Config", identifier: str) -> BaseSpace:
        """
        Create an directory space instance.

        Argument
        """
        
        working_dir = config.get_working_dir()
        path = working_dir / "dir-spaces" / identifier
        return DirectorySpace(path)

    def space_type(self) -> str:
        """Return the space type this factory creates."""
        return "directory"
