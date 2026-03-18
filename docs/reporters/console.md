# Console (Rich) Reporter

The Console reporter outputs prescriptions directly to your terminal during
development. When the [Rich](https://github.com/Textualize/rich) library is
installed, output is formatted with colors, tables, and panels. Without Rich,
it falls back to plain-text output that works in any terminal.

## Installation

The console reporter works out of the box with no extra dependencies. To enable
Rich formatting, install the optional extra:

```bash
pip install django-query-doctor[rich]
```

Or install Rich directly:

```bash
pip install rich
```

!!! tip "Rich extras"
    Installing `django-query-doctor[rich]` also pulls in Rich's markdown and
    syntax highlighting capabilities, which the reporter uses to display SQL
    queries with syntax coloring.

## Configuration

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
    ],

    # Console-specific settings
    "CONSOLE_COLOR_SCHEME": "auto",     # "auto", "dark", "light", "none"
    "CONSOLE_VERBOSITY": "normal",      # "quiet", "normal", "verbose"
    "CONSOLE_SHOW_SQL": True,           # Show the captured SQL in output
    "CONSOLE_SHOW_TRACEBACK": False,    # Show Python stack trace per query
    "CONSOLE_MAX_SQL_LENGTH": 200,      # Truncate SQL after N characters
}
```

### Setting Details

| Setting | Default | Description |
|---------|---------|-------------|
| `CONSOLE_COLOR_SCHEME` | `"auto"` | Color scheme for Rich output. `"auto"` detects terminal capability. `"none"` forces plain text even if Rich is installed. |
| `CONSOLE_VERBOSITY` | `"normal"` | `"quiet"` shows only high-severity issues. `"normal"` shows all prescriptions. `"verbose"` adds SQL and stack traces. |
| `CONSOLE_SHOW_SQL` | `True` | Whether to include the captured SQL statement in each prescription. |
| `CONSOLE_SHOW_TRACEBACK` | `False` | Whether to include the Python stack trace showing where the query originated. |
| `CONSOLE_MAX_SQL_LENGTH` | `200` | Maximum characters of SQL to display before truncation. Set to `0` for no limit. |

## Example Output

### With Rich Installed

```
 query-doctor  GET /api/books/ (127 queries, 4 prescriptions)
+-----------+---------+----------------------------------------------+
| Severity  | Analyzer| Issue                                        |
+-----------+---------+----------------------------------------------+
| CRITICAL  | N+1     | 50 queries fetching Author for each Book.    |
|           |         | Location: views.py:42                        |
|           |         | Fix: Add select_related('author') to queryset|
+-----------+---------+----------------------------------------------+
| WARNING   | Dup     | Query executed 12 times:                     |
|           |         | SELECT "books_category"."id" ...             |
|           |         | Location: serializers.py:18                  |
|           |         | Fix: Hoist query above the loop              |
+-----------+---------+----------------------------------------------+
| WARNING   | Index   | Column 'isbn' in WHERE clause has no index   |
|           |         | Location: views.py:55                        |
|           |         | Fix: Add models.Index(fields=["isbn"]) to Book's Meta.indexes |
+-----------+---------+----------------------------------------------+
| INFO      | Fat SEL | SELECT * fetches 15 unused columns           |
|           |         | Location: views.py:42                        |
|           |         | Fix: Use .only('title', 'author_id')         |
+-----------+---------+----------------------------------------------+
```

### Without Rich (Plain Text Fallback)

```
[query-doctor] GET /api/books/ (127 queries, 4 prescriptions)

[CRITICAL] N+1 Query
  50 queries fetching Author for each Book.
  Location: views.py:42
  Fix: Add select_related('author') to queryset

[WARNING] Duplicate Query
  Query executed 12 times: SELECT "books_category"."id" ...
  Location: serializers.py:18
  Fix: Hoist query above the loop

[WARNING] Missing Index
  Column 'isbn' in WHERE clause has no index
  Location: views.py:55
  Fix: Add models.Index(fields=["isbn"]) to Book's Meta.indexes

[INFO] Fat SELECT
  SELECT * fetches 15 unused columns
  Location: views.py:42
  Fix: Use .only('title', 'author_id')
```

## Verbosity Levels

### Quiet Mode

Only shows `CRITICAL` and `WARNING` prescriptions. Useful when you want to
focus on high-impact issues without noise:

```python
QUERY_DOCTOR = {
    "CONSOLE_VERBOSITY": "quiet",
}
```

### Verbose Mode

Includes the full SQL statement and Python stack trace for every prescription.
Helpful for debugging exactly where a query originates:

```python
QUERY_DOCTOR = {
    "CONSOLE_VERBOSITY": "verbose",
}
```

!!! note "Performance"
    Verbose mode captures full stack traces for every query, which adds
    measurable overhead. Use it only during active debugging, not as a
    persistent setting in development.

## Disabling Colors

If Rich is installed but you want plain-text output (e.g., for piping to a
file), set the color scheme to `"none"`:

```python
QUERY_DOCTOR = {
    "CONSOLE_COLOR_SCHEME": "none",
}
```

Alternatively, Rich respects the `NO_COLOR` environment variable:

```bash
NO_COLOR=1 python manage.py runserver
```

## Using with Context Managers

The console reporter also works with the `diagnose_queries()` context manager
and the `@diagnose` decorator:

```python
from query_doctor.context_managers import diagnose_queries

with diagnose_queries():
    books = list(Book.objects.all())
    for book in books:
        print(book.author.name)  # N+1 detected and printed to console
```

See also: [Reporters Overview](overview.md) | [JSON Reporter](json.md) | [HTML Reporter](html.md)
