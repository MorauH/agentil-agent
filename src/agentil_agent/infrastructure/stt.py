"""
Speech-to-Text module using OpenAI Whisper.

Provides transcription of audio data (numpy arrays, bytes, or files).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import numpy as np
import whisper

if TYPE_CHECKING:
    from whisper import Whisper

from .torch_utils import get_best_device


logger = logging.getLogger(__name__)

# Whisper expects 16kHz audio
SAMPLE_RATE = 16000


class STTEngine:
    """
    Speech-to-Text engine using OpenAI Whisper.
    
    Supports transcription of audio files, numpy arrays, and raw bytes.
    """
    
    # Available model sizes (larger = more accurate but slower)
    MODELS = ["tiny", "base", "small", "medium", "large"]
    
    def __init__(self, model: str = "base", device: str = "auto") -> None:
        """
        Initialize the STT engine.
        
        Args:
            model: Whisper model size (tiny, base, small, medium, large)
            device: Compute device ('auto', 'cpu', 'cuda')
        """
        self._model_name = model
        self._requested_device = device
        self._model: Whisper | None = None
        self._device: str | None = None
    
    def _ensure_model_loaded(self) -> None:
        """Lazy load the Whisper model on first use."""
        if self._model is not None:
            return
        
        # Determine best device
        self._device = get_best_device(self._requested_device)
        logger.info(f"Loading Whisper model '{self._model_name}' on device: {self._device}")
        self._model = whisper.load_model(self._model_name, device=self._device)
        logger.info("Whisper model loaded")
    
    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None
    
    @property
    def device(self) -> str | None:
        """Get the device the model is loaded on."""
        return self._device
    
    def transcribe_file(self, audio_path: str) -> str:
        """
        Transcribe an audio file.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Transcribed text
        """
        self._ensure_model_loaded()
        assert self._model is not None
        
        result = self._model.transcribe(audio_path)
        text = result["text"]
        return text.strip() if isinstance(text, str) else str(text).strip()
    
    def transcribe_audio(self, audio: np.ndarray) -> str:
        """
        Transcribe audio data.
        
        Args:
            audio: Audio data as numpy array (float32, 16kHz, mono)
            
        Returns:
            Transcribed text
        """
        self._ensure_model_loaded()
        assert self._model is not None
        
        # Ensure correct dtype
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        
        # Use fp16 only if on CUDA and compatible
        use_fp16 = self._device == "cuda"
        result = self._model.transcribe(audio, fp16=use_fp16)
        text = result["text"]
        return text.strip() if isinstance(text, str) else str(text).strip()
    
    def transcribe_bytes(self, audio_bytes: bytes, sample_width: int = 2) -> str:
        """
        Transcribe raw audio bytes (PCM).
        
        Args:
            audio_bytes: Raw audio bytes (PCM, 16kHz, mono)
            sample_width: Bytes per sample (2 for 16-bit, 4 for 32-bit)
            
        Returns:
            Transcribed text
        """
        if sample_width == 2:
            # 16-bit signed PCM
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        elif sample_width == 4:
            # 32-bit float
            audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
        else:
            raise ValueError(f"Unsupported sample width: {sample_width}")
        
        return self.transcribe_audio(audio_np)


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing STT Engine...")
    print()
    
    engine = STTEngine(model="base")
    
    # Test with a simple audio generation (silence + tone)
    print("Generating test audio...")
    duration = 2.0  # seconds
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), dtype=np.float32)
    # Generate a simple sine wave (won't transcribe to anything meaningful)
    audio = 0.1 * np.sin(2 * np.pi * 440 * t)
    
    print(f"Audio shape: {audio.shape}, dtype: {audio.dtype}")
    print("Transcribing (this is just a test tone, expect empty or noise)...")
    
    result = engine.transcribe_audio(audio)
    print(f"Result: '{result}'")
    print()
    print("STT Engine test complete!")
