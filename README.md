# Agentil

Agentic assistant base with speech-based support.

## Features

- **Abstract Agent** - Use OpenCode, Langchain agents or inject your own solution
- **Speech-to-Text (STT)** - Whisper-based local transcription
- **Text-to-Speech (TTS)** - MeloTTS for natural voice output, locally generated
- **Space Management** - Project-based workspaces with isolated configurations
- **MCP Server Management** - Install, update, and delete MCP servers per-space

## Requirements

- Python 3.11 (specifically `>=3.11,<3.12`)
- ffmpeg (for audio format conversion)
- [OpenCode](https://opencode.ai/docs/) installed and available in PATH


# Agentil Server/Client

Voice assistant built on the Agentil-base

## Additional Features

- **WebSocket API** - Bidirectional audio/text streaming
- **Flexible I/O** - Clients can send text OR audio, receive BOTH text AND audio
- **Space Management** - Project-based workspaces with isolated configurations
- **MCP Server Management** - Install, update, and delete MCP servers per-space

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
agentil-server config-init
```

This creates `~/.config/agentil-server/config.toml` with a generated auth token.

### 3. Start the Server

```bash
agentil-server serve
```

The server will display:
```
Server starting on http://0.0.0.0:8765
Authentication token: <your-token>
```

### 4. Connect with the CLI Client

In a new terminal:

```bash
agentil-client --token <your-token>
```

You're now connected! Type messages and press Enter to chat with OpenCode.

## CLI Reference

### Server Commands

```bash
# Start server with defaults
agentil-server serve

# Custom host/port
agentil-server serve --host 127.0.0.1 --port 9000

# Debug logging
agentil-server serve -l DEBUG

# Use specific config file
agentil-server serve -c /path/to/config.toml
```

### Client Commands

```bash
# Connect to server
agentil-client --token <token>

# Connect with TTS audio playback
agentil-client --token <token> --tts

# Connect to custom URL
agentil-client --url ws://192.168.1.100:8765/ws --token <token>
```

### Configuration Commands

```bash
# Generate default config
agentil-server config-init

# Overwrite existing config
agentil-server config-init --force

# Show current config
agentil-server config-show

# Show/regenerate auth token
agentil-server token
agentil-server token --regenerate
```

### Testing Commands

```bash
# Check system dependencies
agentil-server check

# Test TTS
agentil-server test-tts
agentil-server test-tts --text "Hello world"

# Test agent backend
agentil-server test-agent
agentil-server test-agent -p "What is 2+2?"
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

Config file location: `~/.config/agentil-server/config.toml`

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
device = "auto"  # cpu, cuda, mps, auto

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
2. Check OpenCode can start manually: `opencode .`, and test prompt
3. Verify `[agent.opencode]` settings in config

### CUDA Errors

If you see CUDA-related errors, the code will fall back to CPU. To force CPU:

```toml
[stt]
device = "cpu"

[tts]
device = "cpu"
```

## License

MIT
