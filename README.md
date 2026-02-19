# Agentil Agent

WebSocket voice server for [OpenCode](https://opencode.ai) - enables speech-based interaction with the AI coding assistant.

## Features

- **WebSocket API** - Bidirectional audio/text streaming
- **Speech-to-Text (STT)** - Whisper-based transcription
- **Text-to-Speech (TTS)** - MeloTTS for natural voice output
- **Flexible I/O** - Clients can send text OR audio, receive BOTH text AND audio
- **Space Management** - Project-based workspaces with isolated configurations
- **MCP Server Management** - Install, update, and delete MCP servers per-space

## Requirements

- Python 3.11 (specifically `>=3.11,<3.12`)
- ffmpeg (for audio format conversion)
- [OpenCode](https://opencode.ai/docs/) installed and available in PATH

## Quick Start

### 1. Enter Development Environment

**NixOS (Recommended):**
```bash
cd agentil-agent
nix develop
```

**Using UV:**
```bash
cd agentil-agent
uv sync
```

### 2. Generate Configuration

```bash
agentil-agent config-init
```

This creates `~/.config/agentil-agent/config.toml` with a generated auth token.

### 3. Start the Server

```bash
agentil-agent serve
```

The server will display:
```
Server starting on http://0.0.0.0:8765
Authentication token: <your-token>
```

### 4. Connect with the CLI Client

In a new terminal:

```bash
agentil-agent client --token <your-token>
```

You're now connected! Type messages and press Enter to chat with OpenCode.

## CLI Reference

### Server Commands

```bash
# Start server with defaults
agentil-agent serve

# Custom host/port
agentil-agent serve --host 127.0.0.1 --port 9000

# Debug logging
agentil-agent serve -l DEBUG

# Use specific config file
agentil-agent serve -c /path/to/config.toml
```

### Client Commands

```bash
# Connect to server
agentil-agent client --token <token>

# Connect with TTS audio playback
agentil-agent client --token <token> --tts

# Connect to custom URL
agentil-agent client --url ws://192.168.1.100:8765/ws --token <token>
```

### Configuration Commands

```bash
# Generate default config
agentil-agent config-init

# Overwrite existing config
agentil-agent config-init --force

# Show current config
agentil-agent config-show

# Show/regenerate auth token
agentil-agent token
agentil-agent token --regenerate
```

### Testing Commands

```bash
# Check system dependencies
agentil-agent check

# Test TTS
agentil-agent test-tts
agentil-agent test-tts --text "Hello world"

# Test agent backend
agentil-agent test-agent
agentil-agent test-agent -p "What is 2+2?"
```

## Client Commands (In-Session)

Once connected with `agentil-agent client`, these commands are available:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/quit` | Exit client |
| `/cancel` | Cancel current operation |
| `/clear` | Clear conversation history |
| `/tts on\|off` | Enable/disable TTS |
| `/stop` | Stop playing audio |
| `/spaces` | List available spaces |
| `/space <id>` | Switch to space |
| `/mcps` | List MCP servers |
| `/mcp on <id>` | Enable MCP server |
| `/mcp off <id>` | Disable MCP server |
| `/mcp install <url>` | Install MCP from git URL |

## Configuration

Config file location: `~/.config/agentil-agent/config.toml`

### Minimal Config

```toml
[server]
host = "0.0.0.0"
port = 8765
token = "your-secret-token"

[agent]
type = "opencode"

[agent.opencode]
auto_start = true
```

### Full Config Example

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
auto_start = true  # Start OpenCode if not running
timeout = 30.0

[stt]
model = "base"  # tiny, base, small, medium, large
device = "auto"  # cpu, cuda, auto

[tts]
speaker = "EN-BR"  # EN-US, EN-BR, EN-AU, EN-Default
speed = 1.2
device = "auto"  # cpu, cuda, mps, auto

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
prompt = """
You are a voice assistant. Keep responses concise and conversational.
Avoid markdown formatting. Use natural spoken language.
"""
```

## Troubleshooting

### "ffmpeg not found"

Audio conversion requires ffmpeg:

```bash
# NixOS
nix-shell -p ffmpeg

# Debian/Ubuntu
apt install ffmpeg

# macOS
brew install ffmpeg
```

### "Could not connect to server"

1. Check the server is running: `agentil-agent serve`
2. Verify the token matches
3. Check firewall allows the port (default: 8765)

### "Agent error" / OpenCode not starting

1. Ensure OpenCode is installed: `opencode --version`
2. Check OpenCode can start manually: `opencode serve`
3. Verify `[agent.opencode]` settings in config

### CUDA Errors

If you see CUDA-related errors, the code will fall back to CPU. To force CPU:

```toml
[stt]
device = "cpu"

[tts]
device = "cpu"
```

## Development

### Running from Source

```bash
# With nix
nix develop -c python -m agentil_agent.main serve

# With UV
uv run agentil-agent serve

# Direct Python
python -m agentil_agent.main serve
```

### Testing Modules

```bash
# Test TTS module
python -m agentil_agent.tts

# Test STT module
python -m agentil_agent.stt

# Test config loading
python -m agentil_agent.config
```

### Project Structure

```
agentil-agent/
├── src/agentil_agent/
│   ├── main.py          # CLI entry point
│   ├── server.py        # WebSocket server (FastAPI)
│   ├── session.py       # Session manager
│   ├── protocol.py      # WebSocket message types
│   ├── config.py        # Configuration (Pydantic)
│   ├── stt.py           # Speech-to-Text (Whisper)
│   ├── tts.py           # Text-to-Speech (MeloTTS)
│   ├── audio.py         # Audio format conversion
│   ├── agent/           # Agent backends (OpenCode, mock)
│   ├── space/           # Space management
│   ├── mcp/             # MCP server management
│   └── client/          # Test clients
├── pyproject.toml
├── flake.nix
```

## WebSocket Protocol

For building custom clients, see [CLIENT_INTEGRATION.md](./CLIENT_INTEGRATION.md).

### Quick Protocol Overview

**Connect:** `ws://host:port/ws?token=<token>`

**Send text:**
```json
{"type": "text", "content": "Hello"}
```

**Receive response (streaming):**
```json
{"type": "response_start"}
{"type": "response_delta", "content": "Hi "}
{"type": "response_delta", "content": "there!"}
{"type": "response_end"}
```

## License

MIT
