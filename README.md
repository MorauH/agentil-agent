# Agentil Agent

Voice interface for [OpenCode](https://opencode.ai) - interact with the AI coding assistant using your voice.

## Features

- **Speech-to-Text (STT)**: Whisper-based speech recognition
- **Text-to-Speech (TTS)**: MeloTTS for natural voice output
- **Sandbox Mode**: Dedicated workspace with voice-optimized assistant (default)
- **Local Mode**: Standard OpenCode behavior with voice I/O for project work
- **Push-to-Talk**: Button-based voice input
- **Continuous Listening**: Always-on voice input mode
- **Streaming TTS**: Hear responses as they're generated
- **Interruptible**: Start speaking to stop TTS playback

## Status

**Phase 4: Sandbox Mode & Voice-Assistant Agent** - Next

See [PROJECT_STATE.md](./PROJECT_STATE.md) for the full implementation roadmap.

## Operating Modes

### Sandbox Mode (Default)

When you run `agentil-agent` without arguments, it operates in sandbox mode:
- Uses a dedicated workspace at `~/.config/agentil-agent/workspace/`
- Runs a voice-optimized assistant agent (concise, TTS-friendly responses)
- Great for general assistance, note-taking, quick questions
- Not tied to any specific project

### Local Mode

Use `--local` or `--project <path>` to work on a specific project:
- Uses your current directory or specified project path
- Uses the project's `opencode.json` configuration
- Standard OpenCode behavior, just with voice I/O
- Best for coding tasks in a specific repository

## Installation

### Prerequisites

- Python 3.11+
- [OpenCode](https://opencode.ai/docs/) installed and available in PATH
- A microphone and speakers

### Using Nix (Recommended for NixOS)

```bash
cd agentil-agent
nix develop
```

This will set up a complete development environment with all dependencies.

### Using UV

```bash
cd agentil-agent
uv sync
```

### Using pip

```bash
cd agentil-agent
pip install -e .
```

## Usage

### Quick Start

```bash
# Start voice interface (sandbox mode, PTT)
agentil-agent

# Check installation and server status
agentil-agent check

# Start in continuous listening mode
agentil-agent run --mode continuous
```

### Operating Mode Selection

```bash
# Sandbox mode (default) - dedicated workspace, voice-optimized agent
agentil-agent

# Local mode - use current directory
agentil-agent --local
# or
agentil-agent --here

# Project mode - use specific directory
agentil-agent --project /path/to/project
```

### Voice Modes

```bash
# Push-to-talk (default) - hold SPACE to speak
agentil-agent run --mode ptt

# Continuous listening - always listening
agentil-agent run --mode continuous

# Custom PTT key
agentil-agent run --ptt-key f1
```

### Testing Components

```bash
# Test Text-to-Speech
agentil-agent test-tts

# Test Speech-to-Text (records for 10 seconds by default)
agentil-agent test-stt
agentil-agent test-stt --duration 5

# Test OpenCode bridge connection
agentil-agent test-bridge

# Test with custom prompt
agentil-agent test-bridge -p "What is 2+2?"
```

## Configuration

Configuration file location: `~/.config/agentil-agent/config.toml`

### Generate Default Config

```bash
agentil-agent config-init ~/.config/agentil-agent/config.toml
```

### Configuration Options

```toml
[opencode]
host = "127.0.0.1"
port = 4096
auto_start = true  # Start OpenCode server if not running

[stt]
model = "base"  # tiny, base, small, medium, large
energy_threshold = 1000
phrase_timeout = 3.0
device = "default"  # Microphone device

[tts]
speaker = "EN-BR"  # EN-US, EN-BR, EN-AU, EN-Default
speed = 1.2
device = "auto"  # cpu, cuda, mps, auto

[voice]
mode = "ptt"  # ptt, continuous
ptt_key = "space"
interrupt_on_speech = true
streaming_tts = true

# Sandbox configuration (Phase 4)
[sandbox]
path = "~/.config/agentil-agent/workspace"

# Voice assistant agent (Phase 4)
[agent]
name = "voice-assistant"
prompt = """
You are a voice assistant. Keep responses concise and conversational.
Avoid markdown formatting. Use natural spoken language.
"""
```

## Development

### Project Structure

```
agentil-agent/
├── src/agentil_agent/
│   ├── __init__.py      # Package exports
│   ├── main.py          # CLI entry point
│   ├── config.py        # Configuration management
│   ├── tts.py           # Text-to-Speech (MeloTTS)
│   ├── stt.py           # Speech-to-Text (Whisper)
│   ├── bridge.py        # OpenCode HTTP client + SSE streaming
│   ├── controller.py    # Voice state machine orchestration
│   └── keyboard.py      # PTT keyboard handling
├── pyproject.toml       # Python project config
├── flake.nix            # Nix development environment
├── PROJECT_STATE.md     # Implementation roadmap
├── AGENTS.md            # AI assistant context
└── README.md            # This file
```

### Running Module Tests

```bash
# Test TTS module directly
python -m agentil_agent.tts

# Test STT module directly
python -m agentil_agent.stt

# Test OpenCode bridge directly
python -m agentil_agent.bridge
```

## Roadmap

- [x] Phase 1: Project Setup & Foundation
- [x] Phase 2: OpenCode Integration
- [x] Phase 3: Voice Controller
- [ ] Phase 4: Sandbox Mode & Voice-Assistant Agent (current)
- [ ] Phase 5: Web Interface
- [ ] Phase 6: Polish & UX
- [ ] Phase 7: Documentation & Release

### Future Improvements

- Wake word detection (hands-free activation)
- Audio ducking (lower TTS during listening)
- Voice commands for agent switching
- Home server deployment with web UI

## License

MIT
