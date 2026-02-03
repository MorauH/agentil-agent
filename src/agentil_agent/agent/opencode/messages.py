"""
Message operations for OpenCode.

Handles sending messages and processing responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a message in a session."""

    id: str
    role: str  # "user" or "assistant"
    session_id: str
    created_at: str | None = None
    parent_id: str | None = None
    model_id: str | None = None
    provider_id: str | None = None


class MessageManager:
    """
    Manages message operations.

    Handles sending messages (sync/async) and parsing responses.
    """

    def __init__(self, base_url: str, timeout: float = 300.0):
        """
        Initialize message manager.

        Args:
            base_url: Base URL for OpenCode server
            timeout: Default timeout for message operations
        """
        self._base_url = base_url
        self.timeout = timeout
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        """Current base URL."""
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        """Set a new base URL, closing existing clients."""
        if value != self._base_url:
            self.close()
            self._base_url = value

    @property
    def client(self) -> httpx.Client:
        """Get or create synchronous HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    @property
    def async_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._async_client

    def close(self) -> None:
        """Close HTTP clients."""
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

    async def aclose(self) -> None:
        """Async close HTTP clients."""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()
        self._async_client = None

    def send_message(
        self,
        session_id: str,
        text: str,
        model: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a message and wait for complete response (synchronous).

        Args:
            session_id: Session ID
            text: Message text
            model: Optional model override {"providerID": "...", "modelID": "..."}

        Returns:
            Response data with info and parts
        """
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }

        if model:
            body["model"] = model

        logger.debug(f"Sending message to session {session_id}: {text[:100]}")
        response = self.client.post(
            f"/session/{session_id}/message",
            json=body,
        )
        response.raise_for_status()

        return response.json()

    async def send_message_async(
        self,
        session_id: str,
        text: str,
        model: dict[str, str] | None = None,
    ) -> None:
        """
        Send a message without waiting for response (async).

        Use streaming.stream_response() to receive the response.

        Args:
            session_id: Session ID
            text: Message text
            model: Optional model override
        """
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }

        if model:
            body["model"] = model

        logger.debug(f"Sending async message to session {session_id}: {text[:100]}")
        response = await self.async_client.post(
            f"/session/{session_id}/prompt_async",
            json=body,
        )
        response.raise_for_status()

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        """
        Extract text content from a message response.

        Args:
            response: Response from send_message()

        Returns:
            Combined text from all text parts
        """
        parts = response.get("parts", [])
        text_parts = []
        for part in parts:
            if part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "".join(text_parts)

    @staticmethod
    def get_message_info(response: dict[str, Any]) -> Message | None:
        """
        Extract message metadata from response.

        Args:
            response: Response from send_message()

        Returns:
            Message object or None
        """
        info = response.get("info")
        if not info:
            return None

        return Message(
            id=info["id"],
            role=info.get("role", "unknown"),
            session_id=info.get("sessionID", ""),
            created_at=info.get("time", {}).get("created"),
            parent_id=info.get("parentID"),
            model_id=info.get("modelID"),
            provider_id=info.get("providerID"),
        )
