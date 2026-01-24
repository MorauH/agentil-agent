"""
Manages mcp-server installations
"""

import subprocess
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

BASE_PATH = Path.home() / ".config" / "agentil-agent" / "mcp-servers" # TODO: Temporary path value

def get_remote_repo(repo_url: str, ref: str = "main") -> str:
    """
    Clone a git repository (shallow) or return path to existing local clone.
    
    The repo is stored in BASE_PATH under a folder name derived from:
    - the repo name (e.g. "myproject")
    - the branch/ref (e.g. "myproject--main")
    
    Args:
        repo_url: Git URL (https://github.com/user/repo.git, git@..., etc.)
        ref:      Branch, tag or commit to check out (default: "main")
    
    Returns:
        str: Absolute path to the local repository directory
    
    Raises:
        subprocess.CalledProcessError: If cloning fails
        ValueError: If repo_url looks invalid
    """
    BASE_PATH.mkdir(parents=True, exist_ok=True)

    # Extract a clean repo name (e.g. "owner/repo" → "repo", or full if needed)
    parsed = urlparse(repo_url)
    path_parts = parsed.path.strip("/").rstrip(".git").split("/")
    if len(path_parts) >= 1:
        repo_name = path_parts[-1]
    else:
        raise ValueError(f"Could not parse repo name from URL: {repo_url}")

    # Folder name = repo_name--ref  (helps distinguish branches)
    folder_name = f"{repo_name}--{ref.replace('/', '-')}"
    repo_dir = BASE_PATH / folder_name

    if repo_dir.exists() and (repo_dir / ".git").is_dir():
        # Already exists → just return the path
        # Optional: you could do `git fetch + reset --hard` here if you want freshness
        return str(repo_dir.resolve())

    # Clone if missing
    clone_cmd = [
        "git", "clone",
        "--depth", "1",
        "--single-branch",
        "--branch", ref,
        repo_url,
        str(repo_dir)
    ]

    try:
        subprocess.check_call(clone_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        if repo_dir.exists():
            # Partial clone → clean up
            import shutil
            shutil.rmtree(repo_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone {repo_url}@{ref}:\n{e}")

    return str(repo_dir.resolve())


def get_mcp_executable(mcp_path, nix_attr: str = ".") -> str:
    """
    Builds (or reuses) a local Nix flake/package and returns a path
    pointing to the main executable, via the 'result' symlink.

    Args:
        path: Directory of project with nix flake 

    Returns:
        str: Path to output executable

    Nix automatically avoids rebuild if the derivation inputs are unchanged.

    Raises RuntimeError on build failure.
    """
    path = Path(mcp_path).resolve()

    installable = f"{path}#{nix_attr}" if nix_attr != "." else str(path)

    cmd = [
        "nix", "build",
        installable,
        "--print-out-paths",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"nix build failed for {installable}\n"
            f"stderr:\n{e.stderr}\n"
            f"stdout:\n{e.stdout}"
        ) from e
    
    bin_dir = path / "result/bin"

    if not bin_dir.is_dir():
        raise RuntimeError(f"No bin/ directory found at {bin_dir}")

    # Find visible, executable files
    binaries = [
        p for p in bin_dir.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and os.access(p, os.X_OK)
    ]

    if not binaries:
        raise RuntimeError(f"No visible executable binaries found in {bin_dir}")

    if len(binaries) > 1:
        names = [p.name for p in binaries]
        raise RuntimeError(
            f"Found multiple visible executables in {bin_dir}: {names}\n"
            "Don't know which one to pick. Consider specifying the expected name."
        )

    return str(binaries[0])

if __name__ == "__main__":
    try:
        cloned_repo = get_remote_repo(repo_url="git@github.com:agentil-ai/mcp-rag.git")
        executable_path = get_mcp_executable(mcp_path=cloned_repo)
        print(executable_path)
    except Exception as e:
        print("Failed: ", e)


