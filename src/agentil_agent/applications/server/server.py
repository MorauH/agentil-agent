"""
WebSocket server for Agentil Agent.

Provides the main FastAPI application with WebSocket endpoint
for bidirectional audio/text streaming.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import AppConfig, get_config
from .protocol import (
    AudioEndMessage,
    AudioStartMessage,
    CancelMessage,
    ConfigMessage,
    ConnectedMessage,
    ErrorMessage,
    PingMessage,
    PongMessage,
    ServerMessage,
    TextMessage,
    parse_client_message,
)
from .session import SessionManager
from agentil_agent.core.space import SpaceManager
from agentil_agent.core.mcp import MCPManager

logger = logging.getLogger(__name__)

from agentil_agent import __version__


# =============================================================================
# Application State
# =============================================================================


class AppState:
    """Application state container."""

    def __init__(
        self,
        config: AppConfig,
        space_manager: SpaceManager | None = None,
        mcp_manager: MCPManager | None = None,
    ) -> None:
        self.config = config
        self.space_manager = space_manager
        self.mcp_manager = mcp_manager
        self.session_manager = SessionManager(
            config,
            space_manager=space_manager,
            mcp_manager=mcp_manager,
        )
        self.token = config.ensure_token()


_app_state: AppState | None = None


def get_app_state() -> AppState:
    """Get the application state."""
    if _app_state is None:
        raise RuntimeError("Application not initialized")
    return _app_state


# =============================================================================
# Lifespan Management
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global _app_state

    config = get_config()

    # Initialize managers if enabled
    space_manager: SpaceManager | None = None
    mcp_manager: MCPManager | None = None

    if config.core.spaces.auto_initialize:
        logger.info(f"Initializing SpaceManager at {config.core.get_spaces_root()}")
        space_manager = SpaceManager(
            spaces_root=config.core.get_spaces_root(),
            default_space_type=config.core.spaces.default_space_type,
        )
        await space_manager.initialize()
        logger.info(f"SpaceManager initialized with {len(space_manager.list_spaces())} spaces")

    if config.core.mcp.auto_initialize:
        logger.info(f"Initializing MCPManager at {config.core.get_mcp_base_path()}")
        mcp_manager = MCPManager(base_path=config.core.get_mcp_base_path())
        await mcp_manager.initialize()
        logger.info(f"MCPManager initialized with {len(mcp_manager.list_servers())} servers")

    _app_state = AppState(
        config,
        space_manager=space_manager,
        mcp_manager=mcp_manager,
    )

    logger.info(f"Agentil Agent Server v{__version__} starting...")
    logger.info(f"Server: {config.server.host}:{config.server.port}")
    logger.info(f"OpenCode: {config.core.agent.opencode.host}:{config.core.agent.opencode.base_port}-{config.core.agent.opencode.base_port + config.core.agent.opencode.max_servers - 1}")
    logger.info(f"Working directory: {config.get_working_dir()}")
    logger.info(f"Auth token: {_app_state.token[:8]}...")

    yield

    # Cleanup
    logger.info("Shutting down...")
    if _app_state:
        await _app_state.session_manager.close_session()
        # The session manager's session holds the agent which has the server pool
        # Servers in the pool are not stopped by normal shutdown - we need to stop them explicitly
        # This is handled by the session close which calls agent.shutdown()

    # Shutdown managers
    if mcp_manager:
        await mcp_manager.shutdown()
        logger.info("MCPManager shutdown complete")

    if space_manager:
        await space_manager.shutdown()
        logger.info("SpaceManager shutdown complete")


# =============================================================================
# FastAPI Application
# =============================================================================


def create_app(config: AppConfig | None = None) -> FastAPI:
    """
    Create the FastAPI application.

    Args:
        config: Optional configuration (uses global config if not provided)

    Returns:
        Configured FastAPI application
    """
    if config:
        from .config import set_config

        set_config(config)

    app = FastAPI(
        title="Agentil Agent Server",
        description="WebSocket API for voice interaction with OpenCode",
        version=__version__,
        lifespan=lifespan,
    )

    # Get config for CORS setup
    cfg = config or get_config()

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(api_router)

    return app


# =============================================================================
# API Routes
# =============================================================================


from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": __version__,
    }


@api_router.get("/info")
async def server_info() -> dict[str, Any]:
    """Get server information."""
    state = get_app_state()
    opencode_cfg = state.config.core.agent.opencode
    return {
        "version": __version__,
        "opencode": {
            "host": opencode_cfg.host,
            "base_port": opencode_cfg.base_port,
            "max_servers": opencode_cfg.max_servers,
            "port_range": f"{opencode_cfg.base_port}-{opencode_cfg.base_port + opencode_cfg.max_servers - 1}",
        },
        "stt": {
            "model": state.config.infra.stt.model,
        },
        "tts": {
            "speaker": state.config.infra.tts.speaker,
            "speed": state.config.infra.tts.speed,
        },
        "audio": {
            "input_format": state.config.audio.input_format,
            "output_format": state.config.audio.output_format,
        },
    }


# =============================================================================
# WebSocket Handler
# =============================================================================


@api_router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    """
    Main WebSocket endpoint for voice communication.

    Query Parameters:
        token: Authentication token
    """
    state = get_app_state()

    # Validate token
    if token != state.token:
        await websocket.close(code=4001, reason="Invalid token")
        logger.warning(f"Connection rejected: invalid token from {websocket.client}")
        return

    await websocket.accept()
    logger.info(f"Client connected: {websocket.client}")

    # Generate session ID
    session_id = secrets.token_hex(8)

    # Message sending helpers
    async def send_message(msg: ServerMessage) -> None:
        """Send a JSON message to the client."""
        try:
            await websocket.send_json(msg.model_dump())
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

    async def send_binary(data: bytes) -> None:
        """Send binary data to the client."""
        try:
            await websocket.send_bytes(data)
        except Exception as e:
            logger.error(f"Failed to send binary data: {e}")

    # Get or create session
    session = await state.session_manager.get_or_create_session(
        send_message=send_message,
        send_binary=send_binary,
        session_id=session_id,
    )

    # Send connected message
    await send_message(
        ConnectedMessage(
            session_id=session_id,
            server_version=__version__,
        )
    )

    # Send initial session state (spaces, MCPs, settings)
    asyncio.create_task(session.send_initial_state())

    try:
        while True:
            # Receive message (can be text or binary)
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            elif message["type"] == "websocket.receive":
                if "text" in message:
                    # JSON message
                    await handle_json_message(session, message["text"], send_message)
                elif "bytes" in message:
                    # Binary audio data
                    session.add_audio_chunk(message["bytes"])

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {websocket.client}")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        try:
            await send_message(ErrorMessage(message=str(e), fatal=True))
        except Exception:
            pass
    finally:
        logger.info(f"Connection closed: {websocket.client}")


async def handle_json_message(
    session: Any,  # Session type
    raw_message: str,
    send_message: Any,
) -> None:
    """
    Handle an incoming JSON message.

    Args:
        session: The voice session
        raw_message: Raw JSON string
        send_message: Callback to send responses
    """
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {e}")
        await send_message(ErrorMessage(message="Invalid JSON", code="parse_error"))
        return

    msg = parse_client_message(data)

    if msg is None:
        logger.warning(f"Unknown message type: {data.get('type')}")
        await send_message(
            ErrorMessage(message=f"Unknown message type: {data.get('type')}", code="unknown_type")
        )
        return

    # Handle message by type
    if isinstance(msg, TextMessage):
        # Process text input in background
        asyncio.create_task(session.process_text(msg.content))

    elif isinstance(msg, AudioStartMessage):
        session.start_audio_input(msg.format.value)

    elif isinstance(msg, AudioEndMessage):
        # Process audio in background
        asyncio.create_task(session.end_audio_input())

    elif isinstance(msg, CancelMessage):
        await session.cancel()

    elif isinstance(msg, ConfigMessage):
        asyncio.create_task(session.process_config(msg))

    elif isinstance(msg, PingMessage):
        await send_message(PongMessage())


# =============================================================================
# CLI Entry Point
# =============================================================================


def run_server(
    host: str | None = None,
    port: int | None = None,
    config_path: str | None = None,
    log_level: str = "INFO",
) -> None:
    """
    Run the WebSocket server.

    Args:
        host: Override host from config
        port: Override port from config
        config_path: Path to config file
        log_level: Logging level
    """
    import uvicorn

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load config
    config = AppConfig.load(config_path) if config_path else AppConfig.load()

    # Apply overrides
    if host:
        config.server.host = host
    if port:
        config.server.port = port

    # Ensure token exists
    token = config.ensure_token()

    # Save config if token was generated
    config_file = AppConfig.get_default_config_path()
    if not config_file.exists():
        config.save(config_file)
        logger.info(f"Saved config to {config_file}")

    # Print connection info
    print(f"\n{'=' * 60}")
    print(f"Agentil Agent Server v{__version__}")
    print(f"{'=' * 60}")
    print(f"WebSocket URL: ws://{config.server.host}:{config.server.port}/ws")
    print(f"Auth Token:    {token}")
    print(f"{'=' * 60}\n")

    # Create and run app
    from .config import set_config

    set_config(config)

    app = create_app(config)

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_level=log_level.lower(),
    )


# =============================================================================
# Module Entry Point
# =============================================================================


if __name__ == "__main__":
    run_server()
