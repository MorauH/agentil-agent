"""
Exception types for space implementations.

Provides a hierarchy of exceptions that all spaces should use,
enabling consistent error handling across different backends.
"""


class SpaceError(Exception):
    """
    Base exception for all space errors.

    All space-specific exceptions should inherit from this,
    allowing callers to catch all agent errors with a single except clause.
    """

    pass


class SpaceNotReadyError(SpaceError):
    """
    Space is not ready.

    Raised when attempting to use an space that hasn't been initialized,
    or that has been closed down.
    """

    pass


class SpaceInitializationError(SpaceError):
    """
    Space failed to initialize.

    Raised when space.initialize() fails due to:
    - Connection errors
    - Missing dependencies
    """

    pass

# Convenience type for catching any space error
SpaceException = SpaceError
