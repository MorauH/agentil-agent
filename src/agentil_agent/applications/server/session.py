"""
Session manager for Agentil Agent Server.

Manages the voice session state and coordinates STT, TTS, and agent backend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, AsyncGenerator, Callable, Coroutine


from agentil_agent.core.audio import AudioBuffer, split_text_into_sentences
from agentil_agent.infrastructure.audio import decode_audio_to_pcm, encode_audio
from agentil_agent.core.agent import BaseAgent, create_agent
from agentil_agent.core.space import BaseSpace, SpaceManager
from agentil_agent.core.mcp import MCPManager, MCPServerInfo
from .config import AppConfig
from .protocol import (
    SpaceInfo,
    MCPInfo,
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
    SessionUpdateMessage,
    StatusMessage,
    TranscriptMessage,
    ConfigMessage,
    OperationProgressMessage,
)
if TYPE_CHECKING:
    from numpy.typing import NDArray
    from agentil_agent.infrastructure.stt import STTEngine
    from agentil_agent.infrastructure.tts import TTSEngine

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
    - Space management
    """

    def __init__(
        self,
        config: AppConfig,
        send_message: MessageSender,
        send_binary: BinarySender,
        session_id: str,
        space_manager: SpaceManager | None = None,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        """
        Initialize a voice session.

        Args:
            config: Server app configuration
            send_message: Callback to send JSON messages to client
            send_binary: Callback to send binary data to client
            session_id: Unique session identifier
            space_manager: Optional SpaceManager for space management
            mcp_manager: Optional MCPManager for MCP server management
        """
        self.config = config
        self.session_id = session_id
        self._send_message = send_message
        self._send_binary = send_binary

        # Managers (optional for backward compatibility)
        self._space_manager = space_manager
        self._mcp_manager = mcp_manager

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
        self._current_space: BaseSpace | None = None
        self._agent: BaseAgent | None = None
        self._agent_session_id: str | None = None

        # Locks
        self._processing_lock = asyncio.Lock()

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def create_headless(
        cls,
        config: AppConfig,
        space_manager: SpaceManager | None = None,
        mcp_manager: MCPManager | None = None,
        session_id: str = "headless",
    ) -> "Session":
        """
        Create a Session for programmatic (non-WebSocket) use.

        The session is created with no-op message/binary senders,
        making it suitable for library consumers that interact via
        stream_text() instead of WebSocket callbacks.

        Args:
            config: Server app configuration
            space_manager: Optional SpaceManager for space management
            mcp_manager: Optional MCPManager for MCP server management
            session_id: Session identifier (default: "headless")

        Returns:
            A Session instance ready for programmatic use
        """
        async def _noop_send_message(msg: ServerMessage) -> None:
            pass

        async def _noop_send_binary(data: bytes) -> None:
            pass

        return cls(
            config=config,
            send_message=_noop_send_message,
            send_binary=_noop_send_binary,
            session_id=session_id,
            space_manager=space_manager,
            mcp_manager=mcp_manager,
        )

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

    @property
    def current_space(self) -> BaseSpace | None:
        """Current active space."""
        return self._current_space

    # =========================================================================
    # Space Management
    # =========================================================================

    async def switch_space(self, space_id: str) -> None:
        """
        Switch to a different space.

        With the ServerPool architecture, each space has its own OpenCode server.
        Switching spaces updates the agent's space and reconnects to the appropriate
        server (starting one if needed).

        Args:
            space_id: ID of the space to switch to

        Raises:
            ValueError: If SpaceManager is not available
            SpaceError: If space doesn't exist
        """
        if self._space_manager is None:
            raise ValueError("SpaceManager not available")

        logger.info(f"Switching to space: {space_id}")

        # Get the new space (initializes it if needed)
        new_space = await self._space_manager.get_space(space_id)

        # If same space, just clear history
        if self._current_space and self._current_space.space_id == space_id:
            logger.info(f"Already in space '{space_id}', just clearing history")
            await self._clear_history()
            return

        old_space_id = self._current_space.space_id if self._current_space else None

        # Update current space
        self._current_space = new_space

        # If agent exists, update its space and reinitialize
        # The ServerPool will handle connecting to the right server
        if self._agent:
            logger.info(f"Updating agent to use space '{space_id}'...")
            self._agent.set_space(new_space, self._mcp_manager)
            # Re-initialize to connect to the correct server
            # This will switch servers without full shutdown
            await self._agent.initialize()
            # Clear session ID since we're on a new server/space
            self._agent_session_id = None

        logger.info(f"Switched from space '{old_space_id}' to '{space_id}'")

    async def _ensure_space(self) -> BaseSpace | None:
        """
        Ensure a space is loaded.

        If no space is currently active and a SpaceManager is available,
        loads the default space.

        Returns:
            Current space or None if SpaceManager not available
        """
        if self._current_space is not None:
            return self._current_space

        if self._space_manager is None:
            return None

        # Load default space
        self._current_space = await self._space_manager.get_default_space()
        logger.info(f"Loaded default space: {self._current_space.space_id}")
        return self._current_space

    # =========================================================================
    # Component Access (Lazy Loading)
    # =========================================================================

    def _get_stt_engine(self) -> STTEngine:
        """Get or create STT engine."""
        if self._stt_engine is None:
            from agentil_agent.infrastructure.stt import STTEngine

            logger.info(f"Loading STT engine (model: {self.config.infra.stt.model})")
            self._stt_engine = STTEngine(model=self.config.infra.stt.model)
        return self._stt_engine

    def _get_tts_engine(self) -> TTSEngine:
        """Get or create TTS engine."""
        if self._tts_engine is None:
            from agentil_agent.infrastructure.tts import TTSEngine

            logger.info(f"Loading TTS engine (speaker: {self.config.infra.tts.speaker})")
            self._tts_engine = TTSEngine(
                device=self.config.infra.tts.device,
                speaker=self.config.infra.tts.speaker,
                speed=self.config.infra.tts.speed,
            )
        return self._tts_engine

    async def _ensure_agent_session(self) -> tuple[BaseAgent, str]:
        """
        Get or create the backend agent + its conversation session.

        Ensures the space is configured BEFORE initializing the agent,
        so the OpenCode server starts in the correct directory.
        """
        is_new_agent = self._agent is None

        if self._agent is None:
            logger.info(f"Creating agent backend: {self.config.core.agent.type}")
            self._agent = create_agent(self.config.core.agent.type, self.config.core)

        # Ensure space is loaded BEFORE initialization
        # This is critical because OpenCode server binds to its working directory at startup
        space = await self._ensure_space()
        if space is not None and (is_new_agent or self._agent.space != space):
            self._agent.set_space(space, self._mcp_manager)
            logger.info(f"Agent configured with space: {space.space_id}")

        # Initialize after space is set (starts OpenCode server in correct directory)
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

    async def send_initial_state(self) -> None:
        """
        Send initial session state to client on connect.

        This sends available spaces, MCP servers, and current settings
        without requiring the agent to be initialized.
        """
        try:
            # Gather available spaces from SpaceManager
            available_spaces: list[SpaceInfo] = []
            current_space_id: str | None = None

            if self._space_manager:
                for space_info in self._space_manager.list_spaces():
                    available_spaces.append(
                        SpaceInfo(
                            id=space_info.space_id,
                            name=space_info.name,
                            description=space_info.description,
                        )
                    )

            # Load default space if not already set
            if self._current_space is None and self._space_manager:
                self._current_space = await self._space_manager.get_default_space()
                logger.info(f"Loaded default space on connect: {self._current_space.space_id}")

            if self._current_space:
                current_space_id = self._current_space.space_id

            # Gather MCP servers from MCPManager
            mcp_servers: list[MCPInfo] = []
            if self._mcp_manager:
                # Get enabled MCPs from current space
                enabled_mcps: set[str] = set()
                if self._current_space:
                    enabled_mcps = set(self._current_space.get_enabled_mcps())

                for server_info in self._mcp_manager.list_servers():
                    mcp_servers.append(
                        MCPInfo(
                            name=server_info.id,
                            version=server_info.version,
                            enabled=server_info.id in enabled_mcps,
                            description=server_info.description,
                        )
                    )

            await self._send_message(
                SessionUpdateMessage(
                    available_spaces=available_spaces,
                    current_space_id=current_space_id,
                    mcp_servers=mcp_servers,
                    tts_enabled=self._tts_enabled,
                    stt_enabled=self._stt_enabled,
                )
            )
            logger.info(f"Sent initial state: {len(available_spaces)} spaces, {len(mcp_servers)} MCPs")
        except Exception as e:
            logger.exception(f"Error sending initial state: {e}")


    async def _send_session_update(self) -> None:
        """Send current session state to client."""
        try:
            agent, session_id = await self._ensure_agent_session()

            # Gather available spaces from SpaceManager
            available_spaces: list[SpaceInfo] = []
            if self._space_manager:
                for space_info in self._space_manager.list_spaces():
                    available_spaces.append(
                        SpaceInfo(
                            id=space_info.space_id,
                            name=space_info.name,
                            description=space_info.description,
                        )
                    )

            # Gather MCP servers from MCPManager
            mcp_servers: list[MCPInfo] = []
            if self._mcp_manager:
                # Get enabled MCPs from current space
                enabled_mcps: set[str] = set()
                if self._current_space:
                    enabled_mcps = set(self._current_space.get_enabled_mcps())

                for server_info in self._mcp_manager.list_servers():
                    mcp_servers.append(
                        MCPInfo(
                            name=server_info.id,
                            version=server_info.version,
                            enabled=server_info.id in enabled_mcps,
                            description=server_info.description,
                        )
                    )

            await self._send_message(
                SessionUpdateMessage(
                    available_spaces=available_spaces,
                    current_space_id=self._current_space.space_id if self._current_space else None,
                    mcp_servers=mcp_servers,
                    tts_enabled=self._tts_enabled,
                    stt_enabled=self._stt_enabled,
                )
            )
        except Exception as e:
            logger.exception(f"Error sending session update: {e}")

    async def process_config(self, config: ConfigMessage) -> None:
        """
        Process configuration update from client.

        Handles audio settings, space switching, MCP installation, and history management.

        Args:
            config: Configuration message from client
        """
        logger.info("Received session config update")

        # Audio settings
        if config.tts_enabled is not None:
            self.tts_enabled = config.tts_enabled
            logger.info(f"Session TTS set to: {config.tts_enabled}")
        if config.stt_enabled is not None:
            self.stt_enabled = config.stt_enabled
            logger.info(f"Session STT set to: {config.stt_enabled}")

        # Space management
        if config.switch_space is not None:
            try:
                await self.switch_space(config.switch_space)
                # Send updated session info after space switch
                await self._send_session_update()
            except Exception as e:
                logger.exception(f"Failed to switch space: {e}")
                await self._send_message(
                    ErrorMessage(message=f"Failed to switch space: {e}", code="space_switch_error")
                )

        # MCP installation
        if config.install_mcp_url is not None:
            await self._install_mcp_from_url(config.install_mcp_url)

        # MCP activation in current space
        if config.active_mcps:
            await self._set_active_mcps(config.active_mcps)

        # Clear conversation history
        if config.clear_history:
            await self._clear_history()

    async def _install_mcp_from_url(self, url: str) -> None:
        """
        Install an MCP server from a URL.

        Sends progress updates to the client during installation.

        Args:
            url: Git URL of the MCP server to install
        """
        if self._mcp_manager is None:
            await self._send_message(
                ErrorMessage(message="MCP manager not available", code="mcp_unavailable")
            )
            return

        try:
            # Send starting progress
            await self._send_message(
                OperationProgressMessage(
                    operation="install_mcp",
                    target=url,
                    status="starting",
                    message="Cloning repository..."
                )
            )

            # Install the MCP server
            server_info = await self._mcp_manager.install_from_url(url)

            # Send completion
            await self._send_message(
                OperationProgressMessage(
                    operation="install_mcp",
                    target=server_info.id,
                    status="complete",
                    message=f"Installed MCP server: {server_info.name}"
                )
            )

            # Auto-enable in current space if space is available
            if self._current_space:
                enabled_mcps = self._current_space.get_enabled_mcps()
                if server_info.id not in enabled_mcps:
                    enabled_mcps.append(server_info.id)
                    self._current_space.set_enabled_mcps(enabled_mcps)
                    logger.info(f"Auto-enabled MCP '{server_info.id}' in space '{self._current_space.space_id}'")

                    # Reconfigure agent with updated MCPs
                    if self._agent:
                        self._agent.set_space(self._current_space, self._mcp_manager)

            # Send updated session info
            await self._send_session_update()

        except Exception as e:
            logger.exception(f"Failed to install MCP from URL: {e}")
            await self._send_message(
                OperationProgressMessage(
                    operation="install_mcp",
                    target=url,
                    status="failed",
                    message=str(e)
                )
            )
            await self._send_message(
                ErrorMessage(message=f"Failed to install MCP: {e}", code="mcp_install_error")
            )

    async def _set_active_mcps(self, mcp_ids: list[str]) -> None:
        """
        Set the active MCPs for the current space.

        Args:
            mcp_ids: List of MCP server IDs to activate
        """
        if self._current_space is None:
            logger.warning("No current space - cannot set active MCPs")
            return

        # Get current enabled MCPs
        current_enabled = set(self._current_space.get_enabled_mcps())
        new_enabled = set(mcp_ids)

        if current_enabled == new_enabled:
            logger.debug("MCP configuration unchanged")
            return

        # Update space configuration
        self._current_space.set_enabled_mcps(mcp_ids)
        logger.info(f"Updated active MCPs for space '{self._current_space.space_id}': {mcp_ids}")

        # Reconfigure agent with updated MCPs
        if self._agent:
            self._agent.set_space(self._current_space, self._mcp_manager)

        # Send updated session info
        await self._send_session_update()

    async def _clear_history(self) -> None:
        """
        Clear the conversation history.

        Creates a new agent session, effectively starting a fresh conversation.
        """
        if self._agent and self._agent_session_id:
            try:
                await self._agent.abort_session(self._agent_session_id)
            except Exception:
                pass

        # Clear the session ID to force creation of a new session
        self._agent_session_id = None
        logger.info("Conversation history cleared")


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

    async def stream_text(self, text: str) -> AsyncGenerator[str, None]:
        """
        Stream a text response, yielding chunks as they arrive.

        This is the programmatic equivalent of process_text() — it handles
        the full agent lifecycle (ensure agent session, space, initialization)
        but yields text chunks directly instead of routing through WebSocket
        callbacks.

        Intended for library consumers (e.g., CodeReport) that import
        agentil-agent as a dependency and don't use the WebSocket server.

        Args:
            text: User's text message to send to the agent

        Yields:
            Text chunks from the agent's streaming response

        Raises:
            Exception: If agent initialization or streaming fails
        """
        if not text.strip():
            return

        async with self._processing_lock:
            self._cancelled = False

            logger.info(f"Streaming text: '{text[:50]}...'")

            # Get or create backend agent session
            agent, agent_session_id = await self._ensure_agent_session()

            async for chunk in agent.stream_response(agent_session_id, text):
                if self._cancelled:
                    logger.info("Streaming cancelled")
                    break
                yield chunk

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

    def __init__(
        self,
        config: AppConfig,
        space_manager: SpaceManager | None = None,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        """
        Initialize the session manager.

        Args:
            config: Server app configuration
            space_manager: Optional SpaceManager for space management
            mcp_manager: Optional MCPManager for MCP server management
        """
        self.config = config
        self._space_manager = space_manager
        self._mcp_manager = mcp_manager
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
                    space_manager=self._space_manager,
                    mcp_manager=self._mcp_manager,
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
