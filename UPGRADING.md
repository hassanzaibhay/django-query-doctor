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

**What it does:** Caches the SQL compilation output for recurring query
patterns. When your ORM generates the same SQL template with different
parameters, the cached template is reused — skipping the full `as_sql()`
tree traversal.

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
