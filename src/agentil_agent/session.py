"""
Session manager for Agentil Agent Server.

Manages the voice session state and coordinates STT, TTS, and agent backend.
"""

from __future__ import annotations

import asyncio
import logging
from os import wait
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import numpy as np

from .audio import AudioBuffer, decode_audio_to_pcm, encode_audio, split_text_into_sentences
from .agent import BaseAgent, create_agent
from .config import Config
from .protocol import (
    AudioChunkMessage,
    AudioFormat,
    AudioStreamEndMessage,
    AudioStreamStartMessage,
    ErrorMessage,
    ResponseDeltaMessage,
    ResponseEndMessage,
    ResponseStartMessage,
    ServerMessage,
    SessionState,
    StatusMessage,
    TranscriptMessage,
)
from .stt import STTEngine
from .tts import TTSEngine

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


# Type alias for message sender callback
MessageSender = Callable[[ServerMessage], Coroutine[Any, Any, None]]
BinarySender = Callable[[bytes], Coroutine[Any, Any, None]]


class Session:
    """
    Voice session that coordinates all components.

    Handles:
    - Text input → Agent → Text/Audio output
    - Audio input → STT → Agent → Text/Audio output
    - State management
    - Streaming coordination
    """

    def __init__(
        self,
        config: Config,
        send_message: MessageSender,
        send_binary: BinarySender,
        session_id: str,
    ) -> None:
        """
        Initialize a voice session.

        Args:
            config: Server configuration
            send_message: Callback to send JSON messages to client
            send_binary: Callback to send binary data to client
            session_id: Unique session identifier
        """
        self.config = config
        self.session_id = session_id
        self._send_message = send_message
        self._send_binary = send_binary

        # State
        self._state = SessionState.IDLE
        self._tts_enabled = True
        self._stt_enabled = True
        self._cancelled = False

        # Audio buffer for incoming audio
        self._audio_buffer = AudioBuffer()
        self._audio_format: str = "webm"

        # Components (lazy loaded)
        self._stt_engine: STTEngine | None = None
        self._tts_engine: TTSEngine | None = None
        self._agent: BaseAgent | None = None
        self._agent_session_id: str | None = None

        # Locks
        self._processing_lock = asyncio.Lock()

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def state(self) -> SessionState:
        """Current session state."""
        return self._state

    @property
    def tts_enabled(self) -> bool:
        """Whether TTS output is enabled."""
        return self._tts_enabled

    @tts_enabled.setter
    def tts_enabled(self, value: bool) -> None:
        self._tts_enabled = value

    @property
    def stt_enabled(self) -> bool:
        """Whether STT processing is enabled."""
        return self._stt_enabled

    @stt_enabled.setter
    def stt_enabled(self, value: bool) -> None:
        self._stt_enabled = value

    # =========================================================================
    # Component Access (Lazy Loading)
    # =========================================================================

    def _get_stt_engine(self) -> STTEngine:
        """Get or create STT engine."""
        if self._stt_engine is None:
            logger.info(f"Loading STT engine (model: {self.config.stt.model})")
            self._stt_engine = STTEngine(model=self.config.stt.model)
        return self._stt_engine

    def _get_tts_engine(self) -> TTSEngine:
        """Get or create TTS engine."""
        if self._tts_engine is None:
            logger.info(f"Loading TTS engine (speaker: {self.config.tts.speaker})")
            self._tts_engine = TTSEngine(
                device=self.config.tts.device,
                speaker=self.config.tts.speaker,
                speed=self.config.tts.speed,
            )
        return self._tts_engine

    async def _ensure_agent_session(self) -> tuple[BaseAgent, str]:
        """Get or create the backend agent + its conversation session."""
        if self._agent is None:
            logger.info(f"Creating agent backend: {self.config.agent.type}")
            self._agent = create_agent(self.config.agent.type, self.config)

        await self._agent.initialize()

        if self._agent_session_id is None:
            session = await self._agent.create_session(title="Voice Session")
            self._agent_session_id = session.id

        return self._agent, self._agent_session_id

    # =========================================================================
    # State Management
    # =========================================================================

    async def _set_state(self, state: SessionState) -> None:
        """Update state and notify client."""
        if self._state != state:
            self._state = state
            await self._send_message(StatusMessage(state=state))

    # =========================================================================
    # Text Input Processing
    # =========================================================================

    async def process_text(self, text: str) -> None:
        """
        Process text input from client.

        Sends to the configured agent backend and streams back response text and audio.

        Args:
            text: User's text message
        """
        if not text.strip():
            return

        async with self._processing_lock:
            self._cancelled = False

            logger.info(f"Processing text: '{text[:50]}...' (TTS enabled: {self._tts_enabled})")

            try:
                await self._set_state(SessionState.PROCESSING)

                # Get or create backend agent session
                agent, agent_session_id = await self._ensure_agent_session()

                # Start response
                await self._send_message(ResponseStartMessage())

                # Stream response from OpenCode
                full_response = ""
                sentence_buffer = ""

                async for chunk in agent.stream_response(agent_session_id, text):
                    if self._cancelled:
                        logger.info("Processing cancelled")
                        break

                    # Send text delta
                    await self._send_message(ResponseDeltaMessage(content=chunk))
                    full_response += chunk
                    sentence_buffer += chunk

                    # Check for complete sentences to TTS
                    if self._tts_enabled:
                        sentences = split_text_into_sentences(sentence_buffer)
                        logger.debug(
                            f"TTS check: buffer='{sentence_buffer[:50]}...', sentences={len(sentences)}"
                        )
                        if len(sentences) > 1:
                            # We have at least one complete sentence
                            for sentence in sentences[:-1]:
                                logger.info(f"TTS: Speaking sentence: {sentence[:50]}...")
                                await self._speak_sentence(sentence)
                            # Keep the incomplete part
                            sentence_buffer = sentences[-1]

                # Handle any remaining text
                if not self._cancelled:
                    await self._send_message(ResponseEndMessage())

                    # Speak remaining sentence buffer
                    if self._tts_enabled and sentence_buffer.strip():
                        logger.info(f"TTS: Speaking final buffer: {sentence_buffer[:50]}...")
                        await self._speak_sentence(sentence_buffer.strip())

            except Exception as e:
                logger.exception("Error processing text")
                await self._send_message(ErrorMessage(message=str(e), code="processing_error"))
            finally:
                await self._set_state(SessionState.IDLE)

    # =========================================================================
    # Audio Input Processing
    # =========================================================================

    def start_audio_input(self, audio_format: str) -> None:
        """
        Start receiving audio input.

        Args:
            audio_format: Format of incoming audio (e.g., "webm/opus")
        """
        self._audio_buffer.clear()
        # Extract base format (e.g., "webm" from "webm/opus")
        self._audio_format = audio_format.split("/")[0] if "/" in audio_format else audio_format
        logger.debug(f"Started audio input (format: {self._audio_format})")

    def add_audio_chunk(self, data: bytes) -> None:
        """
        Add an audio chunk to the buffer.

        Args:
            data: Raw audio bytes
        """
        self._audio_buffer.add(data)
        logger.debug(f"Added audio chunk: {len(data)} bytes (total: {self._audio_buffer.size})")

    async def end_audio_input(self) -> None:
        """
        End audio input and process the buffered audio.

        Transcribes the audio and processes the resulting text.
        """
        if self._audio_buffer.is_empty:
            logger.warning("No audio data received")
            return

        async with self._processing_lock:
            self._cancelled = False

            try:
                await self._set_state(SessionState.LISTENING)

                # Get audio data
                audio_data = self._audio_buffer.get_all()
                self._audio_buffer.clear()

                logger.info(
                    f"Processing audio: {len(audio_data)} bytes, format: {self._audio_format}"
                )

                # Decode to PCM
                pcm_audio = await asyncio.get_event_loop().run_in_executor(
                    None,
                    decode_audio_to_pcm,
                    audio_data,
                    self._audio_format,
                )

                if len(pcm_audio) == 0:
                    logger.warning("No audio data after decoding")
                    await self._set_state(SessionState.IDLE)
                    return

                # Transcribe
                stt_engine = self._get_stt_engine()
                transcript = await asyncio.get_event_loop().run_in_executor(
                    None,
                    stt_engine.transcribe_audio,
                    pcm_audio,
                )

                logger.info(f"Transcribed: {transcript}")

                # Send transcript to client
                await self._send_message(TranscriptMessage(content=transcript, final=True))

                if not transcript.strip():
                    logger.info("Empty transcript, skipping processing")
                    await self._set_state(SessionState.IDLE)
                    return

                # Process the transcribed text
                # Note: We release the lock briefly to allow cancellation

            except Exception as e:
                logger.exception("Error processing audio")
                await self._send_message(
                    ErrorMessage(message=str(e), code="audio_processing_error")
                )
                await self._set_state(SessionState.IDLE)
                return

        # Process text (outside the lock to allow cancellation)
        if not self._cancelled and transcript.strip():
            await self.process_text(transcript)

    # =========================================================================
    # TTS Output
    # =========================================================================

    async def _speak_sentence(self, sentence: str) -> None:
        """
        Generate and stream TTS audio for a sentence.

        Args:
            sentence: Text to speak
        """
        if not sentence.strip() or self._cancelled:
            logger.debug(f"TTS: Skipping empty/cancelled: '{sentence[:30]}'")
            return

        try:
            await self._set_state(SessionState.SPEAKING)

            # Generate TTS audio
            logger.info(f"TTS: Synthesizing '{sentence[:50]}...'")
            tts_engine = self._get_tts_engine()
            audio_data = await asyncio.get_event_loop().run_in_executor(
                None,
                tts_engine.synthesize,
                sentence,
            )

            logger.info(f"TTS: Synthesized {len(audio_data)} samples")

            if len(audio_data) == 0:
                logger.warning("TTS: No audio generated")
                return

            # Encode to output format
            output_format = self.config.audio.output_format.lower()
            sample_rate = tts_engine.sample_rate

            logger.debug(f"TTS: Encoding to {output_format} at {sample_rate}Hz")
            encoded_audio = await asyncio.get_event_loop().run_in_executor(
                None,
                encode_audio,
                audio_data,
                output_format,
                sample_rate,
            )

            logger.info(f"TTS: Encoded to {len(encoded_audio)} bytes")

            if len(encoded_audio) == 0:
                logger.warning("TTS: Encoding produced no output")
                return

            # Send audio to client
            # Map format string to AudioFormat enum
            format_map = {
                "mp3": AudioFormat.MP3,
                "wav": AudioFormat.WAV,
                "opus": AudioFormat.OGG_OPUS,
                "ogg": AudioFormat.OGG_OPUS,
            }
            audio_format = format_map.get(output_format, AudioFormat.MP3)

            # Send audio chunk message (JSON)
            await self._send_message(
                AudioChunkMessage(
                    format=audio_format,
                    sentence=sentence,
                    chunk_index=0,
                    is_last=True,
                )
            )

            # Send binary audio data
            await self._send_binary(encoded_audio)

            logger.info(f"TTS: Sent {len(encoded_audio)} bytes for '{sentence[:30]}...'")

        except Exception as e:
            logger.exception(f"TTS: Error generating audio for: {sentence[:50]}")

    # =========================================================================
    # Control
    # =========================================================================

    async def cancel(self) -> None:
        """Cancel current operation."""
        self._cancelled = True

        # Try to abort backend agent session
        if self._agent and self._agent_session_id:
            try:
                await self._agent.abort_session(self._agent_session_id)
            except Exception:
                pass

        logger.info("Session cancelled")

    async def close(self) -> None:
        """Close the session and clean up resources."""
        await self.cancel()

        if self._agent:
            await self._agent.shutdown()
            self._agent = None
            self._agent_session_id = None

        logger.info(f"Session {self.session_id} closed")


class SessionManager:
    """
    Manages the global voice session.

    Since all connections share the same session, this provides
    a singleton-like interface.
    """

    def __init__(self, config: Config) -> None:
        """
        Initialize the session manager.

        Args:
            config: Server configuration
        """
        self.config = config
        self._session: Session | None = None
        self._lock = asyncio.Lock()

    async def get_or_create_session(
        self,
        send_message: MessageSender,
        send_binary: BinarySender,
        session_id: str,
    ) -> Session:
        """
        Get the existing session or create a new one.

        Args:
            send_message: Callback for sending JSON messages
            send_binary: Callback for sending binary data
            session_id: Session identifier

        Returns:
            The voice session
        """
        async with self._lock:
            if self._session is None:
                self._session = Session(
                    config=self.config,
                    send_message=send_message,
                    send_binary=send_binary,
                    session_id=session_id,
                )
                logger.info(f"Created new session: {session_id}")
            else:
                # Update callbacks for new connection
                self._session._send_message = send_message
                self._session._send_binary = send_binary
                logger.info(f"Resumed existing session: {session_id}")

            return self._session

    async def close_session(self) -> None:
        """Close the current session."""
        async with self._lock:
            if self._session:
                await self._session.close()
                self._session = None
