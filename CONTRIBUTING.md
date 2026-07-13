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
- Add your change under `## [Unreleased]` in `CHANGELOG.md` (see
  [Changelog](#changelog) below). Do not scatter version notes elsewhere.
- GitHub branch protection on `main` (require PR before merge, require
  status checks, disallow force-push) is enabled by the repo owner in
  GitHub settings — it is not something contributors or tooling configure
  from the CLI.

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The `## [Unreleased]` section at the top collects changes since the last
release. Every PR that changes behavior, fixes a bug, or adds a feature
should add a line under `[Unreleased]` (in `### Added` / `### Changed` /
`### Fixed` / `### Removed` as appropriate). On release, `[Unreleased]` is
renamed to the version heading and a new empty `[Unreleased]` is added above
it.

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
