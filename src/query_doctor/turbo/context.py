"""Context managers for temporarily enabling/disabling QueryTurbo.

Provides turbo_enabled() and turbo_disabled() context managers that
override the global TURBO.ENABLED setting for the current scope.
Supports nesting — the outer override is restored when the inner exits.

Uses contextvars.ContextVar instead of threading.local() so overrides
are isolated per-coroutine in async/ASGI deployments AND per-thread
in sync/WSGI deployments.
"""

from __future__ import annotations

import contextvars
from collections.abc import Generator
from contextlib import contextmanager

_turbo_override: contextvars.ContextVar[bool | None] = contextvars.ContextVar(
    "turbo_override", default=None
)


def get_turbo_override() -> bool | None:
    """Get the current turbo override for this thread/coroutine.

    Returns:
        True if force-enabled, False if force-disabled, None if no override.
    """
    return _turbo_override.get()


def set_turbo_override(value: bool | None) -> contextvars.Token[bool | None]:
    """Set the turbo override. Returns a token for restoration.

    Args:
        value: True to force enable, False to force disable,
               None to clear the override and use global setting.

    Returns:
        A contextvars.Token that can be used to reset to the previous value.
    """
    return _turbo_override.set(value)


@contextmanager
def turbo_enabled() -> Generator[None, None, None]:
    """Temporarily enable QueryTurbo for the current scope.

    Overrides the global setting for the duration of the context.
    Supports nesting: the previous override is restored on exit.
    Works correctly with both threading (WSGI) and asyncio (ASGI).

    Example::

        with turbo_enabled():
            books = Book.objects.filter(author=author)
    """
    token = _turbo_override.set(True)
    try:
        yield
    finally:
        _turbo_override.reset(token)


@contextmanager
def turbo_disabled() -> Generator[None, None, None]:
    """Temporarily disable QueryTurbo for the current scope.

    Overrides the global setting for the duration of the context.
    Supports nesting: the previous override is restored on exit.
    Works correctly with both threading (WSGI) and asyncio (ASGI).

    Example::

        with turbo_disabled():
            books = Book.objects.filter(author=author)
    """
    token = _turbo_override.set(False)
    try:
        yield
    finally:
        _turbo_override.reset(token)
