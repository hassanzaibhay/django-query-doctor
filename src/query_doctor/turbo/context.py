"""Context managers for temporarily enabling/disabling QueryTurbo.

Provides turbo_enabled() and turbo_disabled() context managers that
override the global TURBO.ENABLED setting for the current thread.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def turbo_enabled() -> Generator[None, None, None]:
    """Temporarily enable QueryTurbo for the current thread.

    Overrides the global setting for the duration of the context.
    Useful for benchmarking or testing specific code paths with caching.

    Example::

        with turbo_enabled():
            books = Book.objects.filter(author=author)
    """
    from query_doctor.turbo.patch import set_thread_override

    set_thread_override(True)
    try:
        yield
    finally:
        set_thread_override(None)


@contextmanager
def turbo_disabled() -> Generator[None, None, None]:
    """Temporarily disable QueryTurbo for the current thread.

    Overrides the global setting for the duration of the context.
    Useful when you need to ensure fresh SQL compilation.

    Example::

        with turbo_disabled():
            books = Book.objects.filter(author=author)
    """
    from query_doctor.turbo.patch import set_thread_override

    set_thread_override(False)
    try:
        yield
    finally:
        set_thread_override(None)
