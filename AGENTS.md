# Agentil Agent - Agent Context

This file provides essential context for AI assistants working on this codebase.

## Project Overview

**Agentil Agent** is a WebSocket voice server and library for [OpenCode](https://opencode.ai), enabling speech-based and programmatic interaction with AI coding assistants. It provides:

- **WebSocket API**: Bidirectional audio/text streaming for voice clients
- **Library API**: `Session.create_headless()` + `Session.stream_text()` for in-process use (no WebSocket)
- **Speech-to-Text (STT)**: Whisper-based transcription
- **Text-to-Speech (TTS)**: MeloTTS for natural voice output
- **Space Management**: Project-based workspaces with isolated configurations
- **MCP Server Management**: Install, update, and delete MCP servers; enable per-space
- **Per-Assistant Configuration**: Each assistant has its own prompt, tools, MCP list, and model override
- **Flexible I/O**: Clients can send text OR audio, receive BOTH text AND audio
- **Client-Agnostic**: Designed to work with Flutter PWA, CLI, or any WebSocket client

## Architecture

### High-Level Design

```
+---------------------------------------------------------------------------+
|                       Agentil Agent Server (Python)                        |
|                                                                            |
|  +--------------+     +--------------+     +----------------------------+ |
|  |  WebSocket   |     |   Session    |     |      Agent Backend         | |
|  |   Server     |<--->|   Manager    |<--->|  (HTTP + SSE to OpenCode)  | |
|  |  (FastAPI)   |     |              |     +----------------------------+ |
|  +--------------+     +------+-------+                                    |
|                              |                                             |
|         +--------------------+--------------------+                       |
|         |                    |                    |                       |
|         v                    v                    v                       |
|    +---------+        +-----------+        +----------+                   |
|    |   STT   |        |   Space   |        |   TTS    |                   |
|    |(Whisper) |        |  Manager  |        | (MeloTTS)|                   |
|    +---------+        +-----+-----+        +----------+                   |
|                             |                                              |
|                       +-----+-----+                                       |
|                       |    MCP    |                                       |
|                       |  Manager  |                                       |
|                       +-----------+                                       |
|                                                                            |
+----------------------------------------------------------------------------+
         ^                                                    |
         |              WebSocket (WSS)                       |
         |   +---------------------------------------------+  |
         |   |  Client -> Server:                          |  |
         |   |  * Text messages                            |  |
         |   |  * Audio chunks (webm/opus)                 |  |
         |   |  * Control commands                         |  |
         +---+---------------------------------------------+--+
                                    |
         +--------------------------+--------------------------+
         |   Server -> Client:                                 |
         |   * Transcripts (streaming)                         |
         |   * AI Response text (streaming)                    |
         |   * TTS Audio chunks (streaming, per sentence)      |
         |   * Session updates (spaces, MCPs)                  |
         |   * Status/events                                   |
         +-----------------------------------------------------+
```

### Space & MCP Architecture

Spaces are project workspaces. Each space has its own working directory,
configuration, assistant definitions, and enabled MCP list.

- **SpaceManager** is system-level: creates, lists, deletes spaces.
- **MCPManager** is system-level: installs MCP servers once, enables per-space.
- **Agent receives space via setter**: `agent.set_space(space, mcp_manager)` allows context switching without agent restart.
- **Space switching clears history**: creates a new agent session (fresh conversation).
- **Server pool**: Each space gets its own OpenCode server on a dedicated port.
- **Per-assistant config**: Each assistant in `SpaceConfig.assistants` has its own `prompt`, `tools`, `enabled_mcps`, and `model` override.
- **`AssistantConfig.enabled_mcps`** controls which MCPs are active for that specific assistant.
- **`SpaceConfig.all_enabled_mcps`** is a computed property returning the deduplicated union across all assistants (used for MCP server registration).

### Flexible I/O Modes

| Input | Output | Use Case |
|-------|--------|----------|
| Text | Text | Traditional chat, testing, library use |
| Text | Text + Audio | Accessibility, hands-free |
| Audio | Text | Voice-to-text transcription |
| Audio | Text + Audio | Full voice assistant |

The **client decides** what to send and what to consume.

### Library Mode

CodeReport (and other consumers) can use agentil-agent as a Python library:

```python
session = Session.create_headless(config, space_manager, mcp_manager)
await session.switch_space(space_id)
async for chunk in session.stream_text("Analyze this code"):
    process(chunk)
await session.close()
```

No WebSocket, no network hop -- direct in-process calls.

## Directory Structure

```
agentil-agent/
+-- src/agentil_agent/
|   +-- __init__.py          # Package exports
|   +-- main.py              # CLI entry point (click-based)
|   +-- server.py            # FastAPI WebSocket server
|   +-- session.py           # Session manager (state machine, headless support)
|   +-- protocol.py          # WebSocket message types (Pydantic)
|   +-- config.py            # Pydantic configuration models
|   +-- audio.py             # Audio format conversion (ffmpeg)
|   +-- stt.py               # Speech-to-Text (Whisper)
|   +-- tts.py               # Text-to-Speech (MeloTTS)
|   |
|   +-- agent/               # Agent backend abstraction
|   |   +-- __init__.py      # Factory + registry
|   |   +-- base.py          # BaseAgent abstract class
|   |   +-- types.py         # AgentSession, AgentResponse
|   |   +-- exceptions.py    # Agent error types
|   |   +-- mock/            # Mock agent for testing
|   |   |   +-- agent.py
|   |   +-- opencode/        # OpenCode agent implementation
|   |       +-- __init__.py
|   |       +-- agent.py     # OpenCodeAgent with set_space(), server pool
|   |       +-- connection.py # HTTP connection manager
|   |       +-- events.py    # SSE event types
|   |       +-- exceptions.py
|   |       +-- messages.py  # Message formatting
|   |       +-- server.py    # OpenCode server process manager
|   |       +-- server_pool.py # Per-space server pool
|   |       +-- session.py   # OpenCode session management
|   |       +-- streaming.py # SSE stream processing
|   |
|   +-- space/               # Space management
|   |   +-- __init__.py      # Factory + exports
|   |   +-- base.py          # BaseSpace abstract class
|   |   +-- config.py        # SpaceConfig, AssistantConfig models
|   |   +-- manager.py       # SpaceManager (CRUD + lifecycle)
|   |   +-- types.py         # SpaceInfo, SpaceSummary
|   |   +-- exceptions.py    # Space error types
|   |   +-- directory/       # Directory-based space implementation
|   |       +-- __init__.py
|   |       +-- space.py     # DirectorySpace (workspace_link support)
|   |
|   +-- mcp/                 # MCP server management
|   |   +-- __init__.py      # Exports (MCPManager, helpers)
|   |   +-- types.py         # MCPServerInfo
|   |   +-- manager.py       # MCPManager (install, update, delete, registry)
|   |   +-- nix_installer.py # Nix-based MCP builder, clone helpers
|   |
|   +-- client/              # Test clients
|       +-- __init__.py
|       +-- text_client.py   # CLI text client (text in/out via WebSocket)
|
+-- pyproject.toml
+-- flake.nix
+-- AGENTS.md                # This file
+-- README.md
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
- `Session.create_headless()`: Factory for library use (no WebSocket)
- `Session.stream_text()`: Async generator for streaming agent responses

### 3. Protocol (`protocol.py`)

- Pydantic models for all WebSocket messages
- Client messages: `TextMessage`, `AudioStartMessage`, `AudioEndMessage`, `CancelMessage`, `ConfigMessage`
- Server messages: `ConnectedMessage`, `TranscriptMessage`, `ResponseDeltaMessage`, `AudioChunkMessage`, `SessionUpdateMessage`, `OperationProgressMessage`
- `parse_client_message()`: JSON to typed message conversion

### 4. Configuration (`config.py`)

- Uses **Pydantic v2** for validation
- Supports TOML config files
- Config sections: `ServerConfig`, `OpenCodeConfig`, `AgentBackendConfig`, `AssistantConfig`, `STTConfig`, `TTSConfig`, `AudioConfig`, `SpaceManagerConfig`, `MCPManagerConfig`
- Token generation and management
- Working directory resolution

### 5. Space Config (`space/config.py`)

- `AssistantConfig`: Per-assistant configuration -- `name`, `description`, `prompt`, `mode`, `tools: dict[str, bool]`, `enabled_mcps: list[str]`, `model: str | None`
- `SpaceConfig`: Holds `assistants: list[AssistantConfig]`, `default_assistant`, computed `all_enabled_mcps` property
- `SpaceConfig.load()`: Loads from `space.toml` with migration logic (legacy top-level `enabled_mcps` pushed into per-assistant lists)

### 6. Space Management (`space/`)

- `BaseSpace`: Abstract class defining space interface
- `DirectorySpace`: Filesystem-based implementation with `workspace_link` support (symlinks external directories as workspace)
- `SpaceManager`: System-level space CRUD, initialization, lifecycle
- Each space has: `workspace/` directory, `space.toml` config, assistant definitions

### 7. MCP Management (`mcp/`)

- `MCPManager`: System-level MCP server installation and tracking
- `install_from_url()`: Clone git repo + build with Nix
- `update_server()`: Re-clone and rebuild
- `delete_server()`: Unregister and optionally remove clone
- `register_local()`: Register existing executables
- MCP server registry persisted in `mcp-servers.json`
- Generate OpenCode-compatible MCP config per-assistant

### 8. Agent Backend (`agent/`)

- `BaseAgent` interface + `create_agent()` factory
- `set_space(space, mcp_manager)`: Injects space context, writes `opencode.json`
- OpenCode implementation in `agent/opencode/`:
  - `ServerPool`: Manages one OpenCode server per space (dedicated ports)
  - `ConnectionManager`: HTTP client for OpenCode API
  - `StreamManager`: SSE stream processing
  - `_write_opencode_json()`: Generates config with per-assistant tools, MCPs, and model override
  - `_register_mcp_servers()`: Dynamically registers MCPs via POST `/mcp` after connect

### 9. Audio Utilities (`audio.py`)

- `decode_audio_to_pcm()`: Convert incoming audio (webm/opus) to PCM for Whisper
- `encode_audio_to_mp3/opus/wav()`: Encode TTS output for streaming
- `split_text_into_sentences()`: Break response into TTS-able chunks
- Uses ffmpeg for format conversion

### 10. Speech-to-Text (`stt.py`)

- `STTEngine`: Whisper model wrapper
- `transcribe_audio()`: Transcribe PCM numpy array
- Lazy-loads model on first use
- CUDA compatibility checks with CPU fallback

### 11. Text-to-Speech (`tts.py`)

- `TTSEngine`: MeloTTS wrapper
- `synthesize()`: Generate audio from text
- Supports multiple speakers (EN-US, EN-BR, EN-AU)
- Lazy-loads model on first use

## WebSocket Protocol

### Client -> Server

```json
{"type": "text", "content": "Hello, help me with..."}
{"type": "audio_start", "format": "webm/opus"}
// ... binary audio frames ...
{"type": "audio_end"}
{"type": "cancel"}
{"type": "ping"}

// Configuration / space & MCP management
{
  "type": "config",
  "tts_enabled": true,
  "stt_enabled": true,
  "switch_space": "project-1",
  "install_mcp_url": "https://...",
  "active_mcps": ["mcp-1", "mcp-2"],
  "clear_history": true
}
```

### Server -> Client

```json
{"type": "connected", "session_id": "...", "server_version": "..."}

{"type": "session_update",
 "available_spaces": [{"id": "default", "name": "Default"}],
 "current_space_id": "default",
 "mcp_servers": [{"name": "rag-mcp", "enabled": true}]}

{"type": "operation_progress",
 "operation": "install_mcp", "target": "rag-mcp",
 "status": "in_progress", "progress": 50, "message": "Building..."}

{"type": "transcript", "content": "Hello", "final": true}
{"type": "response_start"}
{"type": "response_delta", "content": "Sure, I can help. "}
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
agentil-agent test-agent               # Test configured agent backend
```

## Configuration File

Location: `~/.config/agentil-agent/config.toml`

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
device = "auto"

[tts]
speaker = "EN-BR"
speed = 1.2
device = "auto"

[audio]
input_format = "webm/opus"
output_format = "mp3"
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
prompt = "You are a voice assistant..."
```

## Development Environment

### NixOS (Recommended)

```bash
nix develop  # Enters dev shell with Python 3.11, uv, ffmpeg, CUDA, opencode
```

### UV/pip

```bash
uv sync                        # Install dependencies
uv run agentil-agent serve     # Run the server
```

### Requirements

- Python 3.11 (specifically `>=3.11,<3.12`)
- ffmpeg (for audio format conversion)
- PyTorch with CUDA support (optional, for GPU acceleration)

## Common Issues & Gotchas

### 1. ffmpeg Required

Audio format conversion requires ffmpeg. Without it, audio input/output won't work.

### 2. CUDA Compatibility

The code includes CUDA compatibility checks because some GPUs have compute capabilities incompatible with certain PyTorch builds. Falls back to CPU if needed.

### 3. Token Authentication

All WebSocket connections require a valid token. Token is auto-generated on first run and saved to config.

### 4. Sentence-Level TTS

TTS is generated per sentence to reduce latency. The `split_text_into_sentences()` function uses simple heuristics.

### 5. LSP Errors in Consumers

Projects that import `agentil_agent` as a path dependency (e.g., `code-report`) will show LSP import errors. These resolve at runtime via `uv`.

## Testing

```bash
# Start server
agentil-agent serve

# In another terminal, connect with text client
agentil-agent client --token <token-from-server-output>

# Or use websocat
websocat "ws://localhost:8765/ws?token=<token>"
```

## Implementation Roadmap

### Phase 1: Project Setup & Foundation [COMPLETED]

- [x] Directory structure, pyproject.toml, flake.nix
- [x] TTS engine (MeloTTS), STT engine (Whisper)
- [x] Config system (Pydantic)

### Phase 2: OpenCode Integration [COMPLETED]

- [x] OpenCode HTTP client, SSE streaming
- [x] Session management, server auto-start

### Phase 3: Voice Controller [COMPLETED - REPLACED]

Original local state machine for CLI use, replaced by WebSocket session manager.
Kept: `stt.py`, `tts.py`, `agent/opencode/`, `config.py`.

### Phase 4: Sandbox Mode [COMPLETED - SIMPLIFIED]

Sandbox mode is now server-side configuration (working directory).

### Phase 5: WebSocket Server [COMPLETED]

- [x] FastAPI + WebSocket server with token auth
- [x] Session manager (replaces controller), reconnection support
- [x] Text input/output, streaming responses
- [x] Audio input (STT): receive, decode, transcribe, stream transcripts
- [x] Audio output (TTS): generate, encode, stream per-sentence
- [x] Server config section (host, port, token, audio format)

### Phase 6: CLI Test Client [COMPLETED]

- [x] WebSocket client with token auth, text REPL
- [x] TTS audio playback support
- [x] Space commands (`/spaces`, `/space <id>`)
- [x] MCP commands (`/mcps`, `/mcp on/off`, `/mcp install`)

### Phase 7: Space & MCP Management [COMPLETED]

- [x] `BaseSpace` abstract class, `DirectorySpace` (filesystem-based, workspace_link)
- [x] `SpaceManager` for multi-space CRUD and lifecycle
- [x] Space configuration (`space.toml`), auto-create default space
- [x] `MCPManager`: install from git+nix, register local, update, delete
- [x] MCP server registry (`mcp-servers.json`)
- [x] `set_space()` on `BaseAgent` / `OpenCodeAgent`
- [x] `opencode.json` generation with MCP and assistant config
- [x] Session integration: `switch_space()`, `session_update` messages
- [x] Server lifespan initializes managers
- [x] Per-assistant `enabled_mcps` and `model` override in `AssistantConfig`
- [x] `SpaceConfig.all_enabled_mcps` computed property (union across assistants)
- [x] Migration logic for legacy top-level `enabled_mcps` in `space.toml`
- [ ] End-to-end testing with real MCP servers
- [ ] Space creation via WebSocket API
- [ ] Better progress reporting for MCP install

### Phase 8: Polish & Production Ready [PLANNED]

- [ ] Error handling and recovery
- [ ] Graceful shutdown
- [ ] Logging and monitoring
- [ ] Rate limiting
- [ ] Audio format negotiation
- [ ] Performance optimization
- [ ] HTTPS/WSS support documentation

## Related Links

- [OpenCode](https://opencode.ai) - The AI coding assistant this bridges to
- [OpenCode Docs](https://opencode.ai/docs) - OpenCode documentation
- [MeloTTS](https://github.com/myshell-ai/MeloTTS) - TTS engine
- [OpenAI Whisper](https://github.com/openai/whisper) - STT engine
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
