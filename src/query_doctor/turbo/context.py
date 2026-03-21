"""Context managers for temporarily enabling/disabling QueryTurbo.

Provides turbo_enabled() and turbo_disabled() context managers that
override the global TURBO.ENABLED setting for the current thread.
Supports nesting — the outer override is restored when the inner exits.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager


@contextmanager
def turbo_enabled() -> Generator[None, None, None]:
    """Temporarily enable QueryTurbo for the current thread.

    Overrides the global setting for the duration of the context.
    Supports nesting: the previous override is restored on exit.

    Example::

        with turbo_enabled():
            books = Book.objects.filter(author=author)
    """
    from query_doctor.turbo.patch import _local, set_thread_override

    previous = getattr(_local, "turbo_override", None)
    set_thread_override(True)
    try:
        yield
    finally:
        set_thread_override(previous)


@contextmanager
def turbo_disabled() -> Generator[None, None, None]:
    """Temporarily disable QueryTurbo for the current thread.

    Overrides the global setting for the duration of the context.
    Supports nesting: the previous override is restored on exit.

    Example::

        with turbo_disabled():
            books = Book.objects.filter(author=author)
    """
    from query_doctor.turbo.patch import _local, set_thread_override

    previous = getattr(_local, "turbo_override", None)
    set_thread_override(False)
    try:
        yield
    finally:
        set_thread_override(previous)
