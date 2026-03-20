"""
OpenCode server lifecycle management.

Handles starting, stopping, and checking the OpenCode server process.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .exceptions import OpenCodeNotInstalledError

if TYPE_CHECKING:
    from .connection import ConnectionManager

logger = logging.getLogger(__name__)


class ServerManager:
    """
    Manages OpenCode server process lifecycle.

    Handles installation checks, starting/stopping the server,
    and working directory configuration.
    """

    def __init__(
        self,
        connection_manager: "ConnectionManager",
        host: str = "127.0.0.1",
        port: int = 6274,
        working_dir: Path | str | None = None,
    ):
        """
        Initialize server manager.

        Args:
            connection_manager: Connection manager for health checks
            host: Server host
            port: Server port
            working_dir: Working directory for server process
        """
        self.connection = connection_manager
        self.host = host
        self.port = port
        self._working_dir = Path(working_dir).resolve() if working_dir else None
        self._server_process: subprocess.Popen | None = None

    @property
    def working_dir(self) -> Path | None:
        """Working directory for OpenCode operations."""
        return self._working_dir

    @working_dir.setter
    def working_dir(self, path: Path | str | None) -> None:
        """Set working directory."""
        self._working_dir = Path(path).resolve() if path else None

    @staticmethod
    def is_opencode_installed() -> bool:
        """Check if OpenCode CLI is installed."""
        return shutil.which("opencode") is not None

    @staticmethod
    def get_opencode_version() -> str | None:
        """Get installed OpenCode version."""
        if not ServerManager.is_opencode_installed():
            return None
        try:
            result = subprocess.run(
                ["opencode", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def start_server(self, wait: bool = True, timeout: float = 30.0) -> bool:
        """
        Start OpenCode server if not running.

        Args:
            wait: Wait for server to be ready
            timeout: Timeout in seconds when waiting

        Returns:
            True if server is running, False otherwise

        Raises:
            OpenCodeNotInstalledError: If OpenCode is not installed
        """
        if not self.is_opencode_installed():
            raise OpenCodeNotInstalledError(
                "OpenCode is not installed. Install with: npm install -g opencode-ai"
            )

        # Check if already running
        if self.connection.check_connection():
            logger.info("OpenCode server already running")
            return True

        # Start server process
        logger.info(f"Starting OpenCode server on {self.host}:{self.port}...")

        # Build command
        cmd = [
            "opencode",
            "serve",
            "--port",
            str(self.port),
            "--hostname",
            self.host,
        ]

        # Set working directory for subprocess
        cwd = str(self._working_dir) if self._working_dir else None
        if cwd:
            logger.info(f"Server working directory: {cwd}")

        # Set environment with CWD for OpenCode
        env = os.environ.copy()
        if self._working_dir:
            env["OPENCODE_CWD"] = str(self._working_dir)

        try:
            self._server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                env=env,
            )
        except Exception as e:
            logger.error(f"Failed to start OpenCode server: {e}")
            return False

        if not wait:
            return True

        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.connection.check_connection():
                logger.info("OpenCode server started successfully")
                return True
            time.sleep(0.5)

        logger.error("OpenCode server failed to start within timeout")
        self.stop_server()
        return False

    def stop_server(self) -> None:
        """Stop server process if we started it."""
        if self._server_process:
            logger.info("Stopping OpenCode server...")
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

    def is_running(self) -> bool:
        """Check if server process is running."""
        if self._server_process:
            return self._server_process.poll() is None
        return False
