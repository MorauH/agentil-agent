"""
Server pool for managing multiple OpenCode server instances.

Each space gets its own OpenCode server on a dedicated port.
This is necessary because OpenCode servers are bound to their
working directory at startup and cannot switch projects at runtime.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from .exceptions import OpenCodeNotInstalledError

if TYPE_CHECKING:
    from ...config import OpenCodeConfig

logger = logging.getLogger(__name__)


@dataclass
class ServerInstance:
    """Represents a running OpenCode server instance."""

    port: int
    working_dir: Path
    space_id: str
    process: subprocess.Popen | None = None
    host: str = "127.0.0.1"

    @property
    def base_url(self) -> str:
        """HTTP base URL for this server."""
        return f"http://{self.host}:{self.port}"

    def is_healthy(self) -> bool:
        """Check if the server is responding to health checks."""
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/global/health")
                response.raise_for_status()
                data = response.json()
                return data.get("healthy", False)
        except Exception:
            return False

    def get_project_path(self) -> str | None:
        """Get the current project path from the server."""
        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"{self.base_url}/project/current")
                response.raise_for_status()
                data = response.json()
                return data.get("path")
        except Exception:
            return None

    def stop(self) -> None:
        """Stop the server process if we started it."""
        if self.process:
            logger.info(f"Stopping OpenCode server on port {self.port}")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


@dataclass
class PortAllocation:
    """Tracks port allocations for spaces."""

    space_id: str
    port: int
    allocated_at: float = field(default_factory=time.time)


class ServerPool:
    """
    Manages a pool of OpenCode server instances.

    Each space gets its own server on a dedicated port from the configured range.
    Handles:
    - Port allocation and tracking
    - Server lifecycle (start/stop)
    - Connection to existing servers
    - Graceful cleanup
    """

    def __init__(
        self,
        config: "OpenCodeConfig",
    ) -> None:
        """
        Initialize the server pool.

        Args:
            config: OpenCode configuration with port range settings
        """
        self.config = config
        self.host = config.host
        self.base_port = config.base_port
        self.max_servers = config.max_servers

        # Track running servers: space_id -> ServerInstance
        self._servers: dict[str, ServerInstance] = {}

        # Track port allocations: port -> PortAllocation
        self._port_allocations: dict[int, PortAllocation] = {}

    @property
    def port_range(self) -> tuple[int, int]:
        """Get the port range (inclusive) for this pool."""
        return (self.base_port, self.base_port + self.max_servers - 1)

    def _is_port_in_range(self, port: int) -> bool:
        """Check if a port is within our managed range."""
        start, end = self.port_range
        return start <= port <= end

    def _find_available_port(self) -> int | None:
        """
        Find an available port in the range.

        Returns:
            An available port number, or None if all ports are in use
        """
        start, end = self.port_range

        for port in range(start, end + 1):
            if port not in self._port_allocations:
                # Double-check the port isn't actually in use
                if not self._is_port_in_use(port):
                    return port

        return None

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port has a responding server."""
        try:
            with httpx.Client(timeout=1.0) as client:
                response = client.get(f"http://{self.host}:{port}/global/health")
                return response.status_code == 200
        except Exception:
            return False

    def _allocate_port(self, space_id: str) -> int:
        """
        Allocate a port for a space.

        Args:
            space_id: Space identifier

        Returns:
            Allocated port number

        Raises:
            RuntimeError: If no ports are available
        """
        # Check if space already has a port
        for port, allocation in self._port_allocations.items():
            if allocation.space_id == space_id:
                return port

        # Find a new port
        port = self._find_available_port()
        if port is None:
            raise RuntimeError(
                f"No available ports in range {self.port_range}. "
                f"Max servers: {self.max_servers}"
            )

        self._port_allocations[port] = PortAllocation(space_id=space_id, port=port)
        logger.info(f"Allocated port {port} for space '{space_id}'")
        return port

    def _release_port(self, space_id: str) -> None:
        """Release a port allocation for a space."""
        to_remove = [
            port for port, alloc in self._port_allocations.items()
            if alloc.space_id == space_id
        ]
        for port in to_remove:
            del self._port_allocations[port]
            logger.info(f"Released port {port} from space '{space_id}'")

    def get_server(self, space_id: str) -> ServerInstance | None:
        """
        Get the server instance for a space.

        Args:
            space_id: Space identifier

        Returns:
            ServerInstance if one exists for this space, None otherwise
        """
        return self._servers.get(space_id)

    def get_or_start_server(
        self,
        space_id: str,
        working_dir: Path,
        timeout: float = 30.0,
    ) -> ServerInstance:
        """
        Get or start a server for a space.

        If a server already exists and is healthy, returns it.
        If a server exists but is in the wrong directory, stops and restarts it.
        Otherwise starts a new server.

        Args:
            space_id: Space identifier
            working_dir: Working directory for the server
            timeout: Timeout for waiting for server to start

        Returns:
            Running ServerInstance

        Raises:
            OpenCodeNotInstalledError: If OpenCode CLI is not installed
            RuntimeError: If server fails to start
        """
        working_dir = Path(working_dir).resolve()

        # Check existing server
        existing = self._servers.get(space_id)
        if existing:
            if existing.is_healthy():
                # Verify it's in the right directory
                current_path = existing.get_project_path()
                if current_path:
                    current_normalized = str(Path(current_path).resolve())
                    expected_normalized = str(working_dir)

                    if current_normalized == expected_normalized:
                        logger.debug(f"Reusing existing server for space '{space_id}' on port {existing.port}")
                        return existing
                    else:
                        logger.warning(
                            f"Server for space '{space_id}' in wrong directory: "
                            f"{current_path} (expected: {working_dir})"
                        )

            # Server exists but is unhealthy or wrong directory - stop it
            logger.info(f"Stopping existing server for space '{space_id}'")
            self.stop_server(space_id)

        # Start new server
        return self._start_server(space_id, working_dir, timeout)

    def _start_server(
        self,
        space_id: str,
        working_dir: Path,
        timeout: float = 30.0,
    ) -> ServerInstance:
        """
        Start a new OpenCode server for a space.

        Args:
            space_id: Space identifier
            working_dir: Working directory for the server
            timeout: Timeout for waiting for server to start

        Returns:
            Started ServerInstance

        Raises:
            OpenCodeNotInstalledError: If OpenCode CLI is not installed
            RuntimeError: If server fails to start
        """
        import shutil

        if not shutil.which("opencode"):
            raise OpenCodeNotInstalledError(
                "OpenCode is not installed. Install with: npm install -g opencode-ai"
            )

        # Allocate port
        port = self._allocate_port(space_id)

        # Check if something is already running on this port
        if self._is_port_in_use(port):
            # Try to check if it's ours (right directory)
            try:
                with httpx.Client(timeout=2.0) as client:
                    response = client.get(f"http://{self.host}:{port}/project/current")
                    if response.status_code == 200:
                        current_path = response.json().get("path")
                        if current_path:
                            current_normalized = str(Path(current_path).resolve())
                            expected_normalized = str(working_dir)

                            if current_normalized == expected_normalized:
                                # Already running in correct directory
                                logger.info(
                                    f"Found existing server on port {port} in correct directory"
                                )
                                instance = ServerInstance(
                                    port=port,
                                    working_dir=working_dir,
                                    space_id=space_id,
                                    process=None,  # We didn't start it
                                    host=self.host,
                                )
                                self._servers[space_id] = instance
                                return instance

                            # Wrong directory - dispose it
                            logger.info(
                                f"Disposing existing server on port {port} (wrong directory)"
                            )
                            client.post(f"http://{self.host}:{port}/instance/dispose")
                            time.sleep(1)
            except Exception as e:
                logger.debug(f"Error checking existing server: {e}")

        # Build command
        cmd = [
            "opencode",
            "serve",
            "--port",
            str(port),
            "--hostname",
            self.host,
        ]

        logger.info(f"Starting OpenCode server for space '{space_id}' on port {port}")
        logger.info(f"Working directory: {working_dir}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(working_dir),
            )
        except Exception as e:
            self._release_port(space_id)
            raise RuntimeError(f"Failed to start OpenCode server: {e}") from e

        # Create instance
        instance = ServerInstance(
            port=port,
            working_dir=working_dir,
            space_id=space_id,
            process=process,
            host=self.host,
        )

        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if instance.is_healthy():
                self._servers[space_id] = instance
                logger.info(f"OpenCode server started for space '{space_id}' on port {port}")
                return instance
            time.sleep(0.5)

        # Failed to start
        instance.stop()
        self._release_port(space_id)
        raise RuntimeError(
            f"OpenCode server for space '{space_id}' failed to start within {timeout}s"
        )

    def stop_server(self, space_id: str) -> bool:
        """
        Stop the server for a space.

        Args:
            space_id: Space identifier

        Returns:
            True if a server was stopped
        """
        instance = self._servers.pop(space_id, None)
        if instance:
            instance.stop()
            self._release_port(space_id)
            logger.info(f"Stopped server for space '{space_id}'")
            return True
        return False

    def stop_all(self) -> None:
        """Stop all managed servers."""
        logger.info(f"Stopping all servers ({len(self._servers)} active)")
        for space_id in list(self._servers.keys()):
            self.stop_server(space_id)

    def get_port_for_space(self, space_id: str) -> int | None:
        """
        Get the allocated port for a space (if any).

        Args:
            space_id: Space identifier

        Returns:
            Port number or None if no port is allocated
        """
        for port, alloc in self._port_allocations.items():
            if alloc.space_id == space_id:
                return port
        return None

    def get_stats(self) -> dict:
        """Get pool statistics for debugging."""
        return {
            "port_range": self.port_range,
            "max_servers": self.max_servers,
            "active_servers": len(self._servers),
            "allocated_ports": len(self._port_allocations),
            "servers": {
                space_id: {
                    "port": inst.port,
                    "working_dir": str(inst.working_dir),
                    "healthy": inst.is_healthy(),
                    "managed_process": inst.process is not None,
                }
                for space_id, inst in self._servers.items()
            },
        }
