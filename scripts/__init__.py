"""Repository tooling: gate checks and artifact regeneration.

Not part of the distributed package (``pyproject.toml`` ships only
``src/query_doctor``). This file exists so the directory is a real package:
``tests/test_hookenv.py`` imports from it, and mypy derives module names
from package structure, so without it ``scripts/regen_examples.py`` is seen
as top-level ``regen_examples`` and per-module configuration keyed on
``scripts.*`` does not apply.
"""
