# Pytest Plugin

django-query-doctor includes a pytest plugin that is **automatically registered** when the package is installed. No additional configuration is needed. The plugin provides markers, fixtures, and context managers for asserting query behavior in your test suite.

---

## Markers

### `@pytest.mark.query_budget`

Assert that a test does not exceed a maximum number of database queries:

```python
import pytest


@pytest.mark.django_db
@pytest.mark.query_budget(max_queries=5)
def test_book_list_view(client):
    """The book list endpoint should execute at most 5 queries."""
    response = client.get("/api/books/")
    assert response.status_code == 200
```

If the test executes more than 5 queries, it **fails** with a detailed report:

```
FAILED test_views.py::test_book_list_view - QueryBudgetExceeded:
  Expected at most 5 queries, but 23 were executed.

  Top query groups:
    1. SELECT "myapp_author".* FROM "myapp_author" WHERE ... (x18) — myapp/models.py:47
    2. SELECT "myapp_book".* FROM "myapp_book" (x1) — myapp/views.py:83
    3. SELECT "myapp_publisher".* FROM "myapp_publisher" WHERE ... (x3) — myapp/serializers.py:12
    4. SELECT COUNT(*) FROM "myapp_book" (x1) — django/core/paginator.py:96
```

### `@pytest.mark.no_nplusone`

Assert that a test does not trigger any N+1 query patterns:

```python
import pytest


@pytest.mark.django_db
@pytest.mark.no_nplusone
def test_book_detail_serializer(client, book):
    """The book detail endpoint should not have N+1 queries."""
    response = client.get(f"/api/books/{book.pk}/")
    assert response.status_code == 200
```

If an N+1 pattern is detected, the test fails with the prescription details:

```
FAILED test_views.py::test_book_detail_serializer - NPlusOneDetected:
  N+1 detected: 12 queries for table "myapp_category"
  Location: myapp/serializers.py:34 in BookSerializer
  Fix: Add .prefetch_related('categories') to the queryset in your view or serializer
```

### Combining Markers

Markers can be combined on a single test:

```python
@pytest.mark.django_db
@pytest.mark.query_budget(max_queries=10)
@pytest.mark.no_nplusone
def test_dashboard_view(client, admin_user):
    client.force_login(admin_user)
    response = client.get("/dashboard/")
    assert response.status_code == 200
```

---

## The `query_report` Fixture

The `query_report` fixture gives you programmatic access to the full analysis results within a test:

```python
import pytest


@pytest.mark.django_db
def test_inspect_queries(client, query_report):
    """Use the query_report fixture to inspect query details."""
    response = client.get("/api/books/")

    # Access the captured data
    assert query_report.query_count < 15
    assert query_report.total_time_ms < 100

    # Check for specific analyzer results
    nplusone_issues = [
        p for p in query_report.prescriptions
        if p.analyzer == "nplusone"
    ]
    assert len(nplusone_issues) == 0, (
        f"Found {len(nplusone_issues)} N+1 issues: "
        f"{[p.issue for p in nplusone_issues]}"
    )

    # Inspect individual queries
    for query in query_report.queries:
        assert query.time_ms < 50, (
            f"Slow query ({query.time_ms}ms): {query.sql[:100]}"
        )
```

The `query_report` object exposes:

| Attribute | Type | Description |
|---|---|---|
| `queries` | `list[CapturedQuery]` | All captured SQL queries with timing and stack traces |
| `query_count` | `int` | Total number of queries executed |
| `total_time_ms` | `float` | Total query execution time in milliseconds |
| `prescriptions` | `list[Prescription]` | All prescriptions from all analyzers |
| `fingerprints` | `dict[str, list]` | Queries grouped by their fingerprint hash |

---

## Context Manager in Tests

For fine-grained control, use the `diagnose_queries()` context manager directly in tests:

```python
from query_doctor.context_managers import diagnose_queries


@pytest.mark.django_db
def test_specific_code_path():
    """Analyze only the queries within the context manager."""
    # Queries outside the context manager are not captured
    User.objects.count()

    with diagnose_queries() as report:
        books = list(Book.objects.select_related("author").all())
        for book in books:
            _ = book.author.name  # Should NOT trigger N+1

    assert report.query_count == 1  # Only the one SELECT with JOIN
    assert len(report.prescriptions) == 0  # No issues
```

---

## CI Integration

The pytest plugin works seamlessly in CI. Add the `--query-doctor` flag to your pytest invocation to enable additional output:

```bash
pytest --query-doctor -v
```

This flag:

- Prints a summary of all query issues found across the entire test run.
- Generates a `query-doctor-report.json` file in the current directory.
- Returns a non-zero exit code if any test fails due to query budget or N+1 violations.

> **Tip:** Combine the pytest plugin with the `check_queries` management command in your CI pipeline. The pytest plugin catches issues in your test scenarios, while `check_queries` catches issues in endpoint responses that your tests might not cover. See [CI Integration](ci-integration.md) for a complete workflow.

### Example: Gradual Adoption

If you are adding django-query-doctor to an existing project, you can adopt it incrementally:

1. Start by adding `@pytest.mark.no_nplusone` to your most critical view tests.
2. Use `@pytest.mark.query_budget` with generous limits on new tests.
3. Tighten the budgets over time as you optimize.

```python
# Start generous
@pytest.mark.query_budget(max_queries=50)
def test_legacy_dashboard(client):
    ...

# After optimization
@pytest.mark.query_budget(max_queries=8)
def test_legacy_dashboard(client):
    ...
```

---

## Configuration

The pytest plugin respects all `QUERY_DOCTOR` settings from your Django settings file. You can also override settings per-test using the `settings` fixture:

```python
@pytest.mark.django_db
def test_with_custom_config(client, settings):
    settings.QUERY_DOCTOR = {
        "ANALYZERS": ["nplusone"],  # Only run N+1 detection
        "NPLUSONE_THRESHOLD": 3,    # Flag after 3 repeated queries
    }
    response = client.get("/api/books/")
    assert response.status_code == 200
```

---

## Further Reading

- [CI Integration](ci-integration.md) -- Full CI pipeline with pytest and management commands.
- [How It Works](how-it-works.md) -- Understanding the analysis pipeline.
- [Query Ignore](query-ignore.md) -- Suppress known issues in tests.
