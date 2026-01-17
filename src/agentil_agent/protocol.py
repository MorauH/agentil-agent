"""
WebSocket protocol definitions for Agentil Agent server.

Defines all message types exchanged between client and server.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================


class SessionState(str, Enum):
    """Current state of the voice session."""

    IDLE = "idle"
    LISTENING = "listening"  # STT is processing audio
    PROCESSING = "processing"  # Waiting for OpenCode response
    SPEAKING = "speaking"  # TTS is generating/streaming audio
    ERROR = "error"


class AudioFormat(str, Enum):
    """Supported audio formats."""

    WEBM_OPUS = "webm/opus"
    OGG_OPUS = "ogg/opus"
    MP3 = "mp3"
    WAV = "wav"
    PCM = "pcm"  # Raw 16-bit PCM, 16kHz


# =============================================================================
# Client -> Server Messages
# =============================================================================


class TextMessage(BaseModel):
    """Text input from client."""

    type: Literal["text"] = "text"
    content: str = Field(..., description="Text message content")


class AudioStartMessage(BaseModel):
    """Signals start of audio stream from client."""

    type: Literal["audio_start"] = "audio_start"
    format: AudioFormat = Field(
        default=AudioFormat.WEBM_OPUS,
        description="Audio format of incoming stream",
    )
    sample_rate: int = Field(default=16000, description="Sample rate in Hz")


class AudioEndMessage(BaseModel):
    """Signals end of audio stream from client."""

    type: Literal["audio_end"] = "audio_end"


class CancelMessage(BaseModel):
    """Cancel current operation."""

    type: Literal["cancel"] = "cancel"


class ConfigMessage(BaseModel):
    """Runtime configuration update from client."""

    type: Literal["config"] = "config"
    tts_enabled: bool | None = Field(default=None, description="Enable/disable TTS output")
    stt_enabled: bool | None = Field(default=None, description="Enable/disable STT processing")


class PingMessage(BaseModel):
    """Keepalive ping from client."""

    type: Literal["ping"] = "ping"


# Union type for all client messages
ClientMessage = TextMessage | AudioStartMessage | AudioEndMessage | CancelMessage | ConfigMessage | PingMessage


# =============================================================================
# Server -> Client Messages
# =============================================================================


class ConnectedMessage(BaseModel):
    """Sent when client successfully connects."""

    type: Literal["connected"] = "connected"
    session_id: str = Field(..., description="Session identifier")
    server_version: str = Field(..., description="Server version")


class TranscriptMessage(BaseModel):
    """Transcription result from STT."""

    type: Literal["transcript"] = "transcript"
    content: str = Field(..., description="Transcribed text")
    final: bool = Field(
        default=False,
        description="True if this is the final transcription for the utterance",
    )


class ResponseStartMessage(BaseModel):
    """Signals start of AI response."""

    type: Literal["response_start"] = "response_start"


class ResponseDeltaMessage(BaseModel):
    """Incremental AI response text (streaming)."""

    type: Literal["response_delta"] = "response_delta"
    content: str = Field(..., description="New text chunk")


class ResponseEndMessage(BaseModel):
    """Signals end of AI response."""

    type: Literal["response_end"] = "response_end"


class AudioChunkMessage(BaseModel):
    """
    Signals that a binary audio chunk follows.
    
    The actual audio data is sent as a separate binary WebSocket frame
    immediately after this JSON message.
    """

    type: Literal["audio_chunk"] = "audio_chunk"
    format: AudioFormat = Field(..., description="Audio format")
    sentence: str | None = Field(default=None, description="Text being spoken (for sync)")
    chunk_index: int = Field(default=0, description="Chunk index for ordering")
    is_last: bool = Field(default=False, description="True if this is the last chunk")


class AudioStreamStartMessage(BaseModel):
    """Signals start of audio output stream."""

    type: Literal["audio_stream_start"] = "audio_stream_start"
    format: AudioFormat = Field(..., description="Audio format for this stream")
    sample_rate: int = Field(default=24000, description="Sample rate in Hz")


class AudioStreamEndMessage(BaseModel):
    """Signals end of audio output stream."""

    type: Literal["audio_stream_end"] = "audio_stream_end"


class StatusMessage(BaseModel):
    """Session state update."""

    type: Literal["status"] = "status"
    state: SessionState = Field(..., description="Current session state")


class ErrorMessage(BaseModel):
    """Error notification."""

    type: Literal["error"] = "error"
    message: str = Field(..., description="Error message")
    code: str | None = Field(default=None, description="Error code")
    fatal: bool = Field(default=False, description="True if connection should be closed")


class PongMessage(BaseModel):
    """Response to ping."""

    type: Literal["pong"] = "pong"


# Union type for all server messages
ServerMessage = (
    ConnectedMessage
    | TranscriptMessage
    | ResponseStartMessage
    | ResponseDeltaMessage
    | ResponseEndMessage
    | AudioChunkMessage
    | AudioStreamStartMessage
    | AudioStreamEndMessage
    | StatusMessage
    | ErrorMessage
    | PongMessage
)


# =============================================================================
# Message parsing utilities
# =============================================================================


def parse_client_message(data: dict) -> ClientMessage | None:
    """
    Parse a client message from JSON dict.
    
    Args:
        data: Parsed JSON dict
        
    Returns:
        Parsed message or None if invalid
    """
    msg_type = data.get("type")
    
    try:
        match msg_type:
            case "text":
                return TextMessage.model_validate(data)
            case "audio_start":
                return AudioStartMessage.model_validate(data)
            case "audio_end":
                return AudioEndMessage.model_validate(data)
            case "cancel":
                return CancelMessage.model_validate(data)
            case "config":
                return ConfigMessage.model_validate(data)
            case "ping":
                return PingMessage.model_validate(data)
            case _:
                return None
    except Exception:
        return None
