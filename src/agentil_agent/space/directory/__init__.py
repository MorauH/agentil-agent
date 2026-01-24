"""
Basic directory implementation.

No containerization
"""

from .space import DirectorySpace, DirectorySpaceFactory

__all__ = [
    # Agent
    "DirectorySpace",
    "DirectorySpaceFactory",
]
