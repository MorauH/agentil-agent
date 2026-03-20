"""
CLI entry point for Agentil Agent Server.

Provides commands for running the server and managing configuration.
"""

from __future__ import annotations

import click
from rich.console import Console

console = Console()

from agentil_agent import __version__

@click.group()
@click.version_option(version=__version__, prog_name="agentil-server")
def cli() -> None:
    """Agentil Server - Voice agent"""
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
    from .config import AppConfig

    config = AppConfig.load(config_path) if config_path else AppConfig.load()
    console.print(config.to_toml())


@cli.command("config-init")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output path (default: ~/.config/agentil-server/config.toml)",
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
    from .config import AppConfig

    config = AppConfig()

    # Generate a token
    config.ensure_token()

    # Determine output path
    if output:
        path = Path(output)
    else:
        path = AppConfig.get_default_config_path()

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
    from .config import AppConfig

    config = AppConfig.load(config_path) if config_path else AppConfig.load()

    if regenerate:
        config.server.token = secrets.token_urlsafe(32)
        config_file = AppConfig.get_default_config_path()
        config.save(config_file)
        console.print(f"[green]New token generated and saved to {config_file}[/green]")
    else:
        config.ensure_token()

    console.print(f"Token: {config.server.token}")


@cli.command("check")
def check() -> None:
    """Check system dependencies and configuration."""
    import asyncio
    from pathlib import Path
    from agentil_agent.infrastructure.audio import check_ffmpeg_available
    from agentil_agent.core.agent import create_agent, AgentError
    from agentil_agent.core.space import SpaceManager, SpaceError
    from .config import AppConfig
    
    console.print("[bold]Agentil Agent System Check[/bold]\n")

    # Check ffmpeg
    ffmpeg_ok = check_ffmpeg_available()
    if ffmpeg_ok:
        console.print("[green]✓[/green] ffmpeg available")
    else:
        console.print("[red]✗[/red] ffmpeg not found (required for audio conversion)")

    # Check config
    config = AppConfig.load()
    config_path = None
    for path in AppConfig.get_config_paths():
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
    
    loop = asyncio.get_event_loop()

    # Check Space initialization
    space_ok = False
    space_manager = None
    space = None
    try:
        spaces_root = Path(config.core.spaces.spaces_root)
        space_manager = SpaceManager(spaces_root)
        
        space = loop.run_until_complete(space_manager.get_default_space())
        loop.run_until_complete(space.initialize())
        
        space_ok = True
    except SpaceError as err:
        console.print(f"[red]✗[/red] {err}")

    # Check Agent initialization
    agent_ok = False
    try:
        agent = create_agent(config.core.agent.type, config.core)
        
        # Set operating space
        agent.set_space(space)

        async def init_agent() -> None:
            await agent.initialize()
            await agent.shutdown()

        asyncio.run(init_agent())
        agent_ok = True
    except AgentError as err:
        console.print(f"[red]✗[/red] {err}")

    # Shutdown
    try:
        loop.run_until_complete(space_manager.shutdown())
    except Exception:
        pass

    # Summary
    console.print()
    if ffmpeg_ok and space_ok and agent_ok:
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
    from .config import AppConfig
    from agentil_agent.infrastructure.tts import TTSEngine

    config = AppConfig.load()

    console.print("[bold]Testing TTS...[/bold]")
    console.print(f"Speaker: {config.infra.tts.speaker}")
    console.print(f"Speed: {config.infra.tts.speed}")
    console.print()

    tts = TTSEngine(
        device=config.infra.tts.device,
        speaker=config.infra.tts.speaker,
        speed=config.infra.tts.speed,
    )

    console.print(f"Speaking: [italic]{text}[/italic]")
    tts.speak(text)
    console.print("[green]TTS test complete![/green]")


@cli.command("test-agent")
@click.option("--prompt", "-p", default="Say 'Hello from Agentil Agent!' and nothing else.")
def test_agent(prompt: str) -> None:
    """Test configured agent backend."""
    import asyncio
    from pathlib import Path

    from agentil_agent.core.agent import AgentError, create_agent
    from agentil_agent.core.space import SpaceManager
    from .config import AppConfig

    config = AppConfig.load()

    console.print(f"[bold]Testing Agent Backend ({config.core.agent.type})...[/bold]\n")

    async def run() -> None:
        agent = create_agent(config.core.agent.type, config.core)
        space_manager = SpaceManager(Path(config.core.spaces.spaces_root))
        space = await space_manager.get_default_space()
        
        try:
            await space.initialize()

            agent.set_space(space)

            await agent.initialize()
            session = await agent.create_session(title="Agent Test")

            console.print(f"[green]✓[/green] Created session: {session.id}\n")
            console.print(f"[bold]Prompt:[/bold] {prompt}\n")
            console.print("[bold]Response (streaming):[/bold]")

            async for chunk in agent.stream_response(session.id, prompt):
                console.print(chunk, end="")
            console.print()

            await agent.delete_session(session.id)
            console.print("\n[green]Agent test complete![/green]")
        finally:
            await agent.shutdown()
            await space.shutdown()

    try:
        asyncio.run(run())
    except AgentError as e:
        console.print(f"[red]✗[/red] Agent error: {e}")


# =============================================================================
# Entry Point
# =============================================================================


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
