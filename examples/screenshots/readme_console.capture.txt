============================================================
Query Doctor Report
Total queries: 13 | Time: 0.2ms | Issues: 2
============================================================

CRITICAL: N+1 detected: 12 queries for table "testapp_author" (via Book.author)
   Location: scripts/regen_examples.py:228 in test_capture_readme_console_output
   Code: _ = book.author.name  # N+1 on author; the base query is the fat SELECT
   Fix: Add .select_related('author') to your Book queryset
   Queries: 12 | Est. savings: ~0.2ms

INFO: Fat SELECT: 8 columns from "testapp_book" including large fields: description
   Location: scripts/regen_examples.py:226 in test_capture_readme_console_output
   Code: books = list(Book.objects.all())
   Fix: Use .defer('description') to skip loading large fields, or .values()/.values_list() if you don't need model instances
   Queries: 1 | Est. savings: ~0.0ms

Note: findings are listed in the order to apply them. Resolving the N+1 above with select_related() widens the base query, so re-read the fat SELECT findings only after that.
