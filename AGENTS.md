# Agentil Agent - Agent Context

This file provides essential context for AI assistants working on this codebase.

## Project Overview

**Agentil Agent** is a WebSocket voice server for [OpenCode](https://opencode.ai), enabling speech-based interaction with the AI coding assistant. It provides:

- **WebSocket API**: Bidirectional audio/text streaming
- **Speech-to-Text (STT)**: Whisper-based transcription
- **Text-to-Speech (TTS)**: MeloTTS for natural voice output  
- **Flexible I/O**: Clients can send text OR audio, receive BOTH text AND audio
- **Client-Agnostic**: Designed to work with Flutter PWA, CLI, or any WebSocket client

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Agentil Agent Server (Python)                        │
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐ │
│  │  WebSocket   │     │   Session    │     │      Agent Backend           │ │
│  │   Server     │◀───▶│   Manager    │◀───▶│  (HTTP + SSE to OpenCode)    │ │
│  │  (FastAPI)   │     │              │     └──────────────────────────────┘ │
│  └──────────────┘     └──────┬───────┘                                      │
│                              │                                               │
│         ┌────────────────────┼────────────────────┐                         │
│         │                    │                    │                         │
│         ▼                    ▼                    ▼                         │
│    ┌─────────┐        ┌───────────┐        ┌──────────┐                    │
│    │   STT   │        │  Message  │        │   TTS    │                    │
│    │(Whisper)│        │  Router   │        │(MeloTTS) │                    │
│    └─────────┘        └───────────┘        └──────────┘                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
         ▲                                                    │
         │              WebSocket (WSS)                       │
         │   ┌─────────────────────────────────────────────┐  │
         │   │  Client → Server:                           │  │
         │   │  • Text messages                            │  │
         │   │  • Audio chunks (webm/opus)                 │  │
         │   │  • Control commands                         │  │
         └───┴─────────────────────────────────────────────┴──┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         │   Server → Client:                                  │
         │   │  • Transcripts (streaming)                      │
         │   │  • AI Response text (streaming)                 │
         │   │  • TTS Audio chunks (streaming, per sentence)   │
         │   │  • Status/events                                │
         └───┴─────────────────────────────────────────────────┘
```

## Directory Structure

```
agentil-agent/
├── src/agentil_agent/
│   ├── __init__.py        # Package exports
│   ├── main.py            # CLI entry point (click-based)
│   ├── server.py          # FastAPI WebSocket server
│   ├── session.py         # Session manager (state machine)
│   ├── protocol.py        # WebSocket message types
│   ├── config.py          # Pydantic configuration models
│   ├── audio.py           # Audio format conversion (ffmpeg)
│   ├── stt.py             # Speech-to-Text (Whisper)
│   ├── tts.py             # Text-to-Speech (MeloTTS)
│   ├── agent/             # Backend agents (e.g., OpenCode)
│   └── client/
│       └── text_client.py # CLI test client (text in/out)
├── pyproject.toml         # Python project config, dependencies
├── flake.nix              # Nix development environment
├── PROJECT_STATE.md       # Implementation roadmap & progress
├── AGENTS.md              # This file - AI assistant context
└── README.md              # User documentation
```

## Key Components

### 1. Server (`server.py`)

- FastAPI application with WebSocket endpoint
- Token-based authentication via query parameter
- CORS middleware for web clients
- Health check and info endpoints
- Connection handling and message routing

### 2. Session Manager (`session.py`)

- `Session`: Manages voice interaction state
- Coordinates STT, TTS, and agent backend
- States: `IDLE`, `LISTENING`, `PROCESSING`, `SPEAKING`, `ERROR`
- Sentence-level TTS streaming for low latency
- `SessionManager`: Singleton-like session management (single-user mode)

### 3. Protocol (`protocol.py`)

- Pydantic models for all WebSocket messages
- Client messages: `TextMessage`, `AudioStartMessage`, `AudioEndMessage`, `CancelMessage`, `ConfigMessage`
- Server messages: `ConnectedMessage`, `TranscriptMessage`, `ResponseDeltaMessage`, `AudioChunkMessage`, etc.
- `parse_client_message()`: JSON to typed message conversion

### 4. Configuration (`config.py`)

- Uses **Pydantic v2** for validation
- Supports TOML config files
- Config sections: `ServerConfig`, `OpenCodeConfig`, `AgentBackendConfig`, `AssistantConfig`, `STTConfig`, `TTSConfig`, `AudioConfig`
- Token generation and management
- Working directory resolution

### 5. Audio Utilities (`audio.py`)

- `decode_audio_to_pcm()`: Convert incoming audio (webm/opus) to PCM for Whisper
- `encode_audio_to_mp3/opus/wav()`: Encode TTS output for streaming
- `split_text_into_sentences()`: Break response into TTS-able chunks
- Uses ffmpeg for format conversion

### 6. Speech-to-Text (`stt.py`)

- `STTEngine`: Whisper model wrapper
- `transcribe_audio()`: Transcribe PCM numpy array
- Lazy-loads model on first use
- CUDA compatibility checks with CPU fallback

### 7. Text-to-Speech (`tts.py`)

- `TTSEngine`: MeloTTS wrapper
- `synthesize()`: Generate audio from text
- Supports multiple speakers (EN-US, EN-BR, EN-AU)
- Lazy-loads model on first use

### 8. Agent Backend (`agent/`)

- `BaseAgent` interface + `create_agent()` factory
- OpenCode implementation in `src/agentil_agent/agent/opencode/`
- Streaming responses via `BaseAgent.stream_response()`
- Optional server auto-start (OpenCode)

## WebSocket Protocol

### Client → Server

```json
{"type": "text", "content": "Hello, help me with..."}
{"type": "audio_start", "format": "webm/opus"}
// ... binary audio frames ...
{"type": "audio_end"}
{"type": "cancel"}
{"type": "config", "tts_enabled": false}
{"type": "ping"}
```

### Server → Client

```json
{"type": "connected", "session_id": "abc123", "server_version": "0.3.0"}
{"type": "transcript", "content": "Hello", "final": true}
{"type": "response_start"}
{"type": "response_delta", "content": "Sure, "}
{"type": "response_end"}
{"type": "audio_chunk", "format": "mp3", "sentence": "Sure, I can help."}
// ... binary audio frame ...
{"type": "status", "state": "processing"}
{"type": "error", "message": "...", "code": "..."}
{"type": "pong"}
```

## CLI Commands

```bash
# Server
agentil-agent serve                    # Start WebSocket server
agentil-agent serve --host 0.0.0.0     # Bind to all interfaces
agentil-agent serve --port 8080        # Custom port
agentil-agent serve -l DEBUG           # Debug logging

# Client
agentil-agent client --token <token>   # Connect text client
agentil-agent client --tts             # Enable TTS output

# Configuration
agentil-agent config-init              # Generate default config
agentil-agent config-show              # Show current config
agentil-agent token                    # Show auth token
agentil-agent token --regenerate       # Generate new token

# Testing
agentil-agent check                    # Check dependencies
agentil-agent test-tts                 # Test TTS
agentil-agent test-agent              # Test configured agent backend
```

## Configuration File

Location: `~/.config/agentil-agent/config.toml`

```toml
[server]
host = "0.0.0.0"
port = 8765
token = "your-secret-token"

[agent]
type = "opencode"

[agent.opencode]
host = "127.0.0.1"
port = 4096
auto_start = true

[stt]
model = "base"  # tiny, base, small, medium, large
device = "auto"

[tts]
speaker = "EN-BR"
speed = 1.2
device = "auto"

[audio]
input_format = "webm/opus"
output_format = "mp3"

[assistant]
name = "voice-assistant"
prompt = "You are a voice assistant..."
```

## Development Environment

### NixOS (Recommended)

```bash
nix develop  # Enters dev shell with all dependencies
```

### UV/pip

```bash
uv sync                        # Install dependencies
uv run agentil-agent serve    # Run the server
```

### Requirements

- Python 3.11 (specifically `>=3.11,<3.12`)
- ffmpeg (for audio format conversion)
- PyTorch with CUDA support (optional, for GPU acceleration)

## Common Issues & Gotchas

### 1. ffmpeg Required

Audio format conversion requires ffmpeg. Without it, audio input/output won't work.

```bash
# NixOS
nix-shell -p ffmpeg

# Debian/Ubuntu
apt install ffmpeg
```

### 2. CUDA Compatibility

The code includes CUDA compatibility checks because some GPUs have compute capabilities incompatible with certain PyTorch builds. Falls back to CPU if needed.

### 3. Token Authentication

All WebSocket connections require a valid token. Token is auto-generated on first run and saved to config.

### 4. Sentence-Level TTS

TTS is generated per sentence to reduce latency. The `split_text_into_sentences()` function uses simple heuristics.

## Testing

```bash
# Start server
agentil-agent serve

# In another terminal, connect with text client
agentil-agent client --token <token-from-server-output>

# Or use websocat
websocat "ws://localhost:8765/ws?token=<token>"
```

## Project Status

Currently in **Phase 5: WebSocket Server**. See `PROJECT_STATE.md` for detailed roadmap.

### Completed Phases
- Phase 1: Project Setup & Foundation
- Phase 2: OpenCode Integration  
- Phase 3: Voice Controller (legacy, replaced)
- Phase 4: Sandbox Mode (simplified)
- Phase 5: WebSocket Server
- Phase 6: CLI Test Client

### Upcoming Phases
- Phase 7: Polish & Production Ready
- Phase 8: Documentation & Release

## Related Links

- [OpenCode](https://opencode.ai) - The AI coding assistant this bridges to
- [OpenCode Docs](https://opencode.ai/docs) - OpenCode documentation
- [MeloTTS](https://github.com/myshell-ai/MeloTTS) - TTS engine
- [OpenAI Whisper](https://github.com/openai/whisper) - STT engine
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
