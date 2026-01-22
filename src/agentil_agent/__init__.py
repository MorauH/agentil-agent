"""
Agentil Agent - WebSocket voice server for AI agents.

Provides a WebSocket API for voice interaction with various AI agents,
supporting STT (speech-to-text) and TTS (text-to-speech).
"""

from .config import (
    Config,
    ServerConfig,
    OpenCodeConfig,
    AgentBackendConfig,
    AssistantConfig,
    STTConfig,
    TTSConfig,
    AudioConfig,
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

# Agent abstraction
from .agent import (
    BaseAgent,
    BaseAgentFactory,
    AgentSession,
    AgentMessage,
    AgentResponse,
    AgentError,
    AgentNotReadyError,
    AgentSessionError,
    create_agent,
    register_agent_factory,
    list_available_agents,
)

from .tts import TTSEngine, speak, stop
from .stt import STTEngine
from .session import Session, SessionManager
from .server import create_app, run_server

__version__ = "0.3.0"

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
    "AgentBackendConfig",
    "AssistantConfig",
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
    # Agent Abstraction
    "BaseAgent",
    "BaseAgentFactory",
    "AgentSession",
    "AgentMessage",
    "AgentResponse",
    "AgentError",
    "AgentNotReadyError",
    "AgentSessionError",
    "create_agent",
    "register_agent_factory",
    "list_available_agents",
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
