#!/usr/bin/env python
"""
Example 2: Context Manager — diagnose_queries()

Use in tests, scripts, or anywhere you want targeted diagnosis.
"""

print("=" * 60)
print("Example 2: Context Manager")
print("=" * 60)

print("""
# In a test:
from query_doctor import diagnose_queries

def test_book_list_optimized():
    with diagnose_queries() as report:
        books = list(Book.objects.select_related('author').all())
        for book in books:
            _ = book.author.name

    assert report.total_queries <= 2
    assert report.issues == 0
    assert not report.has_critical


# In a script or view:
with diagnose_queries() as report:
    # ... your code ...
    pass

if report.has_critical:
    print(f"CRITICAL issues found: {report.n_plus_one_count} N+1 patterns")
    for rx in report.prescriptions:
        print(f"  {rx.severity.value}: {rx.description}")
        print(f"  Fix: {rx.fix_suggestion}")
        print(f"  At: {rx.callsite.filepath}:{rx.callsite.line_number}")


# Properties available on DiagnosisReport:
# report.total_queries      — int
# report.total_time_ms      — float
# report.prescriptions      — list[Prescription]
# report.issues             — int (count of prescriptions)
# report.has_critical        — bool
# report.n_plus_one_count   — int
# report.captured_queries   — list[CapturedQuery]
""")
