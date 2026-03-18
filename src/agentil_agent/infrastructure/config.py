"""
Configuration management for Agentil Agent Infrastructure.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
# Main Configuration
# =============================================================================


class InfraConfig(BaseModel):
    """Main configuration for Agentil Agent Infrastructure."""

    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)


# =============================================================================
# CLI Testing
# =============================================================================


if __name__ == "__main__":
    config = InfraConfig()
    print("Default configuration:")
    print(config.to_toml())
