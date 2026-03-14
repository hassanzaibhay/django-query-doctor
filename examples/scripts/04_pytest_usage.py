#!/usr/bin/env python
"""
Example 4: Pytest Plugin

The query_doctor fixture is auto-registered when you install the package.
"""

print("=" * 60)
print("Example 4: Pytest Plugin")
print("=" * 60)

print("""
# No configuration needed — just use the fixture:

def test_book_list_no_nplusone(query_doctor):
    \"\"\"Verify the book list view has no N+1 queries.\"\"\"
    books = list(Book.objects.select_related("author").all())
    for book in books:
        _ = book.author.name

    report = query_doctor.report()
    assert report.issues == 0


def test_book_list_query_count(query_doctor):
    \"\"\"Verify query count stays within budget.\"\"\"
    list(Book.objects.all())

    report = query_doctor.report()
    assert report.total_queries <= 3


def test_no_duplicate_queries(query_doctor):
    \"\"\"Verify no duplicate queries.\"\"\"
    # ... your view logic ...

    report = query_doctor.report()
    duplicates = [
        rx for rx in report.prescriptions
        if rx.issue_type.value == "duplicate_query"
    ]
    assert len(duplicates) == 0


# Run with: pytest -v tests/test_queries.py
# The fixture captures queries during the test and provides the report.
""")
