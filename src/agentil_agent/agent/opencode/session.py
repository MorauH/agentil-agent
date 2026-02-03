"""
Session management for OpenCode.

Handles CRUD operations for OpenCode sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from .exceptions import OpenCodeSessionError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Represents an OpenCode session."""

    id: str
    title: str | None = None
    parent_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    share: str | None = None
    version: str | None = None
    project_id: str | None = None
    directory: str | None = None


class SessionManager:
    """
    Manages OpenCode sessions.

    Handles creating, listing, getting, and deleting sessions.
    Tracks the current active session.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        """
        Initialize session manager.

        Args:
            base_url: Base URL for OpenCode server
            timeout: Default timeout for requests
        """
        self._base_url = base_url
        self.timeout = timeout
        self._client: httpx.Client | None = None
        self._current_session: Session | None = None

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

    def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None

    @property
    def current_session(self) -> Session | None:
        """Get current active session."""
        return self._current_session

    @current_session.setter
    def current_session(self, session: Session | None) -> None:
        """Set current active session."""
        self._current_session = session

    def list_sessions(self) -> list[Session]:
        """
        List all sessions.

        Returns:
            List of Session objects
        """
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
                    version=item.get("version"),
                    project_id=item.get("projectID"),
                    directory=item.get("directory"),
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
            version=data.get("version"),
            project_id=data.get("projectID"),
            directory=data.get("directory"),
        )

        self._current_session = session
        logger.info(f"Created session: {session.id}")
        return session

    def get_session(self, session_id: str) -> Session:
        """
        Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session object
            
        Raises:
            OpenCodeSessionError: If session not found
        """
        try:
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
                version=data.get("version"),
                project_id=data.get("projectID"),
                directory=data.get("directory"),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise OpenCodeSessionError(f"Session not found: {session_id}") from e
            raise OpenCodeSessionError(f"Failed to get session: {e}") from e

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID to delete

        Returns:
            True if deleted successfully
            
        Raises:
            OpenCodeSessionError: If deletion fails
        """
        try:
            response = self.client.delete(f"/session/{session_id}")
            response.raise_for_status()
            if self._current_session and self._current_session.id == session_id:
                self._current_session = None
            logger.info(f"Deleted session: {session_id}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Session not found for deletion: {session_id}")
                return False
            raise OpenCodeSessionError(f"Failed to delete session: {e}") from e

    def ensure_session(self, title: str = "Voice Session") -> Session:
        """
        Ensure a session exists, creating one if needed.

        Args:
            title: Title for new session if created

        Returns:
            Current or newly created session
        """
        if self._current_session is None:
            self._current_session = self.create_session(title=title)
        return self._current_session

    def abort_session(self, session_id: str | None = None) -> bool:
        """
        Abort a running session.

        Args:
            session_id: Session ID (uses current if not provided)

        Returns:
            True if aborted successfully
        """
        if session_id is None and self._current_session:
            session_id = self._current_session.id

        if not session_id:
            return False

        try:
            response = self.client.post(f"/session/{session_id}/abort")
            response.raise_for_status()
            logger.info(f"Aborted session: {session_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to abort session: {e}")
            return False
