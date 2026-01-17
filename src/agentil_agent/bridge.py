"""
OpenCode Bridge - HTTP client for OpenCode server.

Handles communication with OpenCode via its HTTP API and SSE events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


@dataclass
class Session:
    """Represents an OpenCode session."""

    id: str
    title: str | None = None
    parent_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    share: str | None = None


@dataclass
class Message:
    """Represents a message in a session."""

    id: str
    role: str  # "user" or "assistant"
    session_id: str
    created_at: str | None = None


@dataclass
class MessagePart:
    """Represents a part of a message (text, tool call, etc.)."""

    type: str
    content: Any


@dataclass
class SSEEvent:
    """Server-sent event from OpenCode."""

    type: str
    properties: dict[str, Any] = field(default_factory=dict)


class OpenCodeError(Exception):
    """Base exception for OpenCode errors."""

    pass


class OpenCodeConnectionError(OpenCodeError):
    """Connection to OpenCode server failed."""

    pass


class OpenCodeNotInstalledError(OpenCodeError):
    """OpenCode CLI is not installed."""

    pass


class OpenCodeBridge:
    """
    Bridge to OpenCode server.

    Provides methods for:
    - Server management (check, start)
    - Session management
    - Sending prompts
    - Streaming responses via SSE
    """

    def __init__(
        self,
        config: "Config",
        working_dir: Path | str | None = None,
    ) -> None:
        """
        Initialize the bridge.

        Args:
            config: Configuration object with OpenCode settings
            working_dir: Working directory for OpenCode server (affects tool execution)
        """
        self.config = config
        self.base_url = f"http://{config.opencode.host}:{config.opencode.port}"
        self._working_dir = Path(working_dir).resolve() if working_dir else None
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._current_session: Session | None = None
        self._server_process: subprocess.Popen | None = None
        self._state = ConnectionState.DISCONNECTED

    @property
    def working_dir(self) -> Path | None:
        """Working directory for OpenCode operations."""
        return self._working_dir

    @working_dir.setter
    def working_dir(self, path: Path | str | None) -> None:
        """Set working directory."""
        self._working_dir = Path(path).resolve() if path else None

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
                timeout=httpx.Timeout(self.config.opencode.timeout, connect=10.0),
            )
        return self._client

    @property
    def async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.config.opencode.timeout, connect=10.0),
            )
        return self._async_client

    def close(self) -> None:
        """Close HTTP clients and stop server if we started it."""
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

        if self._async_client and not self._async_client.is_closed:
            try:
                # Create a fresh event loop for cleanup
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._async_client.aclose())
                loop.close()
            except Exception:
                # If async close fails, the client will be garbage collected
                # This can happen if the original event loop was already closed
                pass
        self._async_client = None

        self._stop_server()
        self._state = ConnectionState.DISCONNECTED

    async def aclose(self) -> None:
        """Async close for HTTP clients."""
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
        self._async_client = None

        self._stop_server()
        self._state = ConnectionState.DISCONNECTED

    def __enter__(self) -> "OpenCodeBridge":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> "OpenCodeBridge":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    # ========== Server Management ==========

    @staticmethod
    def is_opencode_installed() -> bool:
        """Check if OpenCode CLI is installed."""
        return shutil.which("opencode") is not None

    @staticmethod
    def get_opencode_version() -> str | None:
        """Get installed OpenCode version."""
        if not OpenCodeBridge.is_opencode_installed():
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
        if self.check_connection():
            logger.info("OpenCode server already running")
            return True

        # Start server process
        logger.info(f"Starting OpenCode server on port {self.config.opencode.port}...")
        self._state = ConnectionState.CONNECTING

        # Build command
        cmd = [
            "opencode",
            "serve",
            "--port",
            str(self.config.opencode.port),
            "--hostname",
            self.config.opencode.host,
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
            self._state = ConnectionState.ERROR
            return False

        if not wait:
            return True

        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_connection():
                logger.info("OpenCode server started successfully")
                return True
            time.sleep(0.5)

        logger.error("OpenCode server failed to start within timeout")
        self._stop_server()
        self._state = ConnectionState.ERROR
        return False

        if not wait:
            return True

        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_connection():
                logger.info("OpenCode server started successfully")
                return True
            time.sleep(0.5)

        logger.error("OpenCode server failed to start within timeout")
        self._stop_server()
        self._state = ConnectionState.ERROR
        return False

    def _stop_server(self) -> None:
        """Stop server process if we started it."""
        if self._server_process:
            logger.info("Stopping OpenCode server...")
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

    def ensure_connection(self) -> None:
        """
        Ensure connection to OpenCode server.

        Starts server if auto_start is enabled and server is not running.

        Raises:
            OpenCodeConnectionError: If cannot connect to server
            OpenCodeNotInstalledError: If OpenCode is not installed
        """
        if self.check_connection():
            return

        if self.config.opencode.auto_start:
            if self.start_server():
                return

        raise OpenCodeConnectionError(
            f"Cannot connect to OpenCode server at {self.base_url}. Start it with: opencode serve"
        )

    # ========== Session Management ==========

    def list_sessions(self) -> list[Session]:
        """List all sessions."""
        response = self.client.get("/session")
        response.raise_for_status()

        sessions = []
        for item in response.json():
            sessions.append(
                Session(
                    id=item["id"],
                    title=item.get("title"),
                    parent_id=item.get("parentID"),
                    created_at=item.get("createdAt"),
                    updated_at=item.get("updatedAt"),
                )
            )
        return sessions

    def create_session(self, title: str | None = None) -> Session:
        """
        Create a new session.

        Args:
            title: Optional session title

        Returns:
            Created session
        """
        body = {}
        if title:
            body["title"] = title

        response = self.client.post("/session", json=body)
        response.raise_for_status()

        data = response.json()
        session = Session(
            id=data["id"],
            title=data.get("title"),
            created_at=data.get("createdAt"),
        )

        self._current_session = session
        logger.info(f"Created session: {session.id}")
        return session

    def get_session(self, session_id: str) -> Session:
        """Get session by ID."""
        response = self.client.get(f"/session/{session_id}")
        response.raise_for_status()

        data = response.json()
        return Session(
            id=data["id"],
            title=data.get("title"),
            parent_id=data.get("parentID"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            share=data.get("share"),
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        response = self.client.delete(f"/session/{session_id}")
        response.raise_for_status()
        if self._current_session and self._current_session.id == session_id:
            self._current_session = None
        return True

    @property
    def current_session(self) -> Session | None:
        """Get current active session."""
        return self._current_session

    @current_session.setter
    def current_session(self, session: Session | None) -> None:
        """Set current active session."""
        self._current_session = session

    def ensure_session(self, title: str = "Voice Session") -> Session:
        """Ensure a session exists, creating one if needed."""
        if self._current_session is None:
            self._current_session = self.create_session(title=title)
        return self._current_session

    # ========== Messages (Synchronous) ==========

    def send_message(
        self,
        text: str,
        session_id: str | None = None,
        model: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a message and wait for complete response.

        Args:
            text: Message text
            session_id: Session ID (uses current session if not provided)
            model: Optional model override {"providerID": "...", "modelID": "..."}

        Returns:
            Response data with info and parts
        """
        if session_id is None:
            session = self.ensure_session()
            session_id = session.id

        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }

        if model:
            body["model"] = model

        response = self.client.post(
            f"/session/{session_id}/message",
            json=body,
            timeout=300.0,  # Long timeout for AI responses
        )
        response.raise_for_status()

        return response.json()

    def get_response_text(self, response: dict[str, Any]) -> str:
        """Extract text content from a message response."""
        parts = response.get("parts", [])
        text_parts = []
        for part in parts:
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "".join(text_parts)

    # ========== Messages (Async) ==========

    async def send_message_async(
        self,
        text: str,
        session_id: str | None = None,
        model: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message without waiting for response.

        Use stream_response() or subscribe_events() to receive the response.

        Args:
            text: Message text
            session_id: Session ID (uses current session if not provided)
            model: Optional model override
        """
        if session_id is None:
            session = self.ensure_session()
            session_id = session.id

        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }

        if model:
            body["model"] = model

        response = await self.async_client.post(
            f"/session/{session_id}/prompt_async",
            json=body,
        )
        response.raise_for_status()

    # ========== Events (SSE) ==========

    async def subscribe_events(self) -> AsyncGenerator[SSEEvent, None]:
        """
        Subscribe to server-sent events.

        Yields SSE events as they arrive. Use this to get streaming
        responses and other real-time updates.

        Yields:
            SSEEvent objects
        """
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(None, connect=10.0),  # No read timeout for SSE
        ) as client:
            async with client.stream("GET", "/event") as response:
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk

                    # Process complete events (separated by double newline)
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        event = self._parse_sse_event(event_str)
                        if event:
                            yield event

    def _parse_sse_event(self, event_str: str) -> SSEEvent | None:
        """Parse an SSE event string into an SSEEvent object."""
        event_type = None
        data_lines = []

        for line in event_str.strip().split("\n"):
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif line.startswith(":"):
                # Comment, ignore
                continue

        if not data_lines:
            return None

        data_str = "\n".join(data_lines)

        try:
            data = json.loads(data_str)
            return SSEEvent(
                type=data.get("type", event_type or "unknown"),
                properties=data.get("properties", {}),
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse SSE data: {data_str[:100]}")
            return None

    async def stream_response(
        self,
        text: str,
        session_id: str | None = None,
        model: dict[str, str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Send a message and stream the response text incrementally.

        Yields text chunks as they arrive, not cumulative text.

        Args:
            text: Message text
            session_id: Session ID
            model: Optional model override

        Yields:
            New text chunks from the response (incremental)
        """
        if session_id is None:
            session = self.ensure_session()
            session_id = session.id

        # Track seen text to yield only new content
        seen_text = ""
        response_complete = asyncio.Event()
        error_message: str | None = None

        async def collect_events() -> AsyncGenerator[str, None]:
            nonlocal seen_text, error_message

            async for event in self.subscribe_events():
                # Skip events for other sessions
                event_session = event.properties.get("sessionID")
                if event_session and event_session != session_id:
                    continue

                # Handle text updates
                if event.type == "message.part.updated":
                    part = event.properties.get("part", {})
                    if part.get("type") == "text":
                        full_text = part.get("text", "")
                        # Yield only the new portion
                        if len(full_text) > len(seen_text):
                            new_text = full_text[len(seen_text) :]
                            seen_text = full_text
                            yield new_text

                # Handle completion
                elif event.type == "session.idle":
                    response_complete.set()
                    return

                # Handle errors
                elif event.type == "session.error":
                    error_message = event.properties.get("error", "Unknown error")
                    logger.error(f"Session error: {error_message}")
                    response_complete.set()
                    return

        # Start event collection
        event_gen = collect_events()

        # Send the message
        await self.send_message_async(text, session_id, model)

        # Yield events as they arrive
        async for chunk in event_gen:
            yield chunk

        if error_message:
            raise OpenCodeError(error_message)

    # ========== Utility ==========

    def abort_session(self, session_id: str | None = None) -> bool:
        """Abort a running session."""
        if session_id is None and self._current_session:
            session_id = self._current_session.id

        if not session_id:
            return False

        try:
            response = self.client.post(f"/session/{session_id}/abort")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Failed to abort session: {e}")
            return False

    async def abort_session_async(self, session_id: str | None = None) -> bool:
        """Async abort a running session."""
        if session_id is None and self._current_session:
            session_id = self._current_session.id

        if not session_id:
            return False

        try:
            response = await self.async_client.post(f"/session/{session_id}/abort")
            response.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Failed to abort session: {e}")
            return False


# Synchronous wrapper for streaming (for non-async contexts)
def stream_response_sync(
    bridge: OpenCodeBridge,
    text: str,
    session_id: str | None = None,
) -> Generator[str, None, None]:
    """
    Synchronous wrapper for stream_response.

    Args:
        bridge: OpenCodeBridge instance
        text: Message text
        session_id: Session ID

    Yields:
        Text chunks from the response
    """

    async def run() -> list[str]:
        chunks = []
        async for chunk in bridge.stream_response(text, session_id):
            chunks.append(chunk)
        return chunks

    # Run in event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    chunks = loop.run_until_complete(run())
    yield from chunks


# For testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    # Check OpenCode installation
    print(f"OpenCode installed: {OpenCodeBridge.is_opencode_installed()}")
    print(f"OpenCode version: {OpenCodeBridge.get_opencode_version()}")

    from .config import Config

    config = Config()

    with OpenCodeBridge(config) as bridge:
        print(f"\nChecking connection to {bridge.base_url}...")

        try:
            bridge.ensure_connection()
            print(f"Connected! Server version: {bridge.get_server_version()}")

            # List sessions
            sessions = bridge.list_sessions()
            print(f"Existing sessions: {len(sessions)}")

            # Create a session
            session = bridge.create_session(title="Test Session")
            print(f"Created session: {session.id}")

            # Test synchronous message
            print("\nSending test message (sync)...")
            response = bridge.send_message("Say 'Hello from Agentil Agent!' and nothing else.")
            text = bridge.get_response_text(response)
            print(f"Response: {text}")

            # Test streaming message
            print("\nSending test message (streaming)...")

            async def test_streaming():
                async for chunk in bridge.stream_response(
                    "Count from 1 to 5, one number per line."
                ):
                    print(chunk, end="", flush=True)
                print()

            asyncio.run(test_streaming())

            # Clean up
            bridge.delete_session(session.id)
            print("\nDeleted test session")

        except OpenCodeNotInstalledError:
            print("ERROR: OpenCode is not installed")
            print("Install with: npm install -g opencode-ai")
            sys.exit(1)
        except OpenCodeConnectionError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
