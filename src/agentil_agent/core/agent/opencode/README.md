# OpenCode Agent - Architecture

This document describes the refactored architecture of the OpenCode agent backend.

## Overview

The bridge has been split into specialized modules, each with a single responsibility. This makes the code more maintainable, testable, and easier to understand.

## Module Structure

```
opencode/
├── __init__.py          # Public API exports
├── agent.py             # BaseAgent implementation (facade)
├── connection.py        # HTTP client & health checks
├── server.py            # Server lifecycle management
├── session.py           # Session CRUD operations
├── messages.py          # Message sending & parsing
├── streaming.py         # SSE streaming & text deltas
├── events.py            # Event parsing & types
└── exceptions.py        # Error types
```

## Module Responsibilities

### `agent.py` - BaseAgent Implementation
**Goal**: Provide a unified `BaseAgent` implementation

- Orchestrates all other components
- Delegates to specialized managers
- Adapts OpenCode HTTP/SSE to `BaseAgent`
- Handles context manager protocol (`__enter__`, `__exit__`)

**Key Methods**:
- `ensure_connection()` - Setup connection with auto-start
- `create_session()`, `list_sessions()`, etc. - Session management
- `send_message()` - Synchronous messaging
- `stream_response()` - Async streaming (now properly delta-based)

### `connection.py` - Connection Management
**Goal**: Handle HTTP client lifecycle and health checks

- Creates and manages `httpx.Client` instances (sync & async)
- Tracks connection state (`ConnectionState` enum)
- Performs health checks against `/global/health`
- Ensures proper cleanup on close

**Key Classes**:
- `ConnectionManager` - Manages HTTP clients and health checks
- `ConnectionState` - Enum for connection states

### `server.py` - Server Lifecycle
**Goal**: Manage the OpenCode server process

- Checks if OpenCode CLI is installed
- Starts/stops the server subprocess
- Configures working directory and environment
- Waits for server to be ready with timeout

**Key Classes**:
- `ServerManager` - Handles server process lifecycle

**Key Methods**:
- `is_opencode_installed()` - Check CLI availability
- `start_server()` - Start server subprocess
- `stop_server()` - Terminate server process

### `session.py` - Session Management
**Goal**: Handle session CRUD operations

- Create, list, get, delete sessions
- Track current active session
- Abort running sessions
- Ensure session exists (create if needed)

**Key Classes**:
- `SessionManager` - Session operations
- `Session` - Session data model

### `messages.py` - Message Operations
**Goal**: Send messages and parse responses

- Synchronous message sending (`/session/{id}/message`)
- Asynchronous message sending (`/session/{id}/prompt_async`)
- Extract text content from responses
- Parse message metadata (ID, role, model, etc.)

**Key Classes**:
- `MessageManager` - Message operations
- `Message` - Message metadata model

**Key Methods**:
- `send_message()` - Sync send and wait
- `send_message_async()` - Async send (no wait)
- `extract_text()` - Get text from response
- `get_message_info()` - Get message metadata

### `streaming.py` - SSE Streaming
**Goal**: Handle streaming responses with proper delta-based text yielding

This is the **most critical fix** - the old version incorrectly tried to track "seen text" and slice strings. The new version:

1. Subscribes to SSE events
2. Filters for `message.part.updated` events with `type: "text"`
3. **Directly yields the `delta` field** (already contains only new text)
4. Tracks completion via `session.idle` or `session.status` events

**Key Classes**:
- `StreamManager` - Manages SSE connections and streaming

**Key Methods**:
- `subscribe_events()` - Raw SSE subscription
- `stream_text_response()` - Stream text deltas for a session
- `stream_with_events()` - Stream text + event metadata


### `events.py` - Event Parsing
**Goal**: Parse and represent SSE events

- Parse raw SSE strings into structured objects
- Provide helper methods for event filtering
- Define event type constants
- Extract common event properties (session_id, message_id)

**Key Classes**:
- `SSEEvent` - Event data model with helpers
- `MessagePart` - Structured part data
- `EventType` - Event type constants
- `SessionStatus` - Status constants

**Key Methods**:
- `parse_sse_event()` - Parse raw SSE string
- `SSEEvent.is_for_session()` - Filter by session

### `exceptions.py` - Error Types
**Goal**: Centralize all custom exceptions

- `OpenCodeError` - Base exception
- `OpenCodeConnectionError` - Connection failures
- `OpenCodeNotInstalledError` - CLI not found
- `OpenCodeTimeoutError` - Operation timeout
- `OpenCodeSessionError` - Session errors

Makes error handling consistent and discoverable across the codebase.

## Data Flow

### Synchronous Message Flow
```
User Code
   ↓
OpenCodeAgent.send_message()
   ↓
MessageManager.send_message()
   ↓
POST /session/{id}/message
   ↓
Response with complete text
   ↓
MessageManager.extract_text()
   ↓
Return to user
```

### Async Streaming Flow
```
User Code
   ↓
OpenCodeAgent.stream_response()
   ↓
MessageManager.send_message_async()  (non-blocking)
   ↓
POST /session/{id}/prompt_async
   |
   ↓
StreamManager.stream_text_response()
   ↓
StreamManager.subscribe_events()
   ↓
GET /event (SSE connection)
   ↓
Filter: message.part.updated events
   ↓
Extract: delta field (incremental text)
   ↓
Yield to user (async generator)
```

## Usage Patterns

### Simple Usage (Facade)
```python
from agentil_agent.agent import create_agent
from agentil_agent.core.config import CoreConfig

config = CoreConfig()
agent = create_agent(config.agent.type, config)

async def main():
    await agent.initialize()
    session = await agent.create_session(title="Example")
    response = await agent.send_message(session.id, "Hello!")
    print(response.text)
    await agent.shutdown()
```

### Advanced Usage (Direct Managers)
```python
from agentil_agent.agent.opencode.streaming import StreamManager
from agentil_agent.agent.opencode.messages import MessageManager

# Use managers directly for fine-grained control
messages = MessageManager(base_url, timeout=60)
streams = StreamManager(base_url)

await messages.send_message_async(session_id, "Hello")
async for chunk in streams.stream_text_response(session_id):
    print(chunk, end="")
```

### Custom Event Handling
```python
async for event in streams.subscribe_events():
    if event.type == EventType.MESSAGE_PART_UPDATED:
        part = event.properties.get("part", {})
        # Custom processing
```

## Performance Considerations

1. **HTTP Client Reuse**: Clients are created once and reused
2. **Async Streaming**: Uses async generators for efficient streaming
3. **Event Filtering**: Filters events early to reduce processing
4. **Memory Efficient**: No accumulation of full text in streaming

## Future Enhancements

Possible additions that fit the architecture:

- `files.py` - File upload/download operations
- `tools.py` - Tool management and execution
- `models.py` - Model listing and configuration
- `history.py` - Conversation history management
- `cache.py` - Response caching
- `retry.py` - Automatic retry logic with exponential backoff

Each would be a new module with clear responsibilities.
