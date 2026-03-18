# Contributing

Thank you for your interest in contributing to django-query-doctor. This guide
covers everything you need to get started: development setup, testing, code
style, and the process for submitting changes.

---

## Development Setup

### Prerequisites

- Python 3.10 or later
- Git

### Clone and Install

```bash
# Fork the repository on GitHub, then clone your fork
git clone https://github.com/YOUR_USERNAME/django-query-doctor.git
cd django-query-doctor

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode with all extras
pip install -e ".[dev,docs,rich,otel]"
```

The `dev` extra installs testing and linting tools. The `docs` extra installs
MkDocs and related packages for building documentation locally.

### Verify Installation

```bash
# Run the test suite
pytest

# Check linting
ruff check src/ tests/

# Check types
mypy src/query_doctor/
```

All three commands should pass before you start making changes.

---

## Running Tests

### Full Test Suite

```bash
pytest
```

### Single Test File

```bash
pytest tests/test_nplusone.py -v
```

### With Coverage

```bash
pytest --cov=query_doctor --cov-report=term-missing
```

!!! info "Coverage target"
    The project targets >90% code coverage. If you add new code, add tests
    that cover it. A module at 0% coverage is considered a process bug.

### Test Database

Tests use a minimal Django project defined in `tests/testapp/` with these
models: `Author`, `Publisher`, `Book` (FK to Author and Publisher),
`Category` (M2M with Book), and `Tag` (M2M with Book).

Use the factories defined in `tests/factories.py` to create test data:

```python
from tests.factories import BookFactory, AuthorFactory

def test_something():
    author = AuthorFactory(name="Test Author")
    book = BookFactory(author=author)
    ...
```

### Test Structure

Tests follow TDD conventions. Each test file mirrors a source file:

| Source | Test |
|--------|------|
| `src/query_doctor/fingerprint.py` | `tests/test_fingerprint.py` |
| `src/query_doctor/analyzers/nplusone.py` | `tests/test_nplusone.py` |
| `src/query_doctor/reporters/console.py` | `tests/test_console_reporter.py` |

For each analyzer, include these test cases:

1. **Positive case** -- the issue is correctly detected
2. **Negative case** -- no false positive when the issue is absent
3. **Edge case** -- boundary conditions (empty querysets, single items)
4. **Threshold boundary** -- behavior at exactly the threshold value

---

## Code Style

### Linting with Ruff

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix issues
ruff check src/ tests/ --fix

# Format code
ruff format src/ tests/

# Check formatting without changes
ruff format src/ tests/ --check
```

### Type Checking with mypy

```bash
mypy src/query_doctor/
```

All function signatures must have type hints. The project uses strict mypy
configuration.

### Conventions

- **Imports**: stdlib, then third-party, then Django, then local. One blank
  line between each group.
- **Docstrings**: Every public function, method, and class has a docstring.
  Use Google-style docstrings:

    ```python
    def normalize_sql(sql: str) -> str:
        """Normalize a SQL statement by replacing literal values with placeholders.

        Args:
            sql: The raw SQL statement to normalize.

        Returns:
            The normalized SQL string with literals replaced by '?'.
        """
    ```

- **Future annotations**: Every file starts with `from __future__ import annotations`.
- **Module docstrings**: Every module has a module-level docstring explaining
  its purpose.
- **No mutable module state**: Use `threading.local()` for per-request state.
- **No direct settings access**: Use `query_doctor.conf.get_config()` instead
  of reading `django.conf.settings` directly.

---

## Submitting Changes

### Workflow

1. **Fork** the repository on GitHub
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
   Use prefixes: `feat/`, `fix/`, `test/`, `docs/`, `refactor/`, `chore/`
3. **Write tests first** (TDD) -- the test should fail before you implement
4. **Implement** the feature or fix
5. **Verify** everything passes:
   ```bash
   pytest
   ruff check src/ tests/
   ruff format src/ tests/ --check
   mypy src/query_doctor/
   ```
6. **Commit** with a conventional commit message:
   ```bash
   git commit -m "feat: add slow-query-log analyzer"
   ```
7. **Push** to your fork and open a **Pull Request** against `main`

### Commit Message Format

```
type: short description

Optional longer description explaining the change in more detail.
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`

### Pull Request Guidelines

- Keep PRs focused on a single change
- Include tests for new functionality
- Update documentation if the change affects public APIs
- Ensure CI passes (tests, lint, type check)
- Reference any related issues in the PR description

!!! warning "Do not commit to main"
    All changes go through pull requests. Direct commits to `main` are not
    accepted.

---

## Reporting Issues

When opening a GitHub issue, include the following information:

```markdown
## Environment
- Python version:
- Django version:
- django-query-doctor version:
- OS:

## Description
What happened and what you expected to happen.

## Steps to Reproduce
1.
2.
3.

## Relevant Code
```python
# Minimal code example that demonstrates the issue
```

## Error Output
```
Paste any error messages or unexpected output here
```
```

!!! tip "Minimal reproduction"
    The most helpful bug reports include a minimal reproduction case. If
    possible, create a small Django project that demonstrates the issue.

---

## Adding a New Analyzer

django-query-doctor is designed to be extended with custom analyzers. Here is
a step-by-step guide for adding a new built-in analyzer.

### 1. Write the Test

Create a test file in `tests/`:

```python title="tests/test_my_analyzer.py"
from __future__ import annotations

import pytest
from query_doctor.analyzers.my_analyzer import MyAnalyzer


class TestMyAnalyzer:
    """Tests for the MyAnalyzer."""

    def test_detects_issue(self, captured_queries_with_issue):
        """Positive case: issue is detected."""
        analyzer = MyAnalyzer()
        prescriptions = analyzer.analyze(captured_queries_with_issue)
        assert len(prescriptions) == 1
        assert prescriptions[0].severity == "high"

    def test_no_false_positive(self, captured_queries_without_issue):
        """Negative case: no issue reported when none exists."""
        analyzer = MyAnalyzer()
        prescriptions = analyzer.analyze(captured_queries_without_issue)
        assert len(prescriptions) == 0

    def test_threshold_boundary(self, captured_queries_at_threshold):
        """Edge case: behavior at exactly the threshold."""
        analyzer = MyAnalyzer()
        prescriptions = analyzer.analyze(captured_queries_at_threshold)
        assert len(prescriptions) == 0  # At threshold, not over
```

### 2. Implement the Analyzer

Create the analyzer in `src/query_doctor/analyzers/`:

```python title="src/query_doctor/analyzers/my_analyzer.py"
"""Analyzer that detects [specific issue type]."""
from __future__ import annotations

from query_doctor.analyzers.base import BaseAnalyzer, Prescription


class MyAnalyzer(BaseAnalyzer):
    """Detects [specific issue] in captured queries."""

    def analyze(self, queries: list[CapturedQuery]) -> list[Prescription]:
        """Examine queries for [specific issue].

        Args:
            queries: List of captured and fingerprinted queries.

        Returns:
            List of prescriptions for any detected issues.
        """
        prescriptions = []
        # Detection logic here
        return prescriptions
```

### 3. Register the Analyzer

Add your analyzer to the default list in `src/query_doctor/conf.py` and
update the documentation in `docs/analyzers/`.

### 4. Submit

Run the full test suite, linter, and type checker, then open a PR.

---

## Building Documentation

```bash
# Install docs dependencies
pip install -e ".[docs]"

# Serve documentation locally with live reload
mkdocs serve

# Build static documentation
mkdocs build
```

The documentation will be available at `http://127.0.0.1:8000/`.
