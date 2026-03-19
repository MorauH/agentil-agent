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

from agentil_agent.core import CoreConfig
from agentil_agent.infrastructure import InfraConfig

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
# Main Configuration
# =============================================================================


class AppConfig(BaseModel):
    """Main configuration for Agentil Agent Server."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    core: CoreConfig = Field(default_factory=CoreConfig)
    infra: InfraConfig = Field(default_factory=InfraConfig)

    @classmethod
    def get_config_paths(cls) -> list[Path]:
        """Get list of config file paths to search (in priority order)."""
        paths = []

        # Project-level config
        cwd = Path.cwd()
        paths.append(cwd / "agentil-server.toml")
        paths.append(cwd / ".agentil-server.toml")

        # User-level config
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        paths.append(config_home / "agentil-server" / "config.toml")

        # Home directory
        paths.append(Path.home() / ".agentil-server.toml")

        return paths

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default user config path."""
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_home / "agentil-server" / "config.toml"

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> "AppConfig":
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
        """Get the resolved working directory path (default space workspace)."""
        return self.core.get_spaces_root() / "default" / "workspace"

    def ensure_working_dir(self) -> Path:
        """Ensure the working directory exists and return its path."""
        work_dir = self.get_working_dir()
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir


# =============================================================================
# Global Config Instance
# =============================================================================


_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig.load()
    return _config


def set_config(config: AppConfig) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = AppConfig()
    print("Default configuration:")
    print(config.to_toml())
