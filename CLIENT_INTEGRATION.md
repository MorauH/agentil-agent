# Agentil Agent - Client Integration Guide

This document describes how to build a client application that connects to the Agentil Agent WebSocket server.

## Overview

The Agentil Agent server provides:
- **Voice interaction** - Speech-to-text and text-to-speech
- **Text interaction** - Send/receive text messages
- **Space management** - Project workspaces with isolated configurations
- **MCP management** - Install and enable MCP servers per-space

## Connection

### WebSocket Endpoint

```
ws://<host>:<port>/ws?token=<auth_token>
```

- **Default URL**: `ws://localhost:8765/ws`
- **Authentication**: Pass the token as a query parameter
- **Protocol**: Standard WebSocket (RFC 6455)

### Connection Example (JavaScript)

```javascript
const token = "your-auth-token";
const ws = new WebSocket(`ws://localhost:8765/ws?token=${token}`);

ws.onopen = () => console.log("Connected");
ws.onclose = (e) => console.log(`Disconnected: ${e.code} ${e.reason}`);
ws.onerror = (e) => console.error("WebSocket error:", e);
ws.onmessage = (event) => {
  if (event.data instanceof Blob) {
    // Binary audio data
    handleAudioData(event.data);
  } else {
    // JSON message
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  }
};
```

### Connection Example (Dart/Flutter)

```dart
import 'package:web_socket_channel/web_socket_channel.dart';

final channel = WebSocketChannel.connect(
  Uri.parse('ws://localhost:8765/ws?token=$token'),
);

channel.stream.listen(
  (data) {
    if (data is List<int>) {
      // Binary audio data
      handleAudioData(Uint8List.fromList(data));
    } else {
      // JSON message
      final msg = jsonDecode(data as String);
      handleMessage(msg);
    }
  },
  onError: (error) => print('Error: $error'),
  onDone: () => print('Connection closed'),
);
```

## Message Protocol

All JSON messages have a `type` field that identifies the message type.

### Client -> Server Messages

#### 1. Text Message
Send text input to the assistant.

```json
{
  "type": "text",
  "content": "Hello, can you help me with..."
}
```

#### 2. Audio Start
Signal the start of an audio stream (for voice input).

```json
{
  "type": "audio_start",
  "format": "webm/opus",
  "sample_rate": 16000
}
```

Supported formats: `webm/opus`, `ogg/opus`, `mp3`, `wav`, `pcm`

#### 3. Audio Data
After sending `audio_start`, send raw binary audio frames directly (not JSON).

```javascript
// JavaScript example
ws.send(audioChunk); // ArrayBuffer or Blob
```

#### 4. Audio End
Signal the end of audio input. Triggers transcription and processing.

```json
{
  "type": "audio_end"
}
```

#### 5. Cancel
Cancel the current operation (stops response generation and TTS).

```json
{
  "type": "cancel"
}
```

#### 6. Config
Update runtime settings, manage spaces, and control MCPs.

```json
{
  "type": "config",
  
  // Audio settings
  "tts_enabled": true,
  "stt_enabled": true,
  
  // Space management
  "switch_space": "project-1",
  
  // MCP management
  "install_mcp_url": "https://github.com/user/mcp-server",
  "active_mcps": ["mcp-server-1", "mcp-server-2"],
  
  // History management
  "clear_history": true
}
```

All fields are optional. Only include the settings you want to change.

| Field | Type | Description |
|-------|------|-------------|
| `tts_enabled` | boolean | Enable/disable text-to-speech audio output |
| `stt_enabled` | boolean | Enable/disable speech-to-text processing |
| `switch_space` | string | Space ID to switch to |
| `install_mcp_url` | string | Git URL of MCP server to install |
| `active_mcps` | string[] | List of MCP IDs to enable in current space |
| `clear_history` | boolean | Clear conversation history (creates new session) |

#### 7. Ping
Keepalive message. Server responds with `pong`.

```json
{
  "type": "ping"
}
```

### Server -> Client Messages

#### 1. Connected
Sent immediately after successful connection.

```json
{
  "type": "connected",
  "session_id": "abc123def456",
  "server_version": "0.3.0"
}
```

#### 2. Session Update
Sent after connection and whenever spaces/MCPs change. Contains current session state.

```json
{
  "type": "session_update",
  "available_spaces": [
    {
      "id": "default",
      "name": "Default",
      "description": "Default workspace"
    },
    {
      "id": "project-1",
      "name": "My Project",
      "description": "Web app project"
    }
  ],
  "current_space_id": "project-1",
  "mcp_servers": [
    {
      "name": "rag-mcp",
      "version": "1.0.0",
      "enabled": true,
      "description": "RAG capabilities"
    },
    {
      "name": "github-mcp",
      "version": "2.1.0",
      "enabled": false,
      "description": "GitHub integration"
    }
  ],
  "tts_enabled": true,
  "stt_enabled": true
}
```

Use this to populate UI elements like space selectors and MCP toggles.

#### 3. Operation Progress
Progress updates for long-running operations (MCP installation, space initialization).

```json
{
  "type": "operation_progress",
  "operation": "install_mcp",
  "target": "rag-mcp",
  "status": "in_progress",
  "progress": 50,
  "message": "Building with nix..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `operation` | string | Operation type: `install_mcp`, `initialize_space` |
| `target` | string | Target identifier (MCP name, space ID) |
| `status` | string | `starting`, `in_progress`, `complete`, `failed` |
| `progress` | number? | Progress percentage (0-100), optional |
| `message` | string? | Human-readable status message |

#### 4. Status
Session state update.

```json
{
  "type": "status",
  "state": "processing"
}
```

States:
- `idle` - Ready for input
- `listening` - Processing audio input (STT)
- `processing` - Waiting for AI response
- `speaking` - Generating/streaming TTS audio
- `error` - Error state

#### 5. Transcript
Speech-to-text result (when audio input is used).

```json
{
  "type": "transcript",
  "content": "Hello can you help me",
  "final": true
}
```

- `final`: `true` for final transcription, `false` for interim results

#### 6. Response Start
Signals the beginning of AI response streaming.

```json
{
  "type": "response_start"
}
```

#### 7. Response Delta
Incremental AI response text (streaming).

```json
{
  "type": "response_delta",
  "content": "Sure, I can "
}
```

Accumulate these to build the full response.

#### 8. Response End
Signals the end of AI response.

```json
{
  "type": "response_end"
}
```

#### 9. Audio Stream Start
Signals the beginning of TTS audio output.

```json
{
  "type": "audio_stream_start",
  "format": "mp3",
  "sample_rate": 24000
}
```

#### 10. Audio Chunk
Metadata for incoming audio data. Binary audio follows this message.

```json
{
  "type": "audio_chunk",
  "format": "mp3",
  "sentence": "Sure, I can help you with that.",
  "chunk_index": 0,
  "is_last": false
}
```

**Important**: The actual audio data is sent as a separate binary WebSocket frame immediately after this JSON message.

#### 11. Audio Stream End
Signals the end of TTS audio output.

```json
{
  "type": "audio_stream_end"
}
```

#### 12. Error
Error notification.

```json
{
  "type": "error",
  "message": "Something went wrong",
  "code": "processing_error",
  "fatal": false
}
```

Error codes:
- `parse_error` - Invalid JSON message
- `unknown_type` - Unknown message type
- `processing_error` - Error during AI processing
- `audio_processing_error` - Error during audio processing
- `space_switch_error` - Error switching spaces
- `mcp_install_error` - Error installing MCP
- `mcp_unavailable` - MCP manager not available

- `fatal`: If `true`, the connection should be closed

#### 13. Pong
Response to ping.

```json
{
  "type": "pong"
}
```

## Typical Message Flow

### Text Input Flow

```
Client                          Server
  |                               |
  |------- text message --------->|
  |                               |
  |<------ status: processing ----|
  |<------ response_start --------|
  |<------ response_delta --------|  (multiple)
  |<------ response_delta --------|
  |<------ response_end ----------|
  |<------ audio_stream_start ----|  (if TTS enabled)
  |<------ audio_chunk -----------|
  |<------ [binary audio] --------|
  |<------ audio_chunk -----------|  (per sentence)
  |<------ [binary audio] --------|
  |<------ audio_stream_end ------|
  |<------ status: idle ----------|
  |                               |
```

### Voice Input Flow

```
Client                          Server
  |                               |
  |------- audio_start ---------->|
  |------- [binary audio] ------->|  (multiple chunks)
  |------- [binary audio] ------->|
  |------- audio_end ------------>|
  |                               |
  |<------ status: listening -----|
  |<------ transcript (final) ----|
  |<------ status: processing ----|
  |<------ response_start --------|
  |<------ response_delta --------|
  |         ... (same as text)    |
```

## Audio Handling

### Input Audio (Client -> Server)

- **Recommended format**: `webm/opus` (best browser support)
- **Sample rate**: 16000 Hz (for Whisper STT)
- **Channels**: Mono preferred

Browser example using MediaRecorder:

```javascript
const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
const mediaRecorder = new MediaRecorder(stream, {
  mimeType: 'audio/webm;codecs=opus'
});

// Start recording
ws.send(JSON.stringify({ type: 'audio_start', format: 'webm/opus' }));
mediaRecorder.start(100); // Send chunks every 100ms

mediaRecorder.ondataavailable = (event) => {
  if (event.data.size > 0) {
    ws.send(event.data);
  }
};

// Stop recording
mediaRecorder.stop();
ws.send(JSON.stringify({ type: 'audio_end' }));
```

### Output Audio (Server -> Client)

- **Default format**: `mp3`
- **Sample rate**: 24000 Hz
- Audio is streamed per-sentence for low latency

Browser playback example:

```javascript
const audioContext = new AudioContext({ sampleRate: 24000 });
const audioQueue = [];
let isPlaying = false;

function handleAudioData(blob) {
  audioQueue.push(blob);
  if (!isPlaying) playNext();
}

async function playNext() {
  if (audioQueue.length === 0) {
    isPlaying = false;
    return;
  }
  
  isPlaying = true;
  const blob = audioQueue.shift();
  const arrayBuffer = await blob.arrayBuffer();
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  source.onended = playNext;
  source.start();
}
```

## Error Handling

### Connection Errors

| Close Code | Meaning |
|------------|---------|
| 4001 | Invalid authentication token |
| 1000 | Normal closure |
| 1006 | Abnormal closure (network issue) |

### Runtime Errors

Handle `error` messages gracefully:

```javascript
function handleMessage(msg) {
  if (msg.type === 'error') {
    console.error(`Error: ${msg.message} (${msg.code})`);
    if (msg.fatal) {
      // Reconnect or notify user
    }
  }
}
```

## Best Practices

1. **Send config on connect**: Set `tts_enabled` based on user preference immediately after receiving `connected`.

2. **Handle reconnection**: Implement exponential backoff for reconnection attempts.

3. **Buffer audio output**: Queue audio chunks and play sequentially to avoid gaps.

4. **Show streaming text**: Display `response_delta` messages as they arrive for responsive UI.

5. **Implement cancel**: Allow users to cancel long responses with the `cancel` message.

6. **Ping/pong keepalive**: Send periodic pings to detect connection issues.

```javascript
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  }
}, 30000);
```

## State Machine

Recommended client states based on server `status` messages:

```
                    +-------+
                    | IDLE  |<-----------------+
                    +-------+                  |
                        |                      |
            text/audio_end                     |
                        |                      |
                        v                      |
                  +-----------+                |
                  | LISTENING |  (audio only)  |
                  +-----------+                |
                        |                      |
                   transcript                  |
                        |                      |
                        v                      |
                  +------------+               |
                  | PROCESSING |               |
                  +------------+               |
                        |                      |
                  response_start               |
                        |                      |
                        v                      |
                  +----------+                 |
                  | SPEAKING |                 |
                  +----------+                 |
                        |                      |
               response_end/                   |
               audio_stream_end                |
                        |                      |
                        +----------------------+
```

## HTTP Endpoints

The server also exposes REST endpoints:

- `GET /health` - Health check
- `GET /info` - Server configuration info

```json
// GET /info response
{
  "version": "0.3.0",
  "stt": { "model": "base" },
  "tts": { "speaker": "EN-BR", "speed": 1.2 },
  "audio": { "input_format": "webm/opus", "output_format": "mp3" }
}
```

## MCP Server Management

MCP servers extend the assistant with additional tools (e.g., RAG, GitHub
integration). Clients manage MCP servers through the `config` WebSocket message.

### Installing an MCP Server

Send a config message with `install_mcp_url` to install a new MCP server from
a git repository:

```json
{
  "type": "config",
  "install_mcp_url": "https://github.com/user/my-mcp-server"
}
```

The server sends `operation_progress` messages during installation.

### Enabling/Disabling MCP Servers Per-Space

Use `active_mcps` to set which installed MCP servers are enabled in the current
space:

```json
{
  "type": "config",
  "active_mcps": ["rag-mcp", "github-mcp"]
}
```

MCP servers not in the list are disabled for the current space. The server
handles all backend registration automatically.

### Viewing MCP Status

The `session_update` message (sent on connect and after changes) includes the
current MCP server list with enabled/disabled status. Use this to populate
toggles or settings UI.
