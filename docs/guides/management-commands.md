# Management Commands

django-query-doctor ships four management commands for on-demand analysis, budget enforcement, auto-fixing, and full project health scans. These commands work independently of the middleware and are ideal for CI/CD pipelines and one-off investigations.

---

## `check_queries`

Analyze queries for specific URLs or URL patterns and report issues.

### Basic Usage

```bash
# Analyze a single URL
python manage.py check_queries --url /api/books/

# Analyze multiple URLs
python manage.py check_queries --url /api/books/ --url /api/authors/ --url /dashboard/

# Analyze all URLs matching a pattern
python manage.py check_queries --url-pattern "^/api/"
```

### Filter by Severity

Only report issues at or above a given severity level:

```bash
# Only show WARNINGs and CRITICALs (skip INFO)
python manage.py check_queries --url /api/books/ --severity WARNING

# Only show CRITICALs
python manage.py check_queries --url /api/books/ --severity CRITICAL
```

### JSON Output

Output structured JSON for consumption by CI tools or dashboards:

```bash
python manage.py check_queries --url /api/books/ --format json
```

```json
{
  "url": "/api/books/",
  "total_queries": 53,
  "total_time_ms": 127.3,
  "prescriptions": [
    {
      "severity": "CRITICAL",
      "analyzer": "nplusone",
      "issue": "N+1 detected: 47 queries for table \"myapp_author\"",
      "location": "myapp/views.py:83",
      "fix": "Add .select_related('author') to your queryset"
    }
  ]
}
```

### Exit Codes for CI

Use `--fail` to make the command exit with a non-zero code if issues are found:

```bash
# Fail CI if any WARNING or CRITICAL is found
python manage.py check_queries --url /api/books/ --severity WARNING --fail
```

Exit codes:

| Code | Meaning |
|------|---------|
| `0` | No issues found at the specified severity level |
| `1` | One or more issues found |
| `2` | Command error (invalid URL, configuration issue) |

---

## `query_budget`

Enforce hard limits on the number of queries an endpoint is allowed to execute.

### Basic Usage

```bash
# Enforce a budget of 10 queries for a URL
python manage.py query_budget --url /api/books/ --max-queries 10

# Enforce budgets across multiple URLs
python manage.py query_budget --url /api/books/ --url /api/authors/ --max-queries 20
```

### CI Integration with `--fail`

```bash
# Fail the build if any URL exceeds its budget
python manage.py query_budget --url /api/books/ --max-queries 10 --fail
```

Output when the budget is exceeded:

```
BUDGET EXCEEDED: /api/books/
  Executed: 53 queries
  Budget:   10 queries
  Over by:  43 queries

Top consumers:
  1. myapp/views.py:83  — 47 queries (N+1 on myapp_author)
  2. myapp/views.py:91  — 6 queries (duplicate)
```

### Budget File

For projects with many endpoints, define budgets in a YAML file:

```yaml title="query_budgets.yml"
/api/books/: 10
/api/authors/: 5
/api/books/{id}/: 8
/dashboard/: 25
```

```bash
python manage.py query_budget --budget-file query_budgets.yml --fail
```

---

## `fix_queries`

Automatically apply suggested fixes to your source code. This command modifies your Python files.

### Dry Run (Default)

By default, `fix_queries` performs a **dry run**. It shows you what changes would be made without modifying any files:

```bash
python manage.py fix_queries --url /api/books/
```

Output:

```diff
--- myapp/views.py (original)
+++ myapp/views.py (fixed)
@@ -83,7 +83,7 @@
     def get_queryset(self):
-        return Book.objects.all()
+        return Book.objects.select_related('author').all()
```

### Apply Fixes

To actually modify your source files, pass `--apply`:

```bash
python manage.py fix_queries --url /api/books/ --apply
```

> **Warning:** Always review the dry-run output before using `--apply`. While django-query-doctor generates correct fixes in most cases, complex querysets with chained calls or dynamic construction may need manual adjustment. Make sure your code is committed to version control before applying fixes.

### Target Specific Fix Types

Only apply certain categories of fixes:

```bash
# Only apply select_related fixes
python manage.py fix_queries --url /api/books/ --fix-type select_related --apply

# Only apply prefetch_related fixes
python manage.py fix_queries --url /api/books/ --fix-type prefetch_related --apply

# Apply both select_related and prefetch_related
python manage.py fix_queries --url /api/books/ --fix-type select_related --fix-type prefetch_related --apply
```

See [Auto-Fix](auto-fix.md) for the full list of supported fix types.

---

## `diagnose_project`

Run a comprehensive health scan across your entire project.

### Basic Usage

```bash
python manage.py diagnose_project
```

This command:

1. Discovers all URL patterns in your project.
2. Makes test requests to each endpoint.
3. Runs all analyzers on the captured queries.
4. Produces a summary report.

### HTML Report

Generate a self-contained HTML report:

```bash
python manage.py diagnose_project --format html --output report.html
```

The HTML report includes:

- Overall project health score.
- Per-endpoint breakdown of issues.
- Top 10 most impactful prescriptions.
- Query count trends (if previous reports exist).

### Per-App Analysis

Scope the scan to specific Django apps:

```bash
# Only scan the "books" and "authors" apps
python manage.py diagnose_project --app books --app authors
```

### JSON Output for CI

```bash
python manage.py diagnose_project --format json --output report.json
```

### Full Example

```bash
# Full project scan with HTML report, limited to WARNING and above
python manage.py diagnose_project \
    --format html \
    --output query-report.html \
    --severity WARNING \
    --fail
```

---

## Common Options

These options are shared across all commands:

| Option | Description |
|---|---|
| `--severity` | Minimum severity to report: `INFO`, `WARNING`, `CRITICAL` |
| `--format` | Output format: `console` (default), `json`, `html` |
| `--output` | Write output to a file instead of stdout |
| `--fail` | Exit with code 1 if issues are found (useful for CI) |
| `--analyzers` | Comma-separated list of analyzers to run (e.g., `nplusone,duplicate`) |
| `--exclude` | Paths to exclude from analysis |

---

## Further Reading

- [CI Integration](ci-integration.md) -- Using management commands in CI pipelines.
- [Auto-Fix](auto-fix.md) -- Details on the auto-fix system.
- [Middleware](middleware.md) -- Alternative: analyze every request automatically.
