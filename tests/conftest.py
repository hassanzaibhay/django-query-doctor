"""Pytest configuration for django-query-doctor test suite."""

from __future__ import annotations

# Enables the ``pytester`` fixture used by the pytest-plugin integration tests
# to run an inner pytest session against our own terminal-summary hook.
pytest_plugins = ["pytester"]
