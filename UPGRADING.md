# Upgrading to django-query-doctor v2.0

## From v1.x to v2.0

### Breaking Changes

**None.** v2.0 is fully backward compatible with v1.x configurations.

All existing settings, analyzers, reporters, and management commands work
exactly as before. v2.0 adds new features that are opt-in.

### New Features (Opt-In)

#### QueryTurbo

Add the `TURBO` section to your `QUERY_DOCTOR` settings:

```python
QUERY_DOCTOR = {
    # Your existing v1.x settings remain unchanged
    'TURBO': {
        'ENABLED': True,
    },
}
```

QueryTurbo is disabled by default. Enable it when you're ready.

**What it does:** Fingerprints each query's structure, caches the compiled
SQL template, and validates that identical structures produce identical SQL.
This enables automatic prepared statement reuse on PostgreSQL (psycopg3)
by ensuring the same SQL string is consistently passed to the database
driver. The cache also detects fingerprint collisions and evicts
mismatched entries.

**What changes at runtime:** A monkey-patch is installed on
`SQLCompiler.execute_sql()` at Django startup (`AppConfig.ready()`). This
is transparent to your application code.

#### Prepared Statement Bridge

When QueryTurbo is enabled, prepared statements are automatically used on
supported backends:

- **PostgreSQL + psycopg3:** protocol-level preparation via `prepare=True`
- **Oracle:** implicit cursor caching (no code changes)
- **MySQL, SQLite, psycopg2:** SQL cache only (no prepare support)

Disable prepared statements while keeping the SQL cache:

```python
QUERY_DOCTOR = {
    'TURBO': {
        'ENABLED': True,
        'PREPARE_ENABLED': False,
    },
}
```

#### Per-File Analysis

No configuration needed. Use the new CLI flags:

```bash
python manage.py check_queries --file=myapp/views.py
python manage.py check_queries --module=myapp.views
python manage.py diagnose_project --file=myapp/views.py
```

Multiple flags can be combined (OR logic):

```bash
python manage.py check_queries --file=views.py --file=serializers.py
```

#### AST SerializerMethodField Analysis

Requires DRF to be installed. Run:

```bash
python manage.py check_serializers
python manage.py check_serializers --app=myapp
python manage.py check_serializers --file=myapp/serializers.py
```

This is a static analyzer — it reads source code with `ast.parse()` and
does not execute serializer methods.

#### Benchmark Dashboard

```bash
python manage.py query_doctor_report
python manage.py query_doctor_report --output=report.html
```

Generates a standalone HTML file with Chart.js graphs showing cache
performance. The report reflects the current process's cache state — it
resets on server restart.

#### GitHub Actions CI Integration

The new `ci.github` module provides helpers for CI/CD:

```python
from query_doctor.ci.github import format_github_annotations, generate_pr_comment, write_json_report
```

See `examples/github-actions/query-doctor.yml` for a complete workflow.

#### Baseline Snapshots

Save current issues and detect regressions on subsequent runs:

```bash
# Save baseline
python manage.py check_queries --save-baseline=.query-baseline.json

# Compare against baseline on CI
python manage.py check_queries --baseline=.query-baseline.json --fail-on-regression
```

Also available on `diagnose_project`.

#### Smart Prescription Grouping

Group related issues for cleaner output:

```bash
python manage.py check_queries --group=file_analyzer
python manage.py check_queries --group=root_cause
python manage.py diagnose_project --group=view
```

#### Async-Safe Context Managers

`turbo_enabled()` and `turbo_disabled()` now use `contextvars.ContextVar`
instead of `threading.local()`. This makes them safe for ASGI deployments
where multiple coroutines share the same thread. No code changes needed —
the API is identical.

### New Dependencies

- No new required dependencies
- psycopg3 (optional): enables prepared statements on PostgreSQL
- DRF (optional): enables SerializerMethodField AST analysis

### New Management Commands

| Command | Description |
|---|---|
| `check_serializers` | AST analysis of DRF serializer methods |
| `query_doctor_report` | Generate benchmark dashboard HTML |

### New Configuration Keys

```python
QUERY_DOCTOR = {
    'TURBO': {
        'ENABLED': False,              # Default: disabled
        'MAX_SIZE': 1024,              # Max cached patterns
        'SKIP_RAW_SQL': True,          # Skip queries with RawSQL
        'SKIP_EXTRA': True,            # Skip queries with .extra()
        'SKIP_SUBQUERIES': True,       # Skip subqueries
        'PREPARE_ENABLED': True,       # Prepared statements
        'PREPARE_THRESHOLD': 5,        # Hits before preparing
        'VALIDATION_THRESHOLD': 3,     # Validations before trusting (skip as_sql)
    },
}
```

### Django Internal API Notice

QueryTurbo works by monkey-patching `SQLCompiler.execute_sql()`, which is a
Django internal API. While this has been stable across Django 4.2–6.0, internal
APIs may change between major Django releases without deprecation warnings.

**What this means for you:**
- QueryTurbo is tested against Django 4.2, 5.0, 5.1, 5.2, and 6.0.
- If a future Django release changes `SQLCompiler.execute_sql()`, QueryTurbo
  will detect this at startup and gracefully degrade (diagnosis features
  continue working; only the SQL caching patch is affected).
- Always test QueryTurbo with a new Django version before deploying to
  production.
- If you encounter issues, disable QueryTurbo (`'TURBO': {'ENABLED': False}`)
  and report the issue on GitHub.

### Migration Steps

1. `pip install --upgrade django-query-doctor`
2. Verify existing tests pass (nothing should break)
3. Optionally enable QueryTurbo in settings
4. Run `check_serializers` to find hidden serializer N+1s
5. Run `query_doctor_report` to generate a performance baseline
