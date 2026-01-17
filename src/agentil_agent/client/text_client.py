"""
Simple text-based WebSocket client for testing Agentil Agent Server.

Provides a REPL interface for sending text messages and receiving responses.
Optionally plays TTS audio output.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
from pathlib import Path
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
            print("Commands: /quit, /tts on, /tts off, /cancel, /stop")
            print("-" * 40)
            
            # Start receiver task
            receiver_task = asyncio.create_task(
                receive_messages(websocket, audio_player)
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
                    if line.lower() == "/quit":
                        break
                    elif line.lower() == "/tts on":
                        await websocket.send(json.dumps({
                            "type": "config",
                            "tts_enabled": True,
                        }))
                        local_tts_enabled = True
                        # Create audio player if not exists
                        if audio_player is None:
                            audio_player = AudioPlayer()
                        print("[TTS enabled]")
                        continue
                    elif line.lower() == "/tts off":
                        await websocket.send(json.dumps({
                            "type": "config",
                            "tts_enabled": False,
                        }))
                        local_tts_enabled = False
                        print("[TTS disabled]")
                        continue
                    elif line.lower() == "/stop":
                        if audio_player:
                            audio_player.stop()
                        print("[Audio stopped]")
                        continue
                    elif line.lower() == "/cancel":
                        if audio_player:
                            audio_player.stop()
                        await websocket.send(json.dumps({"type": "cancel"}))
                        print("[Cancelled]")
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


async def receive_messages(
    websocket: WebSocketClientProtocol,
    audio_player: AudioPlayer | None = None,
) -> None:
    """
    Receive and display messages from the server.
    
    Args:
        websocket: WebSocket connection
        audio_player: Optional audio player for TTS output
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
                print(f"\n[Error]: {error_msg}")
            
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
