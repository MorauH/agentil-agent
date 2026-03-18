"""
Torch utils
"""

import warnings
import logging
import torch

logger = logging.getLogger(__name__)


def get_cuda_compute_capability() -> tuple[int, int] | None:
    """
    Get the CUDA compute capability of the current GPU.

    Returns:
        Tuple of (major, minor) version, or None if CUDA unavailable.
    """
    if not torch.cuda.is_available():
        return None
    try:
        device = torch.cuda.current_device()
        return torch.cuda.get_device_capability(device)
    except Exception:
        return None


def is_cuda_compatible() -> bool:
    """
    Check if cuda is available and compatible with the installed PyTorch version.

    Tests by running a small tensor operation on CUDA.

    Returns:
        True if CUDA works, False otherwise.
    """
    if not torch.cuda.is_available():
        return False

    try:
        # Suppress the UserWarning about incompatible GPU
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*CUDA capability.*not compatible.*")
            # Try a simple tensor operation on CUDA
            x = torch.tensor([1.0, 2.0, 3.0], device="cuda")
            y = x * 2
            _ = y.cpu()  # Force sync
        return True
    except RuntimeError as e:
        if "no kernel image" in str(e) or "CUDA" in str(e):
            return False
        raise

def is_mps_compatible() -> bool:
    """
    Check if the apple silicon is available and compatible with the installed PyTorch version.

    Returns:
        True if CUDA works, False otherwise.
    """
    if not (torch.backends.mps.is_built() and torch.backends.mps.is_available()):
        return False
    
    return True


def get_best_device(requested: str = "auto") -> str:
    """
    Determine the best available device for inference.

    Args:
        requested: Device preference ('auto', 'cpu', 'cuda', 'mps')

    Returns:
        Device string to use ('cpu', 'cuda', or 'mps')
    """
    if requested == "cpu":
        return "cpu"

    if requested == "mps":
        if is_mps_compatible():
            return "mps"
        logger.warning("MPS requested but not available, falling back to CPU")
        return "cpu"

    if requested in ("cuda", "auto"):
        if torch.cuda.is_available():
            if is_cuda_compatible():
                return "cuda"
            else:
                cap = get_cuda_compute_capability()
                cap_str = f"sm_{cap[0]}{cap[1]}" if cap else "unknown"
                logger.warning(
                    f"CUDA device detected (compute capability {cap_str}) but not compatible "
                    f"with installed PyTorch. Falling back to CPU. "
                    f"Consider upgrading PyTorch or use device='cpu' explicitly."
                )
                return "cpu"
        elif requested == "cuda":
            logger.warning("CUDA requested but not available, falling back to CPU")
            return "cpu"

        if is_mps_compatible():
            return "mps"

    return "cpu"
