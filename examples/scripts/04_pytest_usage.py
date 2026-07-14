#!/usr/bin/env python
"""
Example 4: Query assertions in pytest

For in-test assertions, use the diagnose_queries() context manager: its
report is populated as soon as the `with` block exits.

(A `query_doctor` fixture is also auto-registered via the pytest11 entry
point, but its report is populated at test TEARDOWN — assertions on it
inside the test body see an empty report. Prefer diagnose_queries().)
"""

print("=" * 60)
print("Example 4: Query assertions in pytest")
print("=" * 60)

print("""
import pytest

from query_doctor.context_managers import diagnose_queries


@pytest.mark.django_db
def test_book_list_no_nplusone():
    \"\"\"Verify the book list view has no N+1 queries.\"\"\"
    with diagnose_queries() as report:
        books = list(Book.objects.select_related("author").all())
        for book in books:
            _ = book.author.name

    assert report.issues == 0


@pytest.mark.django_db
def test_book_list_query_count():
    \"\"\"Verify query count stays within budget.\"\"\"
    with diagnose_queries() as report:
        list(Book.objects.all())

    assert report.total_queries <= 3


@pytest.mark.django_db
def test_no_duplicate_queries():
    \"\"\"Verify no duplicate queries.\"\"\"
    with diagnose_queries() as report:
        ...  # your view logic

    duplicates = [
        rx for rx in report.prescriptions
        if rx.issue_type.value == "duplicate_query"
    ]
    assert len(duplicates) == 0


# Run with: pytest -v tests/test_queries.py
""")
