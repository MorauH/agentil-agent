"""
MCP Manager for system-level MCP server management.

Handles installation, tracking, and configuration of MCP servers
that can be enabled in individual spaces.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .types import MCPManifest, MCPServerInfo
from .nix_installer import (
    delete_repo_clone,
    get_mcp_executable,
    get_remote_repo,
    update_remote_repo,
)

logger = logging.getLogger(__name__)

# Registry filename
MCP_REGISTRY_FILENAME = "mcp-servers.json"

# Manifest filename expected in MCP server repos
MCP_MANIFEST_FILENAME = "mcp-manifest.json"


def _load_manifest(repo_path: Path) -> MCPManifest | None:
    """Load ``mcp-manifest.json`` from a cloned MCP server repo.

    Args:
        repo_path: Root directory of the cloned repository.

    Returns:
        Parsed ``MCPManifest``, or ``None`` if the file does not exist
        or cannot be parsed.
    """
    manifest_path = repo_path / MCP_MANIFEST_FILENAME
    if not manifest_path.exists():
        logger.debug("No %s found in %s", MCP_MANIFEST_FILENAME, repo_path)
        return None

    try:
        with open(manifest_path) as f:
            data = json.load(f)
        manifest = MCPManifest.from_dict(data)
        logger.info("Loaded MCP manifest from %s", manifest_path)
        return manifest
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", manifest_path, exc)
        return None


class MCPManager:
    """
    Manages system-level MCP server installations.

    Responsibilities:
    - Install MCP servers from git URLs (using nix)
    - Track installed servers and their executables
    - Provide MCP info to spaces and agents
    - Generate OpenCode-compatible MCP configurations

    MCP servers are installed system-wide (user-level) and can then
    be enabled/disabled per-space.
    """

    def __init__(self, base_path: Path) -> None:
        """
        Initialize the MCP manager.

        Args:
            base_path: Base directory for MCP server installations
                      (e.g., ~/.config/agentil-agent/mcp-servers/)
        """
        self._base_path = base_path
        self._registry: dict[str, MCPServerInfo] = {}
        self._initialized = False

    @property
    def base_path(self) -> Path:
        """Base directory for MCP server installations."""
        return self._base_path

    @property
    def registry_path(self) -> Path:
        """Path to the MCP servers registry file."""
        return self._base_path / MCP_REGISTRY_FILENAME

    async def initialize(self) -> None:
        """
        Initialize the MCP manager.

        Creates the base directory and loads the registry.
        """
        if self._initialized:
            return

        logger.info(f"Initializing MCP manager at {self._base_path}")

        # Create base directory
        self._base_path.mkdir(parents=True, exist_ok=True)

        # Load existing registry
        self._load_registry()

        # Validate installed servers (check executables still exist)
        self._validate_installed()

        self._initialized = True
        logger.info(f"MCP manager initialized with {len(self._registry)} servers")

    async def shutdown(self) -> None:
        """Shutdown the MCP manager and save registry."""
        logger.info("Shutting down MCP manager")
        self._save_registry()
        self._initialized = False

    def _load_registry(self) -> None:
        """Load MCP server registry from disk."""
        if not self.registry_path.exists():
            self._registry = {}
            return

        try:
            with open(self.registry_path) as f:
                data = json.load(f)

            self._registry = {
                info["id"]: MCPServerInfo.from_dict(info)
                for info in data.get("servers", [])
            }
            logger.debug(f"Loaded {len(self._registry)} MCP servers from registry")

        except Exception as e:
            logger.warning(f"Failed to load MCP registry: {e}")
            self._registry = {}

    def _save_registry(self) -> None:
        """Save MCP server registry to disk."""
        try:
            data = {
                "servers": [info.to_dict() for info in self._registry.values()]
            }
            with open(self.registry_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved {len(self._registry)} MCP servers to registry")

        except Exception as e:
            logger.warning(f"Failed to save MCP registry: {e}")

    def _validate_installed(self) -> None:
        """Validate that installed MCP servers still have valid executables."""
        invalid = []
        for server_id, info in self._registry.items():
            if not Path(info.executable_path).exists():
                logger.warning(
                    f"MCP server '{server_id}' executable not found: "
                    f"{info.executable_path}"
                )
                invalid.append(server_id)

        # Remove invalid entries
        for server_id in invalid:
            del self._registry[server_id]

        if invalid:
            self._save_registry()
            logger.info(f"Removed {len(invalid)} invalid MCP servers from registry")

    def list_servers(self) -> list[MCPServerInfo]:
        """
        List all installed MCP servers.

        Returns:
            List of MCPServerInfo objects
        """
        return list(self._registry.values())

    def get_server(self, server_id: str) -> MCPServerInfo | None:
        """
        Get information about an installed MCP server.

        Args:
            server_id: MCP server identifier

        Returns:
            MCPServerInfo or None if not found
        """
        return self._registry.get(server_id)

    async def install_from_url(
        self,
        url: str,
        ref: str = "main",
        server_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> MCPServerInfo:
        """
        Install an MCP server from a git URL.

        Clones the repository and builds using nix.  If the repo contains
        an ``mcp-manifest.json``, its metadata is read and stored in the
        registry alongside the server info.

        Args:
            url: Git repository URL
            ref: Git ref (branch, tag, or commit)
            server_id: Optional custom ID (default: derived from repo name)
            name: Optional human-readable name
            description: Optional description

        Returns:
            MCPServerInfo for the installed server

        Raises:
            RuntimeError: If installation fails
        """
        logger.info(f"Installing MCP server from {url} (ref: {ref})")

        # Clone the repository
        repo_path = get_remote_repo(url, ref)
        logger.info(f"Cloned to {repo_path}")

        # Build with nix and get executable path
        executable_path = get_mcp_executable(repo_path)
        logger.info(f"Built executable: {executable_path}")

        # Derive ID from repo name if not provided
        if not server_id:
            # Extract repo name from path
            server_id = Path(repo_path).name.split("--")[0]

        # Load manifest if present
        manifest = _load_manifest(Path(repo_path))

        # Manifest fields provide defaults; explicit args take priority
        effective_name = name or (manifest.name if manifest else None) or server_id
        effective_desc = description or (manifest.description if manifest else None)
        effective_version = (manifest.version if manifest else None)

        # Create MCPServerInfo
        info = MCPServerInfo(
            id=server_id,
            name=effective_name,
            executable_path=executable_path,
            description=effective_desc,
            version=effective_version,
            source_type="git",
            source_url=url,
            source_ref=ref,
            manifest=manifest,
        )

        # Register it
        self._registry[server_id] = info
        self._save_registry()

        logger.info(f"Installed MCP server '{server_id}'")
        return info

    async def update_server(self, server_id: str) -> MCPServerInfo:
        """
        Update a git-installed MCP server by re-cloning and rebuilding.

        Deletes the existing clone directory, performs a fresh shallow clone,
        and rebuilds with nix. The registry entry is updated with the new
        executable path and manifest.

        Args:
            server_id: MCP server identifier

        Returns:
            Updated MCPServerInfo

        Raises:
            ValueError: If server not found or not a git-installed server
            RuntimeError: If clone or build fails
        """
        info = self._registry.get(server_id)
        if info is None:
            raise ValueError(f"MCP server '{server_id}' not found")

        if info.source_type != "git":
            raise ValueError(
                f"Cannot update MCP server '{server_id}': "
                f"only git-installed servers can be updated (type: {info.source_type})"
            )

        if not info.source_url:
            raise ValueError(
                f"Cannot update MCP server '{server_id}': no source URL recorded"
            )

        ref = info.source_ref or "main"
        logger.info(f"Updating MCP server '{server_id}' from {info.source_url} (ref: {ref})")

        # Delete old clone and re-clone
        repo_path = update_remote_repo(info.source_url, ref)
        logger.info(f"Re-cloned to {repo_path}")

        # Rebuild with nix
        executable_path = get_mcp_executable(repo_path)
        logger.info(f"Rebuilt executable: {executable_path}")

        # Re-read manifest
        manifest = _load_manifest(Path(repo_path))

        # Update the registry entry
        info.executable_path = executable_path
        info.manifest = manifest

        # Update metadata from manifest if not overridden at install time
        if manifest:
            if manifest.name:
                info.name = manifest.name
            if manifest.description:
                info.description = manifest.description
            if manifest.version:
                info.version = manifest.version

        self._save_registry()

        logger.info(f"Updated MCP server '{server_id}'")
        return info

    def register_local(
        self,
        server_id: str,
        executable_path: str | Path,
        name: str | None = None,
        description: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> MCPServerInfo:
        """
        Register a locally-installed MCP server.

        Use this for MCP servers that are already installed on the system
        (not via this manager).

        Args:
            server_id: Unique identifier
            executable_path: Path to the executable
            name: Optional human-readable name
            description: Optional description
            args: Optional default arguments
            env: Optional environment variables

        Returns:
            MCPServerInfo for the registered server
        """
        executable_path = Path(executable_path)
        if not executable_path.exists():
            raise FileNotFoundError(f"Executable not found: {executable_path}")

        info = MCPServerInfo(
            id=server_id,
            name=name or server_id,
            executable_path=str(executable_path),
            description=description,
            source_type="local",
            args=args or [],
            env=env or {},
        )

        self._registry[server_id] = info
        self._save_registry()

        logger.info(f"Registered local MCP server '{server_id}'")
        return info

    def unregister(self, server_id: str) -> bool:
        """
        Unregister an MCP server.

        Note: This does not delete the actual files, just removes it
        from the registry. Use delete_server() for full cleanup.

        Args:
            server_id: MCP server identifier

        Returns:
            True if removed, False if not found
        """
        if server_id not in self._registry:
            return False

        del self._registry[server_id]
        self._save_registry()

        logger.info(f"Unregistered MCP server '{server_id}'")
        return True

    async def delete_server(self, server_id: str, cleanup_files: bool = True) -> bool:
        """
        Delete an MCP server: unregister and optionally remove cloned files.

        For git-installed servers, this also deletes the local clone
        directory (the shallow clone and nix build artifacts).

        Args:
            server_id: MCP server identifier
            cleanup_files: If True, delete the clone directory for
                          git-installed servers. Default True.

        Returns:
            True if the server was found and deleted, False if not found.
        """
        info = self._registry.get(server_id)
        if info is None:
            return False

        # Clean up clone directory for git-installed servers
        if cleanup_files and info.source_type == "git" and info.source_url:
            ref = info.source_ref or "main"
            deleted = delete_repo_clone(info.source_url, ref)
            if deleted:
                logger.info(
                    f"Deleted clone directory for MCP server '{server_id}'"
                )
            else:
                logger.debug(
                    f"No clone directory found for MCP server '{server_id}'"
                )

        # Remove from registry
        del self._registry[server_id]
        self._save_registry()

        logger.info(f"Deleted MCP server '{server_id}'")
        return True

    def get_opencode_mcp_config(
        self,
        server_ids: list[str],
        enabled_by_default: bool = True,
    ) -> dict[str, dict]:
        """
        Generate OpenCode-compatible MCP configuration for specified servers.

        Args:
            server_ids: List of MCP server IDs to include
            enabled_by_default: Whether servers should be enabled by default

        Returns:
            Dictionary suitable for opencode.json "mcp" section

        Example output:
            {
                "rag-mcp": {
                    "type": "local",
                    "command": ["./result/bin/rag-mcp"],
                    "enabled": true
                }
            }
        """
        config = {}
        for server_id in server_ids:
            info = self._registry.get(server_id)
            if info:
                config[server_id] = info.get_opencode_config(enabled=enabled_by_default)
            else:
                logger.warning(f"MCP server '{server_id}' not found in registry")

        return config

    def get_all_opencode_mcp_config(self, enabled_ids: list[str] | None = None) -> dict[str, dict]:
        """
        Generate OpenCode-compatible MCP configuration for all servers.

        Args:
            enabled_ids: List of server IDs that should be enabled.
                        If None, all are enabled.

        Returns:
            Dictionary suitable for opencode.json "mcp" section
        """
        config = {}
        for server_id, info in self._registry.items():
            enabled = enabled_ids is None or server_id in enabled_ids
            config[server_id] = info.get_opencode_config(enabled=enabled)

        return config
