"""
Connection management for OpenCode bridge.

Handles HTTP client lifecycle and health checks.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    """Connection state to OpenCode server."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionManager:
    """
    Manages HTTP connections to OpenCode server.

    Handles client lifecycle, health checks, and connection state tracking.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """
        Initialize connection manager.

        Args:
            base_url: Base URL for OpenCode server
            timeout: Default timeout for requests
        """
        self.base_url = base_url
        self.timeout = timeout
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._state = ConnectionState.DISCONNECTED

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def client(self) -> httpx.Client:
        """Get or create synchronous HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    @property
    def async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._async_client

    def close(self) -> None:
        """Close HTTP clients."""
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

        if self._async_client and not self._async_client.is_closed:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._async_client.aclose())
                loop.close()
            except Exception:
                pass
        self._async_client = None

        self._state = ConnectionState.DISCONNECTED

    async def aclose(self) -> None:
        """Async close for HTTP clients."""
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
        self._async_client = None

        self._state = ConnectionState.DISCONNECTED

    def check_connection(self) -> bool:
        """
        Check if OpenCode server is reachable.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            response = self.client.get("/global/health")
            response.raise_for_status()
            data = response.json()
            healthy = data.get("healthy", False)
            if healthy:
                self._state = ConnectionState.CONNECTED
            return healthy
        except httpx.ConnectError:
            logger.debug(f"Cannot connect to {self.base_url}")
            self._state = ConnectionState.DISCONNECTED
            return False
        except Exception as e:
            logger.debug(f"Connection check failed: {e}")
            self._state = ConnectionState.ERROR
            return False

    def get_server_version(self) -> str | None:
        """Get OpenCode server version."""
        try:
            response = self.client.get("/global/health")
            response.raise_for_status()
            data = response.json()
            return data.get("version")
        except Exception:
            return None

    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == ConnectionState.CONNECTED
