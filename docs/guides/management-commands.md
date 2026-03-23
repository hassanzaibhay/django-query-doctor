# Management Commands

django-query-doctor ships six management commands for on-demand analysis, budget enforcement, auto-fixing, static serializer analysis, project health scans, and benchmark reporting. These commands work independently of the middleware and are ideal for CI/CD pipelines and one-off investigations.

---

## `check_queries`

Analyze queries for a URL and report optimization issues.

### Basic Usage

```bash
# Analyze a single URL
python manage.py check_queries --url /api/books/

# JSON output
python manage.py check_queries --format json

# Write output to a file
python manage.py check_queries --output report.json --format json
```

### All Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--url` | `str` | `/` | URL path to analyze |
| `--format` | `str` | `console` | Output format: `console` or `json` |
| `--fail-on` | `str` | — | Exit with code 1 if issues at this severity or higher are found: `critical`, `warning`, or `info` |
| `--diff` | `str` | — | Only report issues in files changed vs this git ref (e.g., `main`, `origin/develop`, `abc123`) |
| `--file` | `str` | — | Only report issues in files matching this substring. Can be specified multiple times. |
| `--module` | `str` | — | Only report issues in modules matching this substring. Can be specified multiple times. |
| `--output`, `-o` | `str` | — | Write output to a file instead of stdout |
| `--save-baseline` | `str` | — | Save current issues as a baseline snapshot (JSON file) |
| `--baseline` | `str` | — | Compare against a baseline snapshot, show only regressions |
| `--fail-on-regression` | flag | — | Exit with code 1 if new issues found vs baseline |
| `--group` | `str` | `file_analyzer` | Group related prescriptions. Strategies: `file_analyzer`, `root_cause`, `view` |

### Examples

```bash
# Filter to a specific file
python manage.py check_queries --file myapp/views.py

# Only report issues in changed files vs main
python manage.py check_queries --diff main

# Baseline regression workflow
python manage.py check_queries --save-baseline=.query-baseline.json
python manage.py check_queries --baseline=.query-baseline.json --fail-on-regression

# Group prescriptions by root cause
python manage.py check_queries --group root_cause
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No issues found (or no regressions when using `--baseline`) |
| `1` | Issues found at the specified `--fail-on` severity, or regressions detected |

---

## `check_serializers` *(v2.0)*

Statically analyze DRF serializer `SerializerMethodField` methods for N+1 patterns using AST inspection. Does not execute any code.

### Basic Usage

```bash
# Scan all installed apps
python manage.py check_serializers

# Scan specific apps
python manage.py check_serializers --app=myapp --app=otherapp
```

### All Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--app` | `str` | — | Only scan serializers in the given app. Can be repeated. |
| `--module` | `str` | — | Only scan the given module path. Can be repeated. |
| `--file` | `str` | — | Only report issues in files matching this substring. Can be repeated. |
| `--format` | `str` | `console` | Output format: `console` or `json` |
| `--fail-on` | `str` | — | Exit with code 1 if issues at this severity or higher: `critical`, `warning`, `info` |
| `--output`, `-o` | `str` | — | Write output to a file instead of stdout |

### Examples

```bash
# Scan specific module
python manage.py check_serializers --module=myapp.serializers

# JSON output for CI
python manage.py check_serializers --format=json --fail-on=warning

# Filter by file
python manage.py check_serializers --file=myapp/serializers.py
```

!!! note "Requires DRF"
    This command requires `djangorestframework` to be installed. If DRF is not present, the command reports no issues.

---

## `query_budget`

Enforce hard limits on the number of queries a code block executes.

### All Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--max-queries` | `int` | **required** | Maximum number of queries allowed |
| `--max-time-ms` | `float` | — | Maximum total query time in milliseconds |
| `--execute` | `str` | — | Python code to execute and measure |

### Examples

```bash
# Enforce a query budget on a code block
python manage.py query_budget --max-queries 10 --execute "list(Book.objects.all())"

# With time budget
python manage.py query_budget --max-queries 10 --max-time-ms 100 --execute "list(Book.objects.all())"
```

!!! warning "Security"
    `--execute` uses `exec()` internally. Only run trusted code.

---

## `fix_queries`

Automatically apply suggested fixes to your source code.

### All Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--dry-run` | flag | **default** | Show diff without applying changes |
| `--apply` | flag | — | Apply fixes to source files |
| `--issue-type` | `str` | — | Only fix specific issue types (e.g., `n_plus_one`, `duplicate`). Can be repeated. |
| `--file` | `str` | — | Only fix specific files. Can be repeated. |
| `--no-backup` | flag | — | Do not create `.bak` files when applying |
| `--url` | `str` | `/` | URL path to analyze |

### Examples

```bash
# Dry run (default) — see what would change
python manage.py fix_queries

# Apply fixes
python manage.py fix_queries --apply

# Only fix N+1 issues
python manage.py fix_queries --issue-type n_plus_one --apply

# Only fix specific files
python manage.py fix_queries --file myapp/views.py --apply
```

!!! warning
    Always review the dry-run output before using `--apply`. Make sure your code is committed to version control before applying fixes.

---

## `diagnose_project`

Run a comprehensive health scan across your entire project by discovering URL patterns and analyzing each endpoint.

### All Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output`, `-o` | `str` | `query_doctor_report.html` | Output file path |
| `--format` | `str` | `html` | Report format: `html` or `json` |
| `--apps` | `str` | — | Only diagnose specific apps (space-separated) |
| `--timeout` | `int` | `30` | Timeout per URL in seconds |
| `--exclude-urls` | `str` | — | URL prefixes to exclude (space-separated) |
| `--methods` | `str` | `GET` | HTTP methods to test (space-separated) |
| `--file` | `str` | — | Only report issues in files matching this substring. Can be repeated. |
| `--module` | `str` | — | Only report issues in modules matching this substring. Can be repeated. |
| `--save-baseline` | `str` | — | Save current issues as a baseline snapshot (JSON file) |
| `--baseline` | `str` | — | Compare against a baseline snapshot, show only regressions |
| `--fail-on-regression` | flag | — | Exit with code 1 if new issues found vs baseline |
| `--group` | `str` | `file_analyzer` | Group related prescriptions. Strategies: `file_analyzer`, `root_cause`, `view` |

### Examples

```bash
# Full project scan with HTML report
python manage.py diagnose_project

# JSON output for CI
python manage.py diagnose_project --format json --output report.json

# Only scan specific apps
python manage.py diagnose_project --apps myapp otherapp

# Exclude admin URLs
python manage.py diagnose_project --exclude-urls /admin/

# With baseline regression detection
python manage.py diagnose_project --baseline=.query-baseline.json --fail-on-regression

# Group by view endpoint
python manage.py diagnose_project --group view
```

---

## `query_doctor_report` *(v2.0)*

Generate a QueryTurbo benchmark dashboard as a self-contained HTML file.

### All Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output`, `-o` | `str` | `query_doctor_report.html` | Output file path |

### Examples

```bash
python manage.py query_doctor_report
python manage.py query_doctor_report --output=reports/turbo-dashboard.html
```

The dashboard shows cache hit rates, top optimized queries, and Chart.js graphs. Data reflects the current process cache — the cache resets on server restart. See [Benchmark Dashboard](benchmark-dashboard.md) for details on what the report contains.

!!! warning "Schema Information"
    The report contains SQL query templates (without parameter values) that may reveal database schema information. Do not share the report publicly if your schema is confidential.

---

## Further Reading

- [CI/CD Integration](ci-integration.md) — Using management commands in CI pipelines
- [Auto-Fix Mode](auto-fix.md) — Details on the auto-fix system
- [Baseline Regression](baseline.md) — Baseline regression detection guide
- [Prescription Grouping](grouping.md) — How grouping works
- [Benchmark Dashboard](benchmark-dashboard.md) — Interactive HTML report
- [Middleware](middleware.md) — Alternative: analyze every request automatically
