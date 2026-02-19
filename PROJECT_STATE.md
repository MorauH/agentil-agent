# Agentil Agent - Project State

This file tracks the implementation progress and serves as a guide for incremental development.

## Current Phase: 7 - Space & MCP Management

## Project Overview

Agentil Agent is a **voice server** for OpenCode, providing:
- **Speech-to-Text (STT)** via Whisper for voice input
- **Text-to-Speech (TTS)** via MeloTTS for spoken responses
- **WebSocket API** for bidirectional streaming with any client
- **Flexible I/O** - Clients can mix text/audio input and receive both text/audio output
- **Space Management** - Project-based workspaces with isolated configurations
- **MCP Server Management** - Install, update, and delete MCP servers per-space

The server is **client-agnostic** - designed to work with:
- Flutter PWA (primary target)
- CLI clients
- Any WebSocket-capable application

## Architecture

### High-Level Design

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
│    │   STT   │        │   Space   │        │   TTS    │                    │
│    │(Whisper)│        │  Manager  │        │(MeloTTS) │                    │
│    └─────────┘        └─────┬─────┘        └──────────┘                    │
│                             │                                               │
│                       ┌─────┴─────┐                                        │
│                       │    MCP    │                                        │
│                       │  Manager  │                                        │
│                       └───────────┘                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
         ▲                                                    │
         │              WebSocket (WSS)                       │
         │   ┌─────────────────────────────────────────────┐  │
         │   │  • Audio chunks (webm/opus)                 │  │
         │   │  • Text messages                            │  │
         │   │  • Control commands                         │  │
         │   │  • Space/MCP management                     │  │
         └───┴─────────────────────────────────────────────┴──┘
                                    │
         ┌──────────────────────────┴──────────────────────────┐
         │   │  • Transcripts (streaming)                      │
         │   │  • AI Response text (streaming)                 │
         │   │  • TTS Audio chunks (streaming)                 │
         │   │  • Session updates (spaces, MCPs)               │
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

### Space & MCP Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Space Concept                              │
│                                                                      │
│  ┌─────────────────┐      ┌─────────────────┐                       │
│  │  SpaceManager   │      │   MCPManager    │                       │
│  │  (System-level) │      │  (System-level) │                       │
│  │                 │      │                 │                       │
│  │ • List spaces   │      │ • Install MCPs  │                       │
│  │ • Create/delete │      │ • Update MCPs   │                       │
│  │ • Get space     │      │ • Delete MCPs   │                       │
│  │                 │      │ • Track servers │                       │
│  │                 │      │ • Build w/ Nix  │                       │
│  └────────┬────────┘      └────────┬────────┘                       │
│           │                        │                                 │
│           ▼                        ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                        Session                               │    │
│  │                                                              │    │
│  │  current_space ──────┐                                       │    │
│  │                      ▼                                       │    │
│  │              ┌──────────────┐                                │    │
│  │              │    Space     │                                │    │
│  │              │  (instance)  │                                │    │
│  │              │              │                                │    │
│  │              │ • workspace/ │  ◀── Agent working directory   │    │
│  │              │ • space.toml │  ◀── Space configuration       │    │
│  │              │ • enabled    │                                │    │
│  │              │   MCPs list  │  ◀── Which MCPs active here    │    │
│  │              └──────┬───────┘                                │    │
│  │                     │                                        │    │
│  │                     ▼                                        │    │
│  │              ┌──────────────┐                                │    │
│  │              │    Agent     │                                │    │
│  │              │  (OpenCode)  │                                │    │
│  │              │              │                                │    │
│  │              │ set_space()  │  ◀── Injects space context     │    │
│  │              │ writes       │                                │    │
│  │              │ opencode.json│  ◀── MCP config for OpenCode   │    │
│  │              └──────────────┘                                │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Spaces are project workspaces** - Each space has its own:
   - Working directory (`<space-root>/workspace/`)
   - Configuration file (`<space-root>/space.toml`)
   - Enabled MCP list (which MCPs are active in this space)

2. **MCP Manager is system-level** - MCPs are installed once and can be enabled/disabled per-space

3. **Agent receives space via setter** - `agent.set_space(space, mcp_manager)` allows context switching without agent restart

4. **Space switching clears history** - Creates new agent session (fresh conversation)

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
{"type": "ping"}

// Configuration
{
  "type": "config",
  "tts_enabled": true,
  "stt_enabled": true,
  "switch_space": "project-1",        // Switch to different space
  "install_mcp_url": "https://...",   // Install MCP from git URL
  "active_mcps": ["mcp-1", "mcp-2"],  // Set active MCPs for space
  "clear_history": true               // Clear conversation history
}
```

#### Server → Client Messages

```json
// Connection established
{"type": "connected", "session_id": "...", "server_version": "..."}

// Session state update (sent on connect and after changes)
{
  "type": "session_update",
  "available_spaces": [
    {"id": "default", "name": "Default", "description": "..."}
  ],
  "current_space_id": "default",
  "mcp_servers": [
    {"name": "rag-mcp", "version": "1.0", "enabled": true, "description": "..."}
  ],
  "tts_enabled": true,
  "stt_enabled": true
}

// Operation progress (MCP install, space init)
{
  "type": "operation_progress",
  "operation": "install_mcp",
  "target": "rag-mcp",
  "status": "in_progress",  // starting, in_progress, complete, failed
  "progress": 50,
  "message": "Building with nix..."
}

// Transcription from STT (streaming)
{"type": "transcript", "content": "Hello help me", "final": false}
{"type": "transcript", "content": "Hello, help me with...", "final": true}

// AI Response text (streaming, sentence-level)
{"type": "response_start"}
{"type": "response_delta", "content": "Sure, I can help with that. "}
{"type": "response_delta", "content": "Here's what you need to do. "}
{"type": "response_end"}

// TTS Audio (streaming, one chunk per sentence)
{"type": "audio_chunk", "format": "mp3", "sentence": "Sure, I can help with that."}
// ... binary audio frame follows ...

// Status and events
{"type": "status", "state": "listening|processing|speaking|idle"}
{"type": "error", "message": "...", "code": "..."}
{"type": "pong"}
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

### Phase 5: WebSocket Server [COMPLETED]
**Status: COMPLETED**
**Goal:** Implement WebSocket server with bidirectional audio/text streaming

#### 5.1 Server Foundation
- [x] Add FastAPI + WebSocket dependencies
- [x] Create WebSocket server entry point
- [x] Implement connection handling with token auth
- [x] Define message types (Pydantic models)
- [x] Basic health check endpoint

#### 5.2 Session Manager
- [x] Create session manager (replaces controller)
- [x] Track connection state
- [x] Handle reconnection (resume session)
- [x] Manage conversation history

#### 5.3 Text Input/Output
- [x] Handle text input messages
- [x] Stream text responses from OpenCode
- [x] Sentence-level buffering for TTS triggers

#### 5.4 Audio Input (STT)
- [x] Receive audio chunks from client
- [x] Buffer and decode audio (webm/opus → PCM)
- [x] Run Whisper transcription
- [x] Stream transcript updates to client

#### 5.5 Audio Output (TTS)
- [x] Generate TTS for each sentence
- [x] Encode audio for streaming (mp3 or opus)
- [x] Stream audio chunks to client
- [x] Coordinate text + audio timing

#### 5.6 Configuration Updates
- [x] Add `[server]` config section (host, port, token)
- [x] Add audio format settings
- [x] Token generation/management

---

### Phase 6: CLI Test Client [COMPLETED]
**Status: COMPLETED**
**Goal:** Simple CLI client for testing (text-in, text-out via WebSocket)

- [x] WebSocket client using `websockets` library
- [x] Connect with token auth
- [x] Send text messages
- [x] Display streaming responses
- [x] Simple REPL interface
- [x] TTS audio playback support
- [x] Space management commands (/spaces, /space <id>)
- [x] MCP management commands (/mcps, /mcp on/off, /mcp install)

---

### Phase 7: Space & MCP Management [CURRENT]
**Status: IN PROGRESS**
**Goal:** Implement project-based workspaces with MCP server management

#### 7.1 Space Infrastructure
- [x] Create `BaseSpace` abstract class
- [x] Implement `DirectorySpace` (filesystem-based)
- [x] Create `SpaceManager` for managing multiple spaces
- [x] Space configuration (`space.toml`)
- [x] Auto-create default space on startup

#### 7.2 MCP Manager
- [x] Create `MCPManager` for system-level MCP tracking
- [x] MCP server registry (`mcp-servers.json`)
- [x] `install_from_url()` - Install via git + nix
- [x] `register_local()` - Register existing executables
- [x] `update_server()` - Re-clone and rebuild git-installed MCP servers
- [x] `delete_server()` - Unregister and optionally delete clone directory
- [x] Generate OpenCode-compatible MCP config

#### 7.3 Agent Integration
- [x] Add `set_space()` method to `BaseAgent`
- [x] Implement `set_space()` in OpenCode agent
- [x] Generate `opencode.json` with MCP and agent config
- [x] Create mock agent for testing

#### 7.4 Session Integration
- [x] Add SpaceManager and MCPManager to Session
- [x] Implement `switch_space()` method
- [x] Configure agent with space on session start
- [x] Handle space switching (clears history)
- [x] Send `session_update` with spaces and MCPs

#### 7.5 Server Integration
- [x] Add `SpaceManagerConfig` and `MCPManagerConfig`
- [x] Initialize managers in server lifespan
- [x] Pass managers to SessionManager

#### 7.6 Client Integration
- [x] Update text client for new message types
- [x] Add space and MCP commands to client

#### 7.7 Remaining Work
- [ ] End-to-end testing with real MCP servers
- [ ] Space creation via WebSocket API
- [x] MCP uninstall/delete command
- [ ] Better progress reporting for MCP install

---

### Phase 8: Polish & Production Ready [PLANNED]
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

[spaces]
spaces_root = "~/.config/agentil-agent/spaces"
default_space_type = "directory"
auto_initialize = true

[mcp]
base_path = "~/.config/agentil-agent/mcp-servers"
auto_initialize = true

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

## File Structure

```
agentil-agent/
├── src/agentil_agent/
│   ├── __init__.py
│   ├── main.py            # CLI entry point
│   ├── server.py          # FastAPI app, WebSocket handlers
│   ├── session.py         # Session manager with space support
│   ├── protocol.py        # WebSocket message types
│   ├── config.py          # Configuration (Pydantic)
│   ├── stt.py             # STT engine (Whisper)
│   ├── tts.py             # TTS engine (MeloTTS)
│   ├── audio.py           # Audio format conversion utilities
│   │
│   ├── agent/             # Agent backend implementations
│   │   ├── __init__.py    # Factory + registry
│   │   ├── base.py        # BaseAgent abstract class
│   │   ├── mock/          # Mock agent for testing
│   │   │   └── agent.py
│   │   └── opencode/      # OpenCode agent
│   │       ├── __init__.py
│   │       ├── agent.py   # OpenCodeAgent with set_space()
│   │       └── client.py  # HTTP/SSE client
│   │
│   ├── space/             # Space management
│   │   ├── __init__.py    # Factory + exports
│   │   ├── base.py        # BaseSpace abstract class
│   │   ├── config.py      # SpaceConfig model
│   │   ├── manager.py     # SpaceManager
│   │   ├── exceptions.py
│   │   └── directory/     # Directory-based space impl
│   │       ├── __init__.py
│   │       └── space.py   # DirectorySpace
│   │
│   ├── mcp/               # MCP server management
│   │   ├── __init__.py
│   │   ├── types.py       # MCPServerInfo
│   │   ├── manager.py     # MCPManager
│   │   └── nix_installer.py  # Nix-based MCP builder
│   │
│   └── client/            # Test clients
│       ├── __init__.py
│       └── text_client.py # CLI text client
│
├── pyproject.toml
├── flake.nix
├── PROJECT_STATE.md       # This file
├── AGENTS.md              # AI assistant context
└── README.md              # User documentation
```

---

## Changelog

### 2026-02-19
- **MCP Manager: update & delete support**
- Added `update_server()` to MCPManager — re-clones and rebuilds git-installed MCP servers
- Added `delete_server()` to MCPManager — unregisters and optionally removes clone directory
- Added `get_clone_dir()`, `update_remote_repo()`, `delete_repo_clone()` helpers in nix_installer
- Extracted `_parse_repo_name()` helper, refactored `get_remote_repo()` to use `get_clone_dir()`
- Exported new functions from `mcp/__init__.py`

### 2025-02-03
- **Phase 7: Space & MCP Management** implementation
- Added SpaceManager for managing multiple project workspaces
- Added MCPManager for system-level MCP server installation
- Implemented space switching (clears conversation history)
- Agent receives space context via `set_space()` method
- OpenCode agent generates `opencode.json` with MCP config
- Updated Session to coordinate spaces, MCPs, and agent
- Updated text client with space and MCP commands
- New config sections: `[spaces]`, `[mcp]`
- New WebSocket messages: `session_update`, `operation_progress`

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
