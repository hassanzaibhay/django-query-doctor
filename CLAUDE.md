# django-query-doctor

Automated diagnosis and prescriptions for slow Django ORM queries.

## Project

- **What**: A pip-installable Django package that intercepts SQL queries at runtime, detects optimization issues (N+1, duplicates, missing indexes, etc.), and generates actionable fix suggestions with exact file:line references.
- **Why**: No existing Django package provides prescriptive query optimization. Tools like debug-toolbar show problems; we prescribe fixes.
- **Inspired by**: Ruby's Bullet gem (8.2k stars) — zero-config, pluggable detection, CI integration.

## Stack

- Python ≥ 3.10, Django ≥ 4.2
- Build: Hatchling (pyproject.toml, PEP 621, src layout)
- Testing: pytest + pytest-django + factory-boy
- Linting: Ruff
- Types: mypy (strict)
- CI: GitHub Actions
- Console output: Rich (optional dependency)

## Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run single test file
pytest tests/test_nplusone.py -v

# Run with coverage
pytest --cov=query_doctor --cov-report=term-missing

# Lint
ruff check src/ tests/
ruff format src/ tests/ --check

# Type check
mypy src/query_doctor/
```

## Architecture

Four-stage pipeline: **INTERCEPT → FINGERPRINT → ANALYZE → REPORT**

```
src/query_doctor/
├── middleware.py          # Django middleware, installs execute_wrapper per request
├── interceptor.py         # execute_wrapper callable, captures queries + stack traces
├── fingerprint.py         # SQL normalization, parameter replacement, SHA-256 hashing
├── stack_tracer.py        # Maps queries to user source code file:line
├── analyzers/             # Pluggable analyzer classes (each detects one issue type)
│   ├── base.py            # BaseAnalyzer ABC with Prescription dataclass
│   ├── nplusone.py        # N+1 detection via fingerprint grouping
│   └── duplicate.py       # Exact + near-duplicate detection
├── reporters/             # Output formatters
│   ├── console.py         # Rich terminal output (falls back to plain text)
│   └── json_reporter.py   # Structured JSON for CI/CD
├── management/commands/   # Django management commands
├── conf.py                # Settings with defaults from Django settings
├── decorators.py          # @diagnose, @query_budget
└── context_managers.py    # with diagnose_queries():
```

## Coding Conventions

- IMPORTANT: Every public function/method has a docstring.
- IMPORTANT: Every module has a module-level docstring explaining its purpose.
- Type hints on ALL function signatures. Ship py.typed.
- Use `from __future__ import annotations` in every file.
- Imports: stdlib → third-party → Django → local. One blank line between groups.
- No runtime dependency beyond Django. Rich is optional: `try: from rich... except ImportError: ...`
- All exceptions inherit from `QueryDoctorError` (defined in `exceptions.py`).
- Settings accessed via `query_doctor.conf.get_config()` only — never read django.conf.settings directly in modules.
- Thread safety: use `threading.local()` for per-request state. Never use module-level mutable state.

## Testing Conventions

- IMPORTANT: Write tests BEFORE implementation (TDD). Never implement without a failing test first.
- Test files mirror source: `src/query_doctor/fingerprint.py` → `tests/test_fingerprint.py`
- Use `tests/testapp/` as a minimal Django project with models: Author, Publisher, Book (FK to Author, FK to Publisher), Category (M2M with Book), Tag (M2M with Book).
- Use `pytest.mark.django_db` for any test touching the database.
- Use `factory_boy` factories in `tests/factories.py` for test data.
- Test each analyzer with: positive case (issue detected), negative case (no false positive), edge case, threshold boundary.
- Target: >90% coverage. 0% coverage on a module = a bug in our process.

## Git Workflow

- Branch per feature: `feat/interceptor`, `feat/nplusone-analyzer`, etc.
- Commit messages: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`
- Run `pytest` and `ruff check` before every commit. Do not commit failing tests.
- Do NOT commit directly to main.

## Key Design Decisions — Do NOT Deviate

1. **execute_wrapper, not connection.queries**: We use `connection.execute_wrapper()` which works without DEBUG=True. Never rely on `connection.queries`.
2. **Prescriptions, not just detection**: Every analyzer returns Prescription objects with: severity, issue description, file:line reference, AND the exact code fix as a string.
3. **Fingerprint-based N+1 detection**: Normalize SQL → hash → group by fingerprint → count. If count > threshold AND pattern matches FK access, it's N+1.
4. **Zero required config**: Package works with just adding the middleware. All settings have defaults.
5. **Never crash the host app**: ALL analysis code is wrapped in try/except. If we error, we log a warning and let the request proceed normally.

## Full Specification

For detailed architecture, analyzer algorithms, data structures, and phased plan:
see `docs/SPEC.md`
