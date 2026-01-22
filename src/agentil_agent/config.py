"""
Configuration management for Agentil Agent Server.

Uses Pydantic for validation and supports TOML config files.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# =============================================================================
# Server Configuration
# =============================================================================


class ServerConfig(BaseModel):
    """WebSocket server settings."""

    host: str = Field(default="0.0.0.0", description="Server bind address")
    port: int = Field(default=8765, description="Server port")
    token: str = Field(
        default="",
        description="Authentication token (auto-generated if empty)",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["*"],
        description="Allowed CORS origins",
    )


# =============================================================================
# OpenCode Configuration
# =============================================================================


class OpenCodeConfig(BaseModel):
    """OpenCode server connection settings."""

    host: str = Field(default="127.0.0.1", description="OpenCode server hostname")
    port: int = Field(default=4096, description="OpenCode server port")
    auto_start: bool = Field(
        default=True, description="Automatically start OpenCode server if not running"
    )
    timeout: float = Field(default=30.0, description="Request timeout in seconds")


# =============================================================================
# STT/TTS Configuration
# =============================================================================


class STTConfig(BaseModel):
    """Speech-to-Text settings."""

    model: Literal["tiny", "base", "small", "medium", "large"] = Field(
        default="base", description="Whisper model size (larger = more accurate but slower)"
    )
    device: str = Field(
        default="auto",
        description="Compute device (auto, cpu, cuda)",
    )


class TTSConfig(BaseModel):
    """Text-to-Speech settings."""

    speaker: Literal["EN-US", "EN-BR", "EN-AU", "EN-Default"] = Field(
        default="EN-BR", description="Speaker voice"
    )
    speed: float = Field(default=1.2, description="Speech speed multiplier (1.0 = normal)")
    device: Literal["auto", "cpu", "cuda", "mps"] = Field(
        default="auto", description="Compute device for TTS model"
    )


# =============================================================================
# Audio I/O Configuration
# =============================================================================


class AudioConfig(BaseModel):
    """Audio format settings for WebSocket communication."""

    input_format: str = Field(
        default="webm/opus",
        description="Expected audio format from clients",
    )
    output_format: str = Field(
        default="mp3",
        description="Audio format sent to clients",
    )
    output_sample_rate: int = Field(
        default=24000,
        description="Sample rate for TTS output",
    )


# =============================================================================
# Agent Backend Configuration
# =============================================================================


class AgentBackendConfig(BaseModel):
    """Agent backend settings (which AI agent implementation to use)."""

    type: str = Field(
        default="opencode",
        description="Backend agent implementation to use (e.g., opencode)",
    )
    opencode: OpenCodeConfig = Field(default_factory=OpenCodeConfig)


# =============================================================================
# Voice Assistant Configuration
# =============================================================================


# Default voice-assistant prompt optimized for TTS output
DEFAULT_ASSISTANT_PROMPT = """You are a voice assistant. Your responses will be spoken aloud via text-to-speech.

Guidelines:
- Keep responses concise and conversational
- Avoid markdown formatting (tables, bullet lists, headers)
- Don't output code blocks unless specifically asked
- Use natural spoken language
- If you need to list items, use "first, second, third" etc.
- For technical content, explain verbally rather than showing code
- Avoid special characters that don't translate well to speech
"""


class AssistantConfig(BaseModel):
    """Voice assistant prompt/settings."""

    name: str = Field(default="voice-assistant", description="Assistant name")
    description: str = Field(
        default="Voice-optimized assistant for general tasks",
        description="Assistant description",
    )
    prompt: str = Field(
        default=DEFAULT_ASSISTANT_PROMPT,
        description="System prompt for the voice assistant",
    )


# =============================================================================
# Sandbox Configuration
# =============================================================================


class SandboxConfig(BaseModel):
    """Sandbox workspace settings."""

    path: str = Field(
        default="~/.config/agentil-agent/workspace",
        description="Path to the sandbox workspace directory",
    )
    auto_create: bool = Field(
        default=True,
        description="Automatically create sandbox directory if it doesn't exist",
    )
    create_opencode_json: bool = Field(
        default=True,
        description="Create opencode.json with voice-assistant agent in sandbox",
    )


# =============================================================================
# Main Configuration
# =============================================================================


class Config(BaseModel):
    """Main configuration for Agentil Agent Server."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    agent: AgentBackendConfig = Field(default_factory=AgentBackendConfig)
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)

    @classmethod
    def get_config_paths(cls) -> list[Path]:
        """Get list of config file paths to search (in priority order)."""
        paths = []

        # Project-level config
        cwd = Path.cwd()
        paths.append(cwd / "agentil-agent.toml")
        paths.append(cwd / ".agentil-agent.toml")

        # User-level config
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        paths.append(config_home / "agentil-agent" / "config.toml")
        paths.append(config_home / "opencode" / "voice.toml")

        # Home directory
        paths.append(Path.home() / ".agentil-agent.toml")

        return paths

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default user config path."""
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_home / "agentil-agent" / "config.toml"

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> "Config":
        """
        Load configuration from file.

        Args:
            config_path: Optional explicit path to config file.
                        If not provided, searches default locations.

        Returns:
            Loaded configuration (or defaults if no config found)
        """
        import tomli

        # If explicit path provided, use it
        if config_path:
            path = Path(config_path)
            if path.exists():
                with open(path, "rb") as f:
                    data = tomli.load(f)
                return cls.model_validate(data)
            raise FileNotFoundError(f"Config file not found: {path}")

        # Search default locations
        for path in cls.get_config_paths():
            if path.exists():
                with open(path, "rb") as f:
                    data = tomli.load(f)
                return cls.model_validate(data)

        # No config found, return defaults
        return cls()

    def save(self, config_path: Path | str) -> None:
        """
        Save configuration to file.

        Args:
            config_path: Path to save config file
        """
        import tomli_w

        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            tomli_w.dump(self.model_dump(), f)

    def to_toml(self) -> str:
        """Export configuration as TOML string."""
        import tomli_w

        return tomli_w.dumps(self.model_dump())

    def ensure_token(self) -> str:
        """
        Ensure the server has an authentication token.

        Generates one if not set and saves config.

        Returns:
            The authentication token
        """
        if not self.server.token:
            self.server.token = secrets.token_urlsafe(32)
        return self.server.token

    def get_working_dir(self) -> Path:
        """Get the resolved working directory path (from sandbox config)."""
        return Path(self.sandbox.path).expanduser().resolve()

    def ensure_working_dir(self) -> Path:
        """Ensure the working directory exists and return its path."""
        work_dir = self.get_working_dir()
        if self.sandbox.auto_create:
            work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir


# =============================================================================
# Global Config Instance
# =============================================================================


_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = Config()
    print("Default configuration:")
    print(config.to_toml())
