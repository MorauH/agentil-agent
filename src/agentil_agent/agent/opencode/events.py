"""
Event handling for OpenCode SSE streams.

Handles parsing and typed representation of server-sent events.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """Server-sent event from OpenCode."""

    type: str
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def session_id(self) -> str | None:
        """Extract session ID across event shapes.

        OpenCode emits different event payload shapes:
        - `session.*`: properties.sessionID
        - `message.part.updated`: properties.part.sessionID
        - `message.updated`: properties.info.sessionID
        """

        session_id = self.properties.get("sessionID")
        if session_id:
            return session_id

        part = self.properties.get("part")
        if isinstance(part, dict):
            session_id = part.get("sessionID")
            if session_id:
                return session_id

        info = self.properties.get("info")
        if isinstance(info, dict):
            session_id = info.get("sessionID")
            if session_id:
                return session_id

        return None

    @property
    def message_id(self) -> str | None:
        """Extract message ID across event shapes."""

        info = self.properties.get("info")
        if isinstance(info, dict):
            msg_id = info.get("id")
            if msg_id:
                return msg_id

        part = self.properties.get("part")
        if isinstance(part, dict):
            msg_id = part.get("messageID")
            if msg_id:
                return msg_id

        return None

    def is_for_session(self, session_id: str) -> bool:
        """Check if event belongs to a specific session."""
        event_session = self.session_id
        return event_session == session_id if event_session else False


@dataclass
class MessagePart:
    """Represents a part of a message."""

    id: str
    type: str
    session_id: str
    message_id: str
    content: Any = None

    # Text-specific fields
    text: str | None = None
    delta: str | None = None

    # Step-specific fields
    reason: str | None = None
    cost: float | None = None
    tokens: dict[str, Any] | None = None

    @classmethod
    def from_event_properties(cls, part_data: dict[str, Any]) -> "MessagePart":
        """Create MessagePart from event properties."""
        return cls(
            id=part_data["id"],
            type=part_data["type"],
            session_id=part_data["sessionID"],
            message_id=part_data["messageID"],
            text=part_data.get("text"),
            delta=part_data.get("delta"),
            reason=part_data.get("reason"),
            cost=part_data.get("cost"),
            tokens=part_data.get("tokens"),
            content=part_data,
        )


def parse_sse_event(event_str: str) -> SSEEvent | None:
    """
    Parse an SSE event string into an SSEEvent object.

    Args:
        event_str: Raw SSE event string

    Returns:
        Parsed SSEEvent or None if parsing fails
    """
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


# Event type constants for easier reference
class EventType:
    """Common OpenCode event types."""

    SERVER_CONNECTED = "server.connected"
    SESSION_IDLE = "session.idle"
    SESSION_STATUS = "session.status"
    SESSION_UPDATED = "session.updated"
    SESSION_DIFF = "session.diff"
    SESSION_ERROR = "session.error"
    MESSAGE_UPDATED = "message.updated"
    MESSAGE_PART_UPDATED = "message.part.updated"


class SessionStatus:
    """Session status values."""

    IDLE = "idle"
    BUSY = "busy"
