"""
Text-to-Speech module using MeloTTS.

Provides synchronous and streaming TTS capabilities for voice output.
"""

from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd
import torch

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


def clean_text_for_tts(text: str) -> str:
    """
    Clean text for TTS by removing markdown and special formatting.

    Args:
        text: Raw text that may contain markdown

    Returns:
        Cleaned text suitable for speech synthesis
    """
    if not text:
        return ""

    # Remove markdown bold/italic (**text**, *text*, __text__, _text_)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # Remove markdown headers (### Header)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove markdown images ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Remove inline code `code`
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove code blocks ```code```
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Remove horizontal rules (---, ***, ___)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Remove bullet points and numbered lists markers
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove blockquotes
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

    # Clean up multiple spaces and newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def list_audio_devices() -> list[dict]:
    """List available audio output devices."""
    try:
        devices = sd.query_devices()
        if isinstance(devices, dict):
            return [devices]
        return [d for d in devices if d.get("max_output_channels", 0) > 0]
    except Exception as e:
        logger.warning(f"Failed to query audio devices: {e}")
        return []


def get_default_output_device() -> int | None:
    """
    Get the default output device index.

    Returns:
        Device index or None if no output device available.
    """
    try:
        device = sd.default.device[1]  # Output device
        if device is not None and device >= 0:
            return device
        # Try to find any output device
        devices = list_audio_devices()
        if devices:
            return devices[0].get("index", 0)
        return None
    except Exception:
        return None


def check_audio_available() -> bool:
    """Check if audio output is available."""
    return get_default_output_device() is not None


def get_cuda_compute_capability() -> tuple[int, int] | None:
    """
    Get the CUDA compute capability of the current GPU.

    Returns:
        Tuple of (major, minor) version, or None if CUDA unavailable.
    """
    if not torch.cuda.is_available():
        return None
    try:
        device = torch.cuda.current_device()
        return torch.cuda.get_device_capability(device)
    except Exception:
        return None


def is_cuda_compatible() -> bool:
    """
    Check if the current GPU is compatible with the installed PyTorch.

    Tests by running a small tensor operation on CUDA.

    Returns:
        True if CUDA works, False otherwise.
    """
    if not torch.cuda.is_available():
        return False

    try:
        # Suppress the UserWarning about incompatible GPU
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*CUDA capability.*not compatible.*")
            # Try a simple tensor operation on CUDA
            x = torch.tensor([1.0, 2.0, 3.0], device="cuda")
            y = x * 2
            _ = y.cpu()  # Force sync
        return True
    except RuntimeError as e:
        if "no kernel image" in str(e) or "CUDA" in str(e):
            return False
        raise


def get_best_device(requested: str = "auto") -> str:
    """
    Determine the best available device for inference.

    Args:
        requested: Device preference ('auto', 'cpu', 'cuda', 'mps')

    Returns:
        Device string to use ('cpu', 'cuda', or 'mps')
    """
    if requested == "cpu":
        return "cpu"

    if requested == "mps":
        if torch.backends.mps.is_available():
            return "mps"
        logger.warning("MPS requested but not available, falling back to CPU")
        return "cpu"

    if requested in ("cuda", "auto"):
        if torch.cuda.is_available():
            if is_cuda_compatible():
                return "cuda"
            else:
                cap = get_cuda_compute_capability()
                cap_str = f"sm_{cap[0]}{cap[1]}" if cap else "unknown"
                logger.warning(
                    f"CUDA device detected (compute capability {cap_str}) but not compatible "
                    f"with installed PyTorch. Falling back to CPU. "
                    f"Consider upgrading PyTorch or use device='cpu' explicitly."
                )
                return "cpu"
        elif requested == "cuda":
            logger.warning("CUDA requested but not available, falling back to CPU")

        # For 'auto', also try MPS on Apple Silicon
        if torch.backends.mps.is_available():
            return "mps"

    return "cpu"


class TTSEngine:
    """
    Text-to-Speech engine using MeloTTS.

    Supports multiple speakers and adjustable speed.
    Can output audio to speakers or return raw audio data.
    """

    # Available speakers for English
    SPEAKERS = ["EN-US", "EN-BR", "EN-AU", "EN-Default"]

    def __init__(
        self,
        device: str = "auto",
        speaker: str = "EN-BR",
        speed: float = 1.2,
    ) -> None:
        """
        Initialize the TTS engine.

        Args:
            device: Device to use ('auto', 'cpu', 'cuda', 'mps')
            speaker: Speaker voice to use (EN-US, EN-BR, EN-AU, EN-Default)
            speed: Speech speed multiplier (1.0 = normal)
        """
        self.speed = speed
        self.speaker_name = speaker
        self._requested_device = device
        self._device: str | None = None  # Resolved device, set on model load

        # Lazy load the model
        self._model = None
        self._sample_rate: int | None = None
        self._speaker_id: int | None = None

    def _ensure_model_loaded(self) -> None:
        """Lazy load the TTS model on first use."""
        if self._model is not None:
            return

        # Resolve the best device
        self._device = get_best_device(self._requested_device)
        logger.info(f"Loading MeloTTS model on device: {self._device}")

        # Download NLTK data if needed
        import nltk

        try:
            nltk.data.find("taggers/averaged_perceptron_tagger_eng")
        except LookupError:
            nltk.download("averaged_perceptron_tagger_eng", quiet=True)

        # Import and initialize MeloTTS
        from melo.api import TTS as MeloTTS

        self._model = MeloTTS(language="EN", device=self._device)
        self._sample_rate = self._model.hps.data.sampling_rate
        self._speaker_id = self._model.hps.data.spk2id[self.speaker_name]

        logger.info(
            f"MeloTTS loaded (sample_rate={self._sample_rate}, speaker={self.speaker_name})"
        )

    @property
    def sample_rate(self) -> int:
        """Get the audio sample rate."""
        self._ensure_model_loaded()
        assert self._sample_rate is not None
        return self._sample_rate

    @property
    def is_loaded(self) -> bool:
        """Check if the model is loaded."""
        return self._model is not None

    def synthesize(self, text: str) -> NDArray[np.float32]:
        """
        Synthesize speech from text.

        Args:
            text: Text to convert to speech

        Returns:
            Audio data as numpy array (float32, mono)
        """
        self._ensure_model_loaded()
        assert self._model is not None

        # Clean text for TTS (remove markdown, etc.)
        cleaned_text = clean_text_for_tts(text)

        if not cleaned_text.strip():
            return np.array([], dtype=np.float32)

        logger.debug(f"Synthesizing: {cleaned_text[:50]}...")

        audio = self._model.tts_to_file(
            cleaned_text,
            speaker_id=self._speaker_id,
            speed=self.speed,
        )

        return audio

    def speak(self, text: str, blocking: bool = True) -> None:
        """
        Synthesize and play speech.

        Args:
            text: Text to speak
            blocking: If True, wait for playback to complete

        Raises:
            RuntimeError: If no audio output device is available
        """
        audio = self.synthesize(text)

        if len(audio) == 0:
            return

        # Check for audio device availability
        output_device = get_default_output_device()
        if output_device is None:
            raise RuntimeError(
                "No audio output device available. "
                "On WSL2, you may need to configure PulseAudio/PipeWire. "
                "Use save_to_file() to save audio to a WAV file instead."
            )

        try:
            sd.play(audio, self.sample_rate, device=output_device)
            if blocking:
                sd.wait()
        except sd.PortAudioError as e:
            raise RuntimeError(
                f"Failed to play audio: {e}. "
                "On WSL2, you may need to configure audio passthrough. "
                "Use save_to_file() to save audio to a WAV file instead."
            ) from e

    def speak_async(self, text: str) -> None:
        """
        Synthesize and play speech without blocking.

        Use stop() to interrupt playback.

        Args:
            text: Text to speak
        """
        self.speak(text, blocking=False)

    @staticmethod
    def stop() -> None:
        """Stop any ongoing audio playback."""
        sd.stop()

    @staticmethod
    def is_playing() -> bool:
        """Check if audio is currently playing."""
        stream = sd.get_stream()
        return stream is not None and stream.active

    def save_to_file(self, text: str, output_path: str) -> None:
        """
        Synthesize speech and save to WAV file.

        Args:
            text: Text to convert to speech
            output_path: Path to save the WAV file
        """
        self._ensure_model_loaded()
        assert self._model is not None

        self._model.tts_to_file(
            text,
            speaker_id=self._speaker_id,
            output_path=output_path,
            speed=self.speed,
        )
        logger.info(f"Saved audio to {output_path}")


# Module-level convenience functions
_default_engine: TTSEngine | None = None


def get_default_engine() -> TTSEngine:
    """Get or create the default TTS engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = TTSEngine()
    return _default_engine


def speak(text: str, blocking: bool = True) -> None:
    """
    Speak text using the default TTS engine.

    Args:
        text: Text to speak
        blocking: If True, wait for playback to complete
    """
    get_default_engine().speak(text, blocking=blocking)


def stop() -> None:
    """Stop any ongoing audio playback."""
    TTSEngine.stop()


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Check audio availability first
    print("Checking audio devices...")
    devices = list_audio_devices()
    if devices:
        print(f"Found {len(devices)} output device(s):")
        for d in devices[:5]:  # Show first 5
            print(f"  - {d.get('name', 'Unknown')} (index: {d.get('index')})")
    else:
        print("No audio output devices found!")
        print("Will save to file instead.")
    print()

    tts = TTSEngine(speaker="EN-BR")

    text = """
        Buzz the bee dreamt of touching the moon, its pale glow reflecting in his tiny eyes.
        Each day, he flew higher, fueled by hope and nectar.
    """

    if check_audio_available():
        print("Speaking...")
        try:
            tts.speak(text)
            print("Done!")
        except RuntimeError as e:
            print(f"Playback failed: {e}")
            print("Saving to file instead...")
            tts.save_to_file(text, "/tmp/tts_test.wav")
            print("Saved to /tmp/tts_test.wav")
    else:
        print("No audio device available. Saving to file...")
        tts.save_to_file(text, "/tmp/tts_test.wav")
        print("Saved to /tmp/tts_test.wav")
        print("Play with: aplay /tmp/tts_test.wav")
    print()
