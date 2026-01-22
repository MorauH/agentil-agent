# Agentil Agent - Project State

This file tracks the implementation progress and serves as a guide for incremental development.

## Current Phase: 5 - WebSocket Server Architecture

## Project Overview

Agentil Agent is a **voice server** for OpenCode, providing:
- **Speech-to-Text (STT)** via Whisper for voice input
- **Text-to-Speech (TTS)** via MeloTTS for spoken responses
- **WebSocket API** for bidirectional streaming with any client
- **Flexible I/O** - Clients can mix text/audio input and receive both text/audio output

The server is **client-agnostic** - designed to work with:
- Flutter PWA (primary target)
- CLI clients
- Any WebSocket-capable application

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Agentil Agent Server (Python)                       │
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
         │   │  • Audio chunks (webm/opus)                 │  │
         │   │  • Text messages                            │  │
         │   │  • Control commands                         │  │
         └───┴─────────────────────────────────────────────┴──┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         │   │  • Transcripts (streaming)                      │
         │   │  • AI Response text (streaming)                 │
         │   │  • TTS Audio chunks (streaming)                 │
         │   │  • Status/events                                │
         └───┴─────────────────────────────────────────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │   Client (any)        │
                        │   - Flutter PWA       │
                        │   - CLI               │
                        │   - etc.              │
                        └───────────────────────┘
```

### Flexible I/O Modes

The server accepts any combination of input/output:

| Input | Output | Use Case |
|-------|--------|----------|
| Text | Text | Traditional chat, testing |
| Text | Text + Audio | Accessibility, hands-free |
| Audio | Text | Voice-to-text transcription |
| Audio | Text + Audio | Full voice assistant |

The **client decides** what to send and what to consume. Server always provides both text and audio output (client can ignore audio if not needed).

### WebSocket Protocol

#### Client → Server Messages

```json
// Text input
{"type": "text", "content": "Hello, help me with..."}

// Audio input start (followed by binary frames)
{"type": "audio_start", "format": "webm/opus"}
// ... binary audio frames ...
{"type": "audio_end"}

// Control commands
{"type": "cancel"}
{"type": "config", "tts_enabled": true, "stt_enabled": true}
```

#### Server → Client Messages

```json
// Transcription from STT (streaming)
{"type": "transcript", "content": "Hello help me", "final": false}
{"type": "transcript", "content": "Hello, help me with...", "final": true}

// AI Response text (streaming, sentence-level)
{"type": "response_start"}
{"type": "response_delta", "content": "Sure, I can help with that. "}
{"type": "response_delta", "content": "Here's what you need to do. "}
{"type": "response_end"}

// TTS Audio (streaming, one chunk per sentence)
{"type": "audio_start", "format": "mp3", "sentence": "Sure, I can help with that."}
// ... binary audio frame ...
{"type": "audio_chunk"}  // signals binary follows
{"type": "audio_end"}

// Status and events
{"type": "status", "state": "listening|processing|speaking|idle"}
{"type": "error", "message": "...", "code": "..."}

// Connection established
{"type": "connected", "session_id": "...", "server_version": "..."}
```

### Session Management

- Server maintains conversation state per WebSocket connection
- All connections treated as same session (single-user mode)
- Reconnecting client resumes existing conversation
- Session includes: conversation history, preferences, OpenCode session ID

### Authentication

Simple token-based authentication:
- Token configured in server config or auto-generated on first run
- Client sends token on connection: `ws://host:port/ws?token=<token>`
- Token can be displayed as QR code for easy mobile setup

---

## Implementation Phases

### Phase 1: Project Setup & Foundation [COMPLETED]
**Status: COMPLETED**

- [x] Create directory structure
- [x] Create pyproject.toml with dependencies
- [x] Create flake.nix for NixOS
- [x] Implement TTS engine (MeloTTS)
- [x] Implement STT engine (Whisper)
- [x] Create config system (Pydantic)

---

### Phase 2: OpenCode Integration [COMPLETED]
**Status: COMPLETED**

- [x] Implement OpenCode HTTP client
- [x] Implement SSE streaming for responses
- [x] Session management
- [x] Server auto-start capability

---

### Phase 3: Voice Controller [COMPLETED - TO BE REPLACED]
**Status: COMPLETED (Legacy)**

The original voice controller was a local state machine for CLI use.
This will be **replaced** by the WebSocket session manager in Phase 5.

Components to **keep**:
- `stt.py` - STT engine (Whisper wrapper)
- `tts.py` - TTS engine (MeloTTS wrapper)
- `agent/opencode/` - OpenCode agent backend implementation
- `config.py` - Configuration system (will be extended)

Components to **replace**:
- `controller.py` - Replaced by WebSocket session manager
- `keyboard.py` - No longer needed (input comes from clients)
- `main.py` - Rewritten for server mode

---

### Phase 4: Sandbox Mode [COMPLETED - SIMPLIFIED]
**Status: COMPLETED (Will be simplified)**

Sandbox mode remains but becomes server-side configuration:
- Server runs with a configured working directory
- Voice-assistant agent prompt still applies
- Client doesn't need to know about sandbox vs local

---

### Phase 5: WebSocket Server [CURRENT]
**Status: IN PROGRESS**
**Goal:** Implement WebSocket server with bidirectional audio/text streaming

#### 5.1 Server Foundation
- [ ] Add FastAPI + WebSocket dependencies
- [ ] Create WebSocket server entry point
- [ ] Implement connection handling with token auth
- [ ] Define message types (Pydantic models)
- [ ] Basic health check endpoint

#### 5.2 Session Manager
- [ ] Create session manager (replaces controller)
- [ ] Track connection state
- [ ] Handle reconnection (resume session)
- [ ] Manage conversation history

#### 5.3 Text Input/Output
- [ ] Handle text input messages
- [ ] Stream text responses from OpenCode
- [ ] Sentence-level buffering for TTS triggers

#### 5.4 Audio Input (STT)
- [ ] Receive audio chunks from client
- [ ] Buffer and decode audio (webm/opus → PCM)
- [ ] Run Whisper transcription
- [ ] Stream transcript updates to client

#### 5.5 Audio Output (TTS)
- [ ] Generate TTS for each sentence
- [ ] Encode audio for streaming (mp3 or opus)
- [ ] Stream audio chunks to client
- [ ] Coordinate text + audio timing

#### 5.6 Configuration Updates
- [ ] Add `[server]` config section (host, port, token)
- [ ] Add audio format settings
- [ ] Token generation/management

**Exit Criteria:**
- WebSocket server accepts connections with token auth
- Can send text, receive streaming text + audio response
- Can send audio, receive transcript + streaming response + audio
- Sentence-level TTS streaming works

---

### Phase 6: CLI Test Client [PLANNED]
**Status: NOT STARTED**
**Goal:** Simple CLI client for testing (text-in, text-out via WebSocket)

- [ ] WebSocket client using `websockets` library
- [ ] Connect with token auth
- [ ] Send text messages
- [ ] Display streaming responses
- [ ] Simple REPL interface

**Exit Criteria:**
- Can test server without Flutter client
- Validates WebSocket protocol works

---

### Phase 7: Polish & Production Ready [PLANNED]
**Status: NOT STARTED**
**Goal:** Production hardening and UX improvements

- [ ] Error handling and recovery
- [ ] Graceful shutdown
- [ ] Logging and monitoring
- [ ] Rate limiting
- [ ] Audio format negotiation
- [ ] Performance optimization
- [ ] HTTPS/WSS support documentation

---

### Phase 8: Documentation & Release [PLANNED]
**Status: NOT STARTED**
**Goal:** Prepare for public release

- [ ] API documentation (WebSocket protocol)
- [ ] Server setup guide
- [ ] Client integration guide
- [ ] Docker deployment option
- [ ] Example Flutter client code snippets

---

## Configuration

### Current Config Structure (agentil-agent.toml)

```toml
[server]
host = "0.0.0.0"
port = 8765
token = ""  # Auto-generated if empty

[agent]
type = "opencode"

[agent.opencode]
host = "127.0.0.1"
port = 4096
auto_start = true
timeout = 30.0

[stt]
model = "base"  # tiny, base, small, medium, large
device = "auto"  # cpu, cuda, auto

[tts]
speaker = "EN-BR"
speed = 1.2
device = "auto"  # cpu, cuda, mps, auto

[audio]
input_format = "webm/opus"  # Expected from clients
output_format = "mp3"       # Sent to clients
output_sample_rate = 24000

[sandbox]
path = "~/.config/agentil-agent/workspace"

[assistant]
name = "voice-assistant"
prompt = """
You are a voice assistant. Your responses will be spoken aloud via text-to-speech.

Guidelines:
- Keep responses concise and conversational
- Avoid markdown formatting (tables, bullet lists, headers)
- Don't output code blocks unless specifically asked
- Use natural spoken language
- If you need to list items, use "first, second, third" etc.
- For technical content, explain verbally rather than showing code
"""
```

---

## Dependencies

### Core Server
- `fastapi` - Web framework with WebSocket support
- `uvicorn` - ASGI server
- `websockets` - WebSocket protocol
- `pydantic` - Data validation and settings

### OpenCode Integration
- `httpx` - Async HTTP client
- `httpx-sse` - SSE client for streaming

### Audio Processing
- `ffmpeg-python` or subprocess - Audio format conversion
- `numpy` - Audio data handling

### TTS
- `melotts` - Text-to-speech
- `soundfile` - Audio file I/O (for encoding output)

### STT
- `openai-whisper` - Speech recognition
- `torch` - ML runtime

### Configuration
- `tomli` / `tomli-w` - TOML parsing

---

## File Structure (Planned)

```
agentil-agent/
├── src/agentil_agent/
│   ├── __init__.py
│   ├── server.py          # FastAPI app, WebSocket handlers
│   ├── session.py         # Session manager (replaces controller)
│   ├── protocol.py        # WebSocket message types
│   ├── stt.py             # STT engine (existing, minor updates)
│   ├── tts.py             # TTS engine (existing, minor updates)
│   ├── agent/             # Agent backend implementations
│   ├── audio.py           # Audio format conversion utilities
│   ├── config.py          # Configuration
│   ├── sandbox.py         # Sandbox workspace + opencode.json
│   └── main.py            # CLI entry point
├── src/agentil_agent/client/
│   └── text_client.py     # Simple CLI test client
├── pyproject.toml
├── flake.nix
└── README.md
```

---

## Changelog

### 2025-01-17
- **MAJOR ARCHITECTURE CHANGE**: Pivoting from CLI tool to WebSocket server
- New design: Server accepts text OR audio, outputs BOTH text AND audio
- Client-agnostic: Flutter PWA, CLI, or any WebSocket client
- Sentence-level TTS streaming for low latency
- Simple token authentication
- Single-session mode (all connections = same conversation)
- Phases 5-8 rewritten for new architecture

### 2025-01-16
- Phase 4 COMPLETED (sandbox mode)

### 2025-01-15
- Initial project setup
- Phases 1-3 COMPLETED
