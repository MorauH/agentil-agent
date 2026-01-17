"""
Audio format conversion utilities for Agentil Agent Server.

Handles conversion between various audio formats for WebSocket streaming.
"""

from __future__ import annotations

import io
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# Whisper expects 16kHz mono audio
WHISPER_SAMPLE_RATE = 16000

# Default TTS output sample rate
TTS_SAMPLE_RATE = 24000


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def decode_audio_to_pcm(
    audio_data: bytes,
    input_format: str = "webm",
    sample_rate: int = WHISPER_SAMPLE_RATE,
) -> NDArray[np.float32]:
    """
    Decode audio data to PCM float32 array using ffmpeg.
    
    Args:
        audio_data: Raw audio bytes in the input format
        input_format: Input format (webm, ogg, mp3, wav, etc.)
        sample_rate: Target sample rate (default: 16kHz for Whisper)
        
    Returns:
        Audio as numpy float32 array, normalized to [-1, 1]
        
    Raises:
        RuntimeError: If ffmpeg fails or is not available
    """
    if not audio_data:
        return np.array([], dtype=np.float32)

    # Use ffmpeg to convert to raw PCM
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", input_format,
        "-i", "pipe:0",  # Read from stdin
        "-ar", str(sample_rate),  # Target sample rate
        "-ac", "1",  # Mono
        "-f", "s16le",  # 16-bit signed little-endian PCM
        "-acodec", "pcm_s16le",
        "pipe:1",  # Write to stdout
    ]

    try:
        result = subprocess.run(
            cmd,
            input=audio_data,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")
            logger.error(f"ffmpeg error: {error_msg}")
            raise RuntimeError(f"ffmpeg failed: {error_msg}")

        # Convert to float32 normalized array
        pcm_data = np.frombuffer(result.stdout, dtype=np.int16)
        return pcm_data.astype(np.float32) / 32768.0

    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out during audio conversion")


def encode_audio_to_mp3(
    audio_data: NDArray[np.float32],
    sample_rate: int = TTS_SAMPLE_RATE,
    bitrate: str = "128k",
) -> bytes:
    """
    Encode PCM audio to MP3 using ffmpeg.
    
    Args:
        audio_data: Audio as numpy float32 array, normalized to [-1, 1]
        sample_rate: Input sample rate
        bitrate: MP3 bitrate (default: 128k)
        
    Returns:
        MP3 encoded audio bytes
        
    Raises:
        RuntimeError: If ffmpeg fails
    """
    if len(audio_data) == 0:
        return b""

    # Convert to 16-bit PCM
    pcm_data = (audio_data * 32767).astype(np.int16).tobytes()

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        "-i", "pipe:0",
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        "-f", "mp3",
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=pcm_data,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")
            logger.error(f"ffmpeg error: {error_msg}")
            raise RuntimeError(f"ffmpeg failed: {error_msg}")

        return result.stdout

    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out during audio encoding")


def encode_audio_to_wav(
    audio_data: NDArray[np.float32],
    sample_rate: int = TTS_SAMPLE_RATE,
) -> bytes:
    """
    Encode PCM audio to WAV format.
    
    Args:
        audio_data: Audio as numpy float32 array
        sample_rate: Sample rate
        
    Returns:
        WAV encoded audio bytes
    """
    import soundfile as sf

    buffer = io.BytesIO()
    sf.write(buffer, audio_data, sample_rate, format="WAV", subtype="PCM_16")
    buffer.seek(0)
    return buffer.read()


def encode_audio_to_opus(
    audio_data: NDArray[np.float32],
    sample_rate: int = TTS_SAMPLE_RATE,
) -> bytes:
    """
    Encode PCM audio to Ogg/Opus using ffmpeg.
    
    Args:
        audio_data: Audio as numpy float32 array
        sample_rate: Input sample rate
        
    Returns:
        Ogg/Opus encoded audio bytes
    """
    if len(audio_data) == 0:
        return b""

    # Convert to 16-bit PCM
    pcm_data = (audio_data * 32767).astype(np.int16).tobytes()

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        "-i", "pipe:0",
        "-codec:a", "libopus",
        "-b:a", "64k",
        "-f", "ogg",
        "pipe:1",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=pcm_data,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffmpeg failed: {error_msg}")

        return result.stdout

    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg.")


def encode_audio(
    audio_data: NDArray[np.float32],
    output_format: str,
    sample_rate: int = TTS_SAMPLE_RATE,
) -> bytes:
    """
    Encode audio to the specified format.
    
    Args:
        audio_data: Audio as numpy float32 array
        output_format: Target format (mp3, wav, ogg/opus)
        sample_rate: Sample rate
        
    Returns:
        Encoded audio bytes
    """
    format_lower = output_format.lower()
    
    if format_lower == "mp3":
        return encode_audio_to_mp3(audio_data, sample_rate)
    elif format_lower == "wav":
        return encode_audio_to_wav(audio_data, sample_rate)
    elif format_lower in ("opus", "ogg", "ogg/opus"):
        return encode_audio_to_opus(audio_data, sample_rate)
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def split_text_into_sentences(text: str) -> list[str]:
    """
    Split text into sentences for incremental TTS.
    
    Uses simple heuristics to split on sentence boundaries.
    
    Args:
        text: Text to split
        
    Returns:
        List of sentences
    """
    import re
    
    if not text:
        return []
    
    # Split on sentence-ending punctuation followed by space or end
    # Keep the punctuation with the sentence
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    
    # Filter out empty strings and clean up
    return [s.strip() for s in sentences if s.strip()]


class AudioBuffer:
    """
    Buffer for accumulating audio chunks.
    
    Used to collect incoming audio data from WebSocket before processing.
    """
    
    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._total_size = 0
    
    def add(self, chunk: bytes) -> None:
        """Add a chunk to the buffer."""
        self._chunks.append(chunk)
        self._total_size += len(chunk)
    
    def get_all(self) -> bytes:
        """Get all buffered data as a single bytes object."""
        return b"".join(self._chunks)
    
    def clear(self) -> None:
        """Clear the buffer."""
        self._chunks.clear()
        self._total_size = 0
    
    @property
    def size(self) -> int:
        """Total size of buffered data in bytes."""
        return self._total_size
    
    @property
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return self._total_size == 0


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print(f"ffmpeg available: {check_ffmpeg_available()}")
    
    # Test sentence splitting
    test_text = "Hello, how are you? I'm doing great. This is a test!"
    sentences = split_text_into_sentences(test_text)
    print(f"Sentences: {sentences}")
