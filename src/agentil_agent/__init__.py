"""
Agentil Agent - WebSocket voice server for OpenCode.

Provides a WebSocket API for voice interaction with OpenCode,
supporting STT (speech-to-text) and TTS (text-to-speech).
"""

from .config import (
    Config,
    ServerConfig,
    OpenCodeConfig,
    STTConfig,
    TTSConfig,
    AudioConfig,
    AgentConfig,
    get_config,
    set_config,
)
from .protocol import (
    SessionState,
    AudioFormat,
    TextMessage,
    AudioStartMessage,
    AudioEndMessage,
    CancelMessage,
    ConfigMessage,
    ConnectedMessage,
    TranscriptMessage,
    ResponseStartMessage,
    ResponseDeltaMessage,
    ResponseEndMessage,
    AudioChunkMessage,
    StatusMessage,
    ErrorMessage,
    parse_client_message,
)
from .bridge import (
    OpenCodeBridge,
    Session as OpenCodeSession,
    Message,
    MessagePart,
    SSEEvent,
    ConnectionState,
    OpenCodeError,
    OpenCodeConnectionError,
    OpenCodeNotInstalledError,
    stream_response_sync,
)
from .tts import TTSEngine, speak, stop
from .stt import STTEngine
from .session import Session, SessionManager
from .server import create_app, run_server

__version__ = "0.2.0"

__all__ = [
    # Version
    "__version__",
    # Config
    "Config",
    "ServerConfig",
    "OpenCodeConfig",
    "STTConfig",
    "TTSConfig",
    "AudioConfig",
    "AgentConfig",
    "get_config",
    "set_config",
    # Protocol
    "SessionState",
    "AudioFormat",
    "TextMessage",
    "AudioStartMessage",
    "AudioEndMessage",
    "CancelMessage",
    "ConfigMessage",
    "ConnectedMessage",
    "TranscriptMessage",
    "ResponseStartMessage",
    "ResponseDeltaMessage",
    "ResponseEndMessage",
    "AudioChunkMessage",
    "StatusMessage",
    "ErrorMessage",
    "parse_client_message",
    # Bridge
    "OpenCodeBridge",
    "OpenCodeSession",
    "Message",
    "MessagePart",
    "SSEEvent",
    "ConnectionState",
    "OpenCodeError",
    "OpenCodeConnectionError",
    "OpenCodeNotInstalledError",
    "stream_response_sync",
    # TTS
    "TTSEngine",
    "speak",
    "stop",
    # STT
    "STTEngine",
    # Session
    "Session",
    "SessionManager",
    # Server
    "create_app",
    "run_server",
]
