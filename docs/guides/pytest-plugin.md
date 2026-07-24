# Pytest Plugin

django-query-doctor includes a pytest plugin that is **automatically registered** when the package is installed (via the `pytest11` entry point). No additional configuration is needed. The plugin provides one fixture, `query_doctor`; for in-test assertions, the `diagnose_queries()` context manager is the recommended tool.

---

## The `query_doctor` Fixture

Requesting the `query_doctor` fixture in a test turns on query capture for that test. The fixture returns a `DiagnosisReport` object:

```python
import pytest


@pytest.mark.django_db
def test_book_list_view(client, query_doctor):
    response = client.get("/api/books/")
    assert response.status_code == 200
```

> **Important:** The report is populated in a test *finalizer* — after the test body has finished running. Assertions on `query_doctor` inside the test body see an empty report (`total_queries == 0`, `issues == 0`) and pass vacuously. Since 2.1.1 the package says so at runtime: requesting the fixture emits a `QueryDoctorWarning` naming the requesting test. Suites that escalate warnings to errors (`-W error`, or `filterwarnings = error` in pytest configuration) will therefore fail on every test that requests the fixture; suppress the category with `ignore::query_doctor.QueryDoctorWarning` if you accept this behavior. Use the fixture to enable capture; use the [`diagnose_queries()` context manager](#context-manager-in-tests) when you want to assert on results inside the test.

The `DiagnosisReport` object exposes:

| Attribute | Type | Description |
|---|---|---|
| `captured_queries` | `list[CapturedQuery]` | All captured SQL queries |
| `total_queries` | `int` | Total number of queries executed |
| `total_time_ms` | `float` | Total query execution time in milliseconds |
| `prescriptions` | `list[Prescription]` | All prescriptions from all analyzers |
| `issues` | `int` (property) | Number of diagnosed issues (`len(prescriptions)`) |
| `n_plus_one_count` | `int` (property) | Number of N+1 issues |
| `has_critical` | `bool` (property) | True if any issue is CRITICAL severity |

Each `CapturedQuery` has `sql`, `params`, `duration_ms`, `fingerprint`, `normalized_sql`, `callsite`, `is_select`, and `tables`. Each `Prescription` has `issue_type`, `severity`, `description`, `fix_suggestion`, `callsite`, `query_count`, `time_saved_ms`, and `fingerprint`.

### End-of-Session Summary

Because the report is populated at teardown, its findings are surfaced after the session finishes rather than inside the test. A `pytest_terminal_summary` hook (`src/query_doctor/pytest_plugin.py:140`) reads the report each fixture use produced and prints a `query_doctor` section: one header line stating how many fixture-using tests were observed and how many were clean, then **one line per test that had findings** — tests with zero issues produce no line, so the section stays proportionate to the problems found:

```text
================================= query_doctor =================================
observed 12 test(s); 10 clean, 2 with findings
  tests/test_views.py::test_book_list: 48 queries, 1 issue(s)
  tests/test_api.py::test_author_feed: 31 queries, 1 issue(s)
```

This makes the fixture useful for passive, zero-effort reporting across a suite. When you need a test to **fail** on a query problem rather than merely report it, use `diagnose_queries()` (below).

---

## Context Manager in Tests

For assertions on query behavior, use the `diagnose_queries()` context manager. Its report is populated as soon as the `with` block exits, so assertions after the block work as expected:

```python
import pytest

from query_doctor.context_managers import diagnose_queries
from myapp.models import Book


@pytest.mark.django_db
def test_book_list_is_optimized():
    with diagnose_queries() as report:
        books = list(Book.objects.select_related("author").all())
        for book in books:
            _ = book.author.name  # Should NOT trigger N+1

    assert report.total_queries == 1  # Only the one SELECT with JOIN
    assert report.issues == 0  # No prescriptions
```

Enforce a query budget the same way:

```python
@pytest.mark.django_db
def test_dashboard_query_budget(client):
    with diagnose_queries() as report:
        response = client.get("/dashboard/")
        assert response.status_code == 200

    assert report.total_queries <= 10, (
        f"Query budget exceeded: {report.total_queries} queries\n"
        + "\n".join(q.sql[:100] for q in report.captured_queries)
    )
```

Or check for a specific issue type:

```python
from query_doctor.types import IssueType


@pytest.mark.django_db
def test_no_nplusone(client):
    with diagnose_queries() as report:
        client.get("/api/books/")

    assert report.n_plus_one_count == 0, "\n".join(
        p.description
        for p in report.prescriptions
        if p.issue_type == IssueType.N_PLUS_ONE
    )
```

---

## CI Integration

Assertions written with `diagnose_queries()` fail the test when violated, which fails the CI job — no extra pytest flags are needed:

```bash
pytest -v
```

> **Tip:** Combine test-level assertions with the `check_queries` management command in your CI pipeline. Test assertions catch issues in your test scenarios, while `check_queries` catches issues in endpoint responses that your tests might not cover. See [CI Integration](ci-integration.md) for a complete workflow.

### Example: Gradual Adoption

If you are adding django-query-doctor to an existing project, adopt it incrementally:

1. Start by adding `diagnose_queries()` assertions to your most critical view tests.
2. Use generous query budgets on legacy paths.
3. Tighten the budgets over time as you optimize.

```python
# Start generous
@pytest.mark.django_db
def test_legacy_dashboard(client):
    with diagnose_queries() as report:
        client.get("/dashboard/")
    assert report.total_queries <= 50

# After optimization: lower the limit to 8
```

---

## Configuration

Analysis in tests respects the `QUERY_DOCTOR` setting from your Django settings file (see [Configuration](../getting-started/configuration.md)).

> **Note:** The configuration is read once and cached for the lifetime of the process (`get_config()` uses an LRU cache). Overriding `settings.QUERY_DOCTOR` inside an individual test does not take effect after the first configuration read.

---

## Further Reading

- [CI Integration](ci-integration.md) -- Full CI pipeline with pytest and management commands.
- [How It Works](how-it-works.md) -- Understanding the analysis pipeline.
- [Query Ignore](query-ignore.md) -- Suppress known issues in tests.
