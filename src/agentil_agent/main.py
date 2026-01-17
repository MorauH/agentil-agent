"""
CLI entry point for Agentil Agent Server.

Provides commands for running the server and managing configuration.
"""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(version="0.2.0", prog_name="agentil-agent")
def cli() -> None:
    """Agentil Agent Server - Voice interface for OpenCode."""
    pass


@cli.command()
@click.option(
    "--host",
    "-h",
    default=None,
    help="Server host (default: from config or 0.0.0.0)",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=None,
    help="Server port (default: from config or 8765)",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to config file",
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level",
)
def serve(
    host: str | None,
    port: int | None,
    config_path: str | None,
    log_level: str,
) -> None:
    """Start the WebSocket server."""
    from .server import run_server
    
    run_server(
        host=host,
        port=port,
        config_path=config_path,
        log_level=log_level,
    )


@cli.command()
@click.option(
    "--url",
    "-u",
    default="ws://localhost:8765/ws",
    help="WebSocket URL",
)
@click.option(
    "--token",
    "-t",
    required=True,
    help="Authentication token",
)
@click.option(
    "--tts/--no-tts",
    default=False,
    help="Enable TTS audio output",
)
def client(url: str, token: str, tts: bool) -> None:
    """Connect to the server as a text client."""
    import asyncio
    from .client.text_client import run_client
    
    try:
        asyncio.run(run_client(url, token, tts))
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye![/dim]")


@cli.command("config-show")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to config file",
)
def config_show(config_path: str | None) -> None:
    """Show current configuration."""
    from .config import Config
    
    config = Config.load(config_path) if config_path else Config.load()
    console.print(config.to_toml())


@cli.command("config-init")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output path (default: ~/.config/agentil-agent/config.toml)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing config file",
)
def config_init(output: str | None, force: bool) -> None:
    """Generate a default configuration file."""
    from pathlib import Path
    from .config import Config
    
    config = Config()
    
    # Generate a token
    config.ensure_token()
    
    # Determine output path
    if output:
        path = Path(output)
    else:
        path = Config.get_default_config_path()
    
    # Check if exists
    if path.exists() and not force:
        console.print(f"[yellow]Config file already exists: {path}[/yellow]")
        console.print("Use --force to overwrite")
        return
    
    # Save
    config.save(path)
    console.print(f"[green]Config file created: {path}[/green]")
    console.print(f"[dim]Auth token: {config.server.token}[/dim]")


@cli.command("token")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to config file",
)
@click.option(
    "--regenerate",
    "-r",
    is_flag=True,
    help="Generate a new token",
)
def token(config_path: str | None, regenerate: bool) -> None:
    """Show or regenerate the authentication token."""
    import secrets
    from .config import Config
    
    config = Config.load(config_path) if config_path else Config.load()
    
    if regenerate:
        config.server.token = secrets.token_urlsafe(32)
        config_file = Config.get_default_config_path()
        config.save(config_file)
        console.print(f"[green]New token generated and saved to {config_file}[/green]")
    else:
        config.ensure_token()
    
    console.print(f"Token: {config.server.token}")


@cli.command("check")
def check() -> None:
    """Check system dependencies and configuration."""
    from .audio import check_ffmpeg_available
    from .bridge import OpenCodeBridge
    from .config import Config
    
    console.print("[bold]Agentil Agent System Check[/bold]\n")
    
    # Check ffmpeg
    ffmpeg_ok = check_ffmpeg_available()
    if ffmpeg_ok:
        console.print("[green]✓[/green] ffmpeg available")
    else:
        console.print("[red]✗[/red] ffmpeg not found (required for audio conversion)")
    
    # Check OpenCode
    opencode_installed = OpenCodeBridge.is_opencode_installed()
    if opencode_installed:
        version = OpenCodeBridge.get_opencode_version()
        console.print(f"[green]✓[/green] OpenCode installed ({version})")
    else:
        console.print("[red]✗[/red] OpenCode not found")
    
    # Check config
    config = Config.load()
    config_path = None
    for path in Config.get_config_paths():
        if path.exists():
            config_path = path
            break
    
    if config_path:
        console.print(f"[green]✓[/green] Config file: {config_path}")
    else:
        console.print("[yellow]![/yellow] No config file found (using defaults)")
    
    # Check working directory
    working_dir = config.get_working_dir()
    if working_dir.exists():
        console.print(f"[green]✓[/green] Working directory: {working_dir}")
    else:
        console.print(f"[yellow]![/yellow] Working directory doesn't exist: {working_dir}")
        console.print("    [dim](will be created on first run)[/dim]")
    
    # Summary
    console.print()
    if ffmpeg_ok and opencode_installed:
        console.print("[green]All checks passed![/green]")
    else:
        console.print("[yellow]Some dependencies are missing.[/yellow]")


@cli.command("test-tts")
@click.option(
    "--text",
    "-t",
    default="Hello! This is a test of the Agentil Agent text-to-speech system.",
    help="Text to speak",
)
def test_tts(text: str) -> None:
    """Test text-to-speech functionality."""
    from .config import Config
    from .tts import TTSEngine
    
    config = Config.load()
    
    console.print("[bold]Testing TTS...[/bold]")
    console.print(f"Speaker: {config.tts.speaker}")
    console.print(f"Speed: {config.tts.speed}")
    console.print()
    
    tts = TTSEngine(
        device=config.tts.device,
        speaker=config.tts.speaker,
        speed=config.tts.speed,
    )
    
    console.print(f"Speaking: [italic]{text}[/italic]")
    tts.speak(text)
    console.print("[green]TTS test complete![/green]")


@cli.command("test-bridge")
@click.option("--prompt", "-p", default="Say 'Hello from Agentil Agent!' and nothing else.")
def test_bridge(prompt: str) -> None:
    """Test OpenCode bridge connection."""
    import asyncio
    from .config import Config
    from .bridge import OpenCodeBridge, OpenCodeNotInstalledError, OpenCodeConnectionError
    
    config = Config.load()
    
    console.print("[bold]Testing OpenCode Bridge...[/bold]\n")
    
    with OpenCodeBridge(config) as bridge:
        try:
            bridge.ensure_connection()
            console.print(f"[green]✓[/green] Connected to {bridge.base_url}")
            console.print(f"  Server version: {bridge.get_server_version()}\n")
        except OpenCodeNotInstalledError:
            console.print("[red]✗[/red] OpenCode not installed")
            console.print("Install with: npm install -g opencode-ai")
            return
        except OpenCodeConnectionError as e:
            console.print(f"[red]✗[/red] Connection failed: {e}")
            return
        
        session = bridge.create_session(title="Bridge Test")
        console.print(f"[green]✓[/green] Created session: {session.id}\n")
        
        console.print(f"[bold]Prompt:[/bold] {prompt}\n")
        console.print("[bold]Response (streaming):[/bold]")
        
        async def run_streaming():
            async for chunk in bridge.stream_response(prompt, session.id):
                console.print(chunk, end="")
            console.print()
        
        asyncio.run(run_streaming())
        
        bridge.delete_session(session.id)
        console.print("\n[green]Bridge test complete![/green]")


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
