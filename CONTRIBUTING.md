# Contributing to django-query-doctor

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/hassanzaibhay/django-query-doctor.git
cd django-query-doctor
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_nplusone.py -v

# Run with coverage
pytest --cov=query_doctor --cov-report=term-missing
```

CI enforces a minimum of **85% coverage** (`pyproject.toml` `fail_under`). Every new feature must include tests; a module at 0% coverage is considered a process bug.

## Code Quality

Run all checks before submitting a PR:

```bash
# Lint
ruff check src/ tests/

# Format
ruff format src/ tests/ --check

# Type check
mypy src/query_doctor/
```

## Coding Standards

- **Docstrings**: Every public function/method and every module must have a docstring.
- **Type hints**: All function signatures must have type annotations.
- **Imports**: Use `from __future__ import annotations` in every file. Order: stdlib, third-party, Django, local.
- **No runtime deps**: Only Django is required. Rich is optional (`try: from rich... except ImportError: ...`).
- **Never crash the host app**: All analysis code must be wrapped in try/except. If we error, log a warning and let the request proceed.

## Adding a New Analyzer

1. Create `src/query_doctor/analyzers/your_analyzer.py`
2. Subclass `BaseAnalyzer` and implement `analyze()`
3. Return `Prescription` objects with severity, description, fix suggestion, and callsite
4. Write tests in `tests/test_your_analyzer.py` covering:
   - Positive case (issue detected)
   - Negative case (no false positive)
   - Edge cases
   - Threshold boundaries
5. Register your analyzer in `middleware.py`, `context_managers.py`, and `pytest_plugin.py`

## Adding a New Reporter

1. Create `src/query_doctor/reporters/your_reporter.py`
2. Implement `render(report) -> str` and `report(report) -> None`
3. Write tests covering output format, file writing, and edge cases

## Git Workflow

- **No direct commits or pushes to `main`.** Every change lands via a
  `feat/*` or `fix/*` branch (also `docs/*`, `chore/*`, `test/*` as fits)
  → pull request → review → squash-merge to `main`.
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Run `pytest`, `ruff check`, `ruff format --check`, and `mypy` before every
  commit and before opening a PR.
- Use the PR template (`.github/pull_request_template.md`) — it prompts for
  the summary, type, exact CHANGELOG entry, testing performed, and a
  pre-merge checklist.
- If your change is user-facing, add it under `## [Unreleased]` in
  `CHANGELOG.md` (see [Changelog](#changelog) below for the test). Do not
  scatter version notes elsewhere.
- GitHub's `main-protection` ruleset guards `main`. It is configured by the
  repo owner in GitHub settings; it is not something contributors or tooling
  configure from the CLI. It enforces: pull request required before merge,
  unresolved review threads block merging, force-push blocked, branch
  deletion blocked, linear history, and signed commits. It requires **no**
  approving reviews and **no status checks**, so a red CI run does not
  mechanically block a merge. Keeping the gates green before merge is a
  convention this project holds by review, not a rule GitHub enforces.

### Optional: pre-push hook

One-time setup, after installing dev deps:

```bash
pre-commit install --hook-type pre-push
```

This runs `ruff check`, `ruff format --check`, `mypy`, the docs truth sweep,
and `pytest` on `git push`; any failure aborts the push. It needs the dev
deps (`pip install -e ".[dev]"`) installed in your active environment —
normally your virtualenv. `scripts/hookenv.py` resolves that interpreter
explicitly rather than reading `PATH`, and prints which one it used.

**This is local convenience, not enforcement.** `git push --no-verify`
bypasses it, and a contributor who hasn't run `pre-commit install` gets no
gate at all. Nor is CI a mechanical wall: the `main-protection` ruleset
requires a pull request but does not require any status check, so CI failing
will not by itself stop a merge. Whether a red run blocks a merge is a
judgement made by whoever reviews the PR.

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The `## [Unreleased]` section at the top collects changes since the last
release. Add a line under `[Unreleased]` (in `### Added` / `### Changed` /
`### Fixed` / `### Removed` as appropriate) if, and only if, someone who runs
`pip install django-query-doctor` could act on your change: a behavior change,
a new or removed feature, a breaking change, a bug fix, a packaging or version
change, or a correction to documentation they read. Changes to this
repository's own development process stay out, however useful: CI wiring,
pre-commit or pre-push hooks, lint or type-check coverage of `scripts/`, PR
templates, this guide, coverage-upload settings, badges. Shipping a feature
*for* users' CI is user-facing; changing *our* CI is not. On release,
`[Unreleased]` is renamed to the version heading and a new empty
`[Unreleased]` is added above it.

Version headings carry the actual PyPI upload date. A version that is staged
but not yet published uses `- Unreleased` in place of the date; setting the
real date is part of the publish step.

The version itself lives in exactly one place, `src/query_doctor/__init__.py`;
`pyproject.toml` declares `dynamic = ["version"]` and hatchling derives the
distribution metadata from it. Because that metadata is snapshotted at install
time, **a version bump requires `pip install -e "."` before the suite will
pass** — `test_version` compares the runtime `__version__` against the
installed distribution, so a stale editable install fails it. The red is
accurate: the installed artifact really is out of date.

## TDD

We follow test-driven development:

1. Write a failing test
2. Implement the minimum code to pass
3. Refactor if needed
4. Repeat

## Reporting Issues

Use [GitHub Issues](https://github.com/hassanzaibhay/django-query-doctor/issues) to report bugs or request features. Include:

- Python and Django versions
- Minimal reproduction steps
- Expected vs actual behavior

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
