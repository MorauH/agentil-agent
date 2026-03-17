"""
Streaming response handling for OpenCode.

Manages streaming text responses from OpenCode sessions with proper
delta-based incremental text yielding.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import httpx

from .events import EventType, SSEEvent, SessionStatus, parse_sse_event
from .exceptions import OpenCodeSessionError

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Manages streaming responses from OpenCode.

    Handles SSE connection, event parsing, and incremental text streaming.
    """

    def __init__(self, base_url: str, timeout: float = 300.0):
        """
        Initialize stream manager.

        Args:
            base_url: Base URL for OpenCode server
            timeout: Timeout for requests
        """
        self._base_url = base_url
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        """Current base URL."""
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        """Set a new base URL."""
        self._base_url = value

    async def subscribe_events(
        self,
        *,
        on_open: Callable[[], Awaitable[None]] | None = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """Subscribe to server-sent events.

        Args:
            on_open: Optional async callback invoked once the SSE connection
                is established. This is useful to avoid races where events are
                emitted before the consumer is listening.

        Yields:
            Parsed `SSEEvent` objects.
        """
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(None, connect=10.0),  # No read timeout for SSE
        ) as client:
            async with client.stream("GET", "/event") as response:
                response.raise_for_status()

                if on_open is not None:
                    await on_open()

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk

                    # Process complete events (separated by double newline)
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        event = parse_sse_event(event_str)
                        if event:
                            yield event

    async def stream_text_response(
        self,
        session_id: str,
        *,
        start_request: Callable[[], Awaitable[None]] | None = None,
        timeout: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream text response for a session.

        This method subscribes to events and yields text deltas as they arrive.
        It properly handles the delta field from message.part.updated events.

        Args:
            session_id: Session ID to stream from
            timeout: Optional timeout in seconds

        Yields:
            Text deltas (incremental chunks, not cumulative)

        Raises:
            OpenCodeError: If session encounters an error
            asyncio.TimeoutError: If timeout is exceeded
        """
        start_time = asyncio.get_event_loop().time() if timeout else None
        error_message: str | None = None
        response_started = False

        try:
            async for event in self.subscribe_events(on_open=start_request):
                # Check timeout
                if timeout and start_time:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed > timeout:
                        raise asyncio.TimeoutError(f"Stream timeout after {timeout}s")

                # Skip events for other sessions
                if not event.is_for_session(session_id):
                    continue

                # Handle text updates - CRITICAL: Use delta field!
                if event.type == EventType.MESSAGE_PART_UPDATED:
                    part_data = event.properties.get("part", {})

                    # Only process text parts
                    if part_data.get("type") != "text":
                        continue

                    # The delta field contains the NEW text chunk
                    delta = event.properties.get("delta")
                    if delta:
                        response_started = True
                        logger.debug(f"Yielding delta: {repr(delta)}")
                        yield delta

                # Handle session status changes
                elif event.type == EventType.SESSION_STATUS:
                    status = event.properties.get("status", {})
                    if status.get("type") == SessionStatus.IDLE and response_started:
                        logger.debug("Session became idle, ending stream")
                        return

                # Handle explicit idle event
                elif event.type == EventType.SESSION_IDLE:
                    logger.debug("Received session.idle event, ending stream")
                    return

                # Handle errors
                elif event.type == EventType.SESSION_ERROR:
                    error_message = event.properties.get("error", "Unknown error")
                    logger.error(f"Session error: {error_message}")
                    raise OpenCodeSessionError(error_message)

                # Handle message completion
                elif event.type == EventType.MESSAGE_UPDATED:
                    info = event.properties.get("info", {})
                    # If message has finish status and response started, we're done
                    if "finish" in info and response_started:
                        logger.debug(f"Message finished: {info.get('finish')}")
                        # Don't return yet - wait for session.idle

        except asyncio.CancelledError:
            logger.debug("Stream cancelled")
            raise
        except Exception as e:
            logger.error(f"Stream error: {e}")
            raise

    async def stream_with_events(
        self,
        session_id: str,
        *,
        start_request: Callable[[], Awaitable[None]] | None = None,
        include_events: bool = True,
    ) -> AsyncGenerator[tuple[str | None, dict[str, Any] | None], None]:
        """
        Stream both text and raw events for advanced use cases.

        Args:
            session_id: Session ID to stream from
            include_events: Whether to include non-text events

        Yields:
            Tuples of (text_delta, event_data)
            - text_delta is None for non-text events
            - event_data is None for text-only yields
        """
        async for event in self.subscribe_events(on_open=start_request):
            if not event.is_for_session(session_id):
                continue

            # Handle text
            if event.type == EventType.MESSAGE_PART_UPDATED:
                delta = event.properties.get("delta")
                if delta:
                    yield (delta, event.properties if include_events else None)
                    continue

            # Handle completion
            if event.type in (EventType.SESSION_IDLE, EventType.SESSION_STATUS):
                status = event.properties.get("status", {})
                if event.type == EventType.SESSION_IDLE or status.get("type") == SessionStatus.IDLE:
                    if include_events:
                        yield (None, event.properties)
                    return

            # Other events
            if include_events:
                yield (None, event.properties)


# Convenience function for simple streaming
async def stream_response(
    base_url: str,
    session_id: str,
    timeout: float | None = None,
) -> AsyncGenerator[str, None]:
    """
    Simple function to stream text response.

    Args:
        base_url: OpenCode server base URL
        session_id: Session to stream from
        timeout: Optional timeout

    Yields:
        Text deltas
    """
    manager = StreamManager(base_url)
    async for chunk in manager.stream_text_response(session_id, timeout=timeout):
        yield chunk
