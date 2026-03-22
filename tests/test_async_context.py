"""Tests for async-safe context managers using contextvars."""

from __future__ import annotations

import asyncio

from query_doctor.turbo.context import (
    get_turbo_override,
    turbo_disabled,
    turbo_enabled,
)


class TestContextVarsNesting:
    """Context managers properly restore using contextvars tokens."""

    def test_enabled_sets_override(self):
        """turbo_enabled() sets override to True."""
        with turbo_enabled():
            assert get_turbo_override() is True

    def test_disabled_sets_override(self):
        """turbo_disabled() sets override to False."""
        with turbo_disabled():
            assert get_turbo_override() is False

    def test_restores_after_enabled(self):
        """Override is None after turbo_enabled() exits."""
        with turbo_enabled():
            pass
        assert get_turbo_override() is None

    def test_restores_after_disabled(self):
        """Override is None after turbo_disabled() exits."""
        with turbo_disabled():
            pass
        assert get_turbo_override() is None

    def test_nested_disabled_inside_enabled(self):
        """turbo_disabled inside turbo_enabled restores to True."""
        with turbo_enabled():
            assert get_turbo_override() is True
            with turbo_disabled():
                assert get_turbo_override() is False
            assert get_turbo_override() is True

    def test_nested_enabled_inside_disabled(self):
        """turbo_enabled inside turbo_disabled restores to False."""
        with turbo_disabled():
            assert get_turbo_override() is False
            with turbo_enabled():
                assert get_turbo_override() is True
            assert get_turbo_override() is False

    def test_triple_nesting(self):
        """Three levels of nesting all restore correctly."""
        with turbo_enabled():
            assert get_turbo_override() is True
            with turbo_disabled():
                assert get_turbo_override() is False
                with turbo_enabled():
                    assert get_turbo_override() is True
                assert get_turbo_override() is False
            assert get_turbo_override() is True


class TestAsyncContextIsolation:
    """Two concurrent coroutines don't interfere with each other."""

    def test_async_context_isolation(self):
        """Two coroutines running concurrently maintain separate overrides."""
        results: dict[str, bool | None] = {}

        async def coro_enabled() -> None:
            with turbo_enabled():
                await asyncio.sleep(0.01)
                results["enabled"] = get_turbo_override()

        async def coro_disabled() -> None:
            with turbo_disabled():
                await asyncio.sleep(0.01)
                results["disabled"] = get_turbo_override()

        async def main() -> None:
            await asyncio.gather(coro_enabled(), coro_disabled())

        asyncio.run(main())
        assert results["enabled"] is True
        assert results["disabled"] is False

    def test_async_nesting_isolation(self):
        """Nested async context managers restore correctly."""
        results: list[bool | None] = []

        async def nested_coro() -> None:
            with turbo_enabled():
                results.append(get_turbo_override())
                with turbo_disabled():
                    await asyncio.sleep(0.01)
                    results.append(get_turbo_override())
                results.append(get_turbo_override())

        asyncio.run(nested_coro())
        assert results == [True, False, True]

    def test_async_override_cleared_after_exit(self):
        """Override is cleared after async context exits."""
        result: list[bool | None] = []

        async def coro() -> None:
            with turbo_enabled():
                pass
            result.append(get_turbo_override())

        asyncio.run(coro())
        assert result == [None]
