"""
Simple text-based WebSocket client for testing Agentil Agent Server.

Provides a REPL interface for sending text messages and receiving responses.
Optionally plays TTS audio output.
Supports space and MCP management commands.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from typing import Any

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    print("Error: websockets package not installed")
    print("Install with: pip install websockets")
    sys.exit(1)

# Audio playback support (optional)
try:
    import sounddevice as sd
    import soundfile as sf
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


# Client state for tracking available spaces and MCPs
class ClientState:
    """Tracks client-side state from server updates."""
    
    def __init__(self) -> None:
        self.spaces: list[dict] = []
        self.mcp_servers: list[dict] = []
        self.current_space: str | None = None
        self.tts_enabled: bool = True
        self.stt_enabled: bool = True
    
    def update_from_session(self, data: dict) -> None:
        """Update state from session_update message."""
        self.spaces = data.get("available_spaces", [])
        self.mcp_servers = data.get("mcp_servers", [])
        self.tts_enabled = data.get("tts_enabled", True)
        self.stt_enabled = data.get("stt_enabled", True)


class AudioPlayer:
    """Simple audio player for TTS output."""
    
    def __init__(self) -> None:
        self._pending_audio: bytes | None = None
        self._audio_format: str = "mp3"
    
    def set_pending_format(self, audio_format: str) -> None:
        """Set the format for the next audio chunk."""
        self._audio_format = audio_format.lower()
    
    def play_audio(self, audio_data: bytes) -> None:
        """Play audio data."""
        if not AUDIO_AVAILABLE:
            print("[Audio playback not available - install sounddevice/soundfile]")
            return
        
        if not audio_data:
            return
        
        try:
            # Decode audio using soundfile
            audio_buffer = io.BytesIO(audio_data)
            data, sample_rate = sf.read(audio_buffer)
            
            # Play audio (non-blocking)
            sd.play(data, sample_rate)
            # Don't wait - let it play in background
            
        except Exception as e:
            print(f"[Audio playback error: {e}]")
    
    def stop(self) -> None:
        """Stop any playing audio."""
        if AUDIO_AVAILABLE:
            sd.stop()


async def run_client(
    url: str,
    token: str,
    tts_enabled: bool = False,
) -> None:
    """
    Run the text client.
    
    Args:
        url: WebSocket URL (e.g., ws://localhost:8765/ws)
        token: Authentication token
        tts_enabled: Whether to enable TTS audio playback
    """
    # Add token to URL
    ws_url = f"{url}?token={token}"
    
    print(f"Connecting to {url}...")
    
    # Create audio player if TTS is enabled
    audio_player = AudioPlayer() if tts_enabled else None
    
    # Client state for tracking spaces and MCPs
    client_state = ClientState()
    
    if tts_enabled:
        if AUDIO_AVAILABLE:
            print("TTS audio playback enabled")
        else:
            print("Warning: TTS enabled but audio libraries not available")
            print("         Install sounddevice and soundfile for audio playback")
    
    try:
        async with websockets.connect(ws_url) as websocket:
            print("Connected!")
            
            # Wait for connected message
            msg = await websocket.recv()
            data = json.loads(msg)
            
            if data.get("type") == "connected":
                print(f"Session ID: {data.get('session_id')}")
                print(f"Server Version: {data.get('server_version')}")
            else:
                print(f"Unexpected message: {data}")
            
            # Send config for TTS setting
            await websocket.send(json.dumps({
                "type": "config",
                "tts_enabled": tts_enabled,
            }))
            
            print("\nReady! Type your message and press Enter.")
            print_help()
            print("-" * 40)
            
            # Start receiver task
            receiver_task = asyncio.create_task(
                receive_messages(websocket, audio_player, client_state)
            )
            
            # Track local TTS state
            local_tts_enabled = tts_enabled
            
            # Input loop
            try:
                while True:
                    # Read input
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, sys.stdin.readline
                    )
                    
                    if not line:
                        break
                    
                    line = line.strip()
                    
                    if not line:
                        continue
                    
                    # Handle commands
                    handled = await handle_command(
                        line, websocket, audio_player, client_state
                    )
                    
                    if handled == "quit":
                        break
                    elif handled:
                        # Command was handled
                        continue
                    
                    # Send text message
                    await websocket.send(json.dumps({
                        "type": "text",
                        "content": line,
                    }))
            
            except KeyboardInterrupt:
                pass
            finally:
                if audio_player:
                    audio_player.stop()
                receiver_task.cancel()
                try:
                    await receiver_task
                except asyncio.CancelledError:
                    pass
    
    except websockets.exceptions.InvalidStatusCode as e:
        if e.status_code == 4001:
            print("Error: Invalid authentication token")
        else:
            print(f"Connection error: {e}")
    except ConnectionRefusedError:
        print(f"Error: Could not connect to {url}")
        print("Is the server running?")
    except Exception as e:
        print(f"Error: {e}")


def print_help() -> None:
    """Print available commands."""
    print("Commands:")
    print("  /help             - Show this help")
    print("  /quit             - Exit client")
    print("  /cancel           - Cancel current operation")
    print("  /clear            - Clear conversation history")
    print("  Audio:")
    print("    /tts on|off     - Enable/disable TTS")
    print("    /stop           - Stop playing audio")
    print("  Spaces:")
    print("    /spaces         - List available spaces")
    print("    /space <id>     - Switch to space")
    print("  MCPs:")
    print("    /mcps           - List MCP servers")
    print("    /mcp on <id>    - Enable MCP server")
    print("    /mcp off <id>   - Disable MCP server")
    print("    /mcp install <url> - Install MCP from URL")


async def handle_command(
    line: str,
    websocket: Any,
    audio_player: AudioPlayer | None,
    client_state: ClientState,
) -> str | bool:
    """
    Handle a command.
    
    Returns:
        "quit" if should quit, True if command was handled, False otherwise
    """
    line_lower = line.lower()
    parts = line.split()
    
    if line_lower == "/quit":
        return "quit"
    
    elif line_lower == "/help":
        print_help()
        return True
    
    elif line_lower == "/tts on":
        await websocket.send(json.dumps({
            "type": "config",
            "tts_enabled": True,
        }))
        print("[TTS enabled]")
        return True
    
    elif line_lower == "/tts off":
        await websocket.send(json.dumps({
            "type": "config",
            "tts_enabled": False,
        }))
        print("[TTS disabled]")
        return True
    
    elif line_lower == "/stop":
        if audio_player:
            audio_player.stop()
        print("[Audio stopped]")
        return True
    
    elif line_lower == "/cancel":
        if audio_player:
            audio_player.stop()
        await websocket.send(json.dumps({"type": "cancel"}))
        print("[Cancelled]")
        return True
    
    elif line_lower == "/clear":
        await websocket.send(json.dumps({
            "type": "config",
            "clear_history": True,
        }))
        print("[History cleared]")
        return True
    
    elif line_lower == "/spaces":
        print("\nAvailable Spaces:")
        if not client_state.spaces:
            print("  (no spaces available)")
        else:
            for space in client_state.spaces:
                space_id = space.get("id", "?")
                name = space.get("name", space_id)
                desc = space.get("description", "")
                current = " (current)" if space_id == client_state.current_space else ""
                if desc:
                    print(f"  {space_id}: {name} - {desc}{current}")
                else:
                    print(f"  {space_id}: {name}{current}")
        return True
    
    elif line_lower.startswith("/space "):
        space_id = line[7:].strip()
        if not space_id:
            print("Usage: /space <id>")
            return True
        await websocket.send(json.dumps({
            "type": "config",
            "switch_space": space_id,
        }))
        print(f"[Switching to space: {space_id}]")
        return True
    
    elif line_lower == "/mcps":
        print("\nMCP Servers:")
        if not client_state.mcp_servers:
            print("  (no MCP servers installed)")
        else:
            for mcp in client_state.mcp_servers:
                name = mcp.get("name", "?")
                version = mcp.get("version", "")
                enabled = mcp.get("enabled", False)
                desc = mcp.get("description", "")
                status = "[ON]" if enabled else "[OFF]"
                version_str = f" v{version}" if version else ""
                if desc:
                    print(f"  {status} {name}{version_str} - {desc}")
                else:
                    print(f"  {status} {name}{version_str}")
        return True
    
    elif line_lower.startswith("/mcp on "):
        mcp_id = line[8:].strip()
        if not mcp_id:
            print("Usage: /mcp on <id>")
            return True
        # Build list of currently enabled MCPs + this one
        enabled = [m.get("name") for m in client_state.mcp_servers if m.get("enabled")]
        if mcp_id not in enabled:
            enabled.append(mcp_id)
        await websocket.send(json.dumps({
            "type": "config",
            "active_mcps": enabled,
        }))
        print(f"[Enabling MCP: {mcp_id}]")
        return True
    
    elif line_lower.startswith("/mcp off "):
        mcp_id = line[9:].strip()
        if not mcp_id:
            print("Usage: /mcp off <id>")
            return True
        # Build list of currently enabled MCPs - this one
        enabled = [m.get("name") for m in client_state.mcp_servers if m.get("enabled") and m.get("name") != mcp_id]
        await websocket.send(json.dumps({
            "type": "config",
            "active_mcps": enabled,
        }))
        print(f"[Disabling MCP: {mcp_id}]")
        return True
    
    elif line_lower.startswith("/mcp install "):
        url = line[13:].strip()
        if not url:
            print("Usage: /mcp install <url>")
            return True
        await websocket.send(json.dumps({
            "type": "config",
            "install_mcp_url": url,
        }))
        print(f"[Installing MCP from: {url}]")
        return True
    
    return False


async def receive_messages(
    websocket: WebSocketClientProtocol,
    audio_player: AudioPlayer | None = None,
    client_state: ClientState | None = None,
) -> None:
    """
    Receive and display messages from the server.
    
    Args:
        websocket: WebSocket connection
        audio_player: Optional audio player for TTS output
        client_state: Optional client state to update
    """
    current_response = ""
    pending_audio_format = "mp3"
    
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Binary audio data
                if audio_player is not None:
                    audio_player.play_audio(message)
                continue
            
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue
            
            msg_type = data.get("type")
            
            if msg_type == "status":
                state = data.get("state")
                if state == "processing":
                    print("\n[Processing...]", end="", flush=True)
                elif state == "idle" and current_response:
                    print()  # New line after response
                    current_response = ""
            
            elif msg_type == "session_update":
                # Update client state with spaces and MCPs
                if client_state:
                    client_state.update_from_session(data)
                    print(f"\n[Session updated: {len(client_state.spaces)} spaces, {len(client_state.mcp_servers)} MCPs]")
            
            elif msg_type == "operation_progress":
                operation = data.get("operation", "?")
                target = data.get("target", "")
                status = data.get("status", "")
                message_text = data.get("message", "")
                progress = data.get("progress")
                
                if status == "starting":
                    print(f"\n[{operation}] Starting: {target}")
                elif status == "in_progress":
                    progress_str = f" ({progress}%)" if progress is not None else ""
                    print(f"\n[{operation}] {message_text}{progress_str}")
                elif status == "complete":
                    print(f"\n[{operation}] Complete: {message_text or target}")
                elif status == "failed":
                    print(f"\n[{operation}] Failed: {message_text}")
            
            elif msg_type == "response_start":
                print("\nAssistant: ", end="", flush=True)
                current_response = ""
            
            elif msg_type == "response_delta":
                content = data.get("content", "")
                print(content, end="", flush=True)
                current_response += content
            
            elif msg_type == "response_end":
                if current_response:
                    print()  # Ensure newline
                print("-" * 40)
                current_response = ""
            
            elif msg_type == "transcript":
                content = data.get("content", "")
                final = data.get("final", False)
                if final:
                    print(f"\n[Transcript]: {content}")
            
            elif msg_type == "error":
                error_msg = data.get("message", "Unknown error")
                code = data.get("code", "")
                code_str = f" ({code})" if code else ""
                print(f"\n[Error{code_str}]: {error_msg}")
            
            elif msg_type == "audio_chunk":
                # Audio chunk metadata - prepare for binary data
                pending_audio_format = data.get("format", "mp3")
                if audio_player:
                    audio_player.set_pending_format(pending_audio_format)
                sentence = data.get("sentence", "")
                if sentence:
                    print(f"\n[TTS: {sentence[:50]}...]", flush=True)
            
            elif msg_type == "pong":
                # Pong response - ignore
                pass
    
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[Receiver error]: {e}")


def main() -> None:
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Text client for Agentil Agent Server"
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:8765/ws",
        help="WebSocket URL (default: ws://localhost:8765/ws)",
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Authentication token",
    )
    parser.add_argument(
        "--tts",
        action="store_true",
        help="Enable TTS audio output",
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_client(args.url, args.token, args.tts))
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
