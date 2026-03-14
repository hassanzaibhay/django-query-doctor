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

We target **>90% test coverage**. Every new feature must include tests.

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

- Branch per feature: `feat/your-feature`
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Run `pytest` and `ruff check` before every commit
- Open a PR against `main`

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
