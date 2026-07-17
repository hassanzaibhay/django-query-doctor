# Upgrading django-query-doctor

## From 2.1.0 to 2.1.1

### Breaking / behavior changes

**1. The `query_doctor` pytest fixture now warns at use.** Requesting the
fixture emits a `QueryDoctorWarning` (new public warning category, importable
from `query_doctor`) stating that the returned report is empty until test
teardown, so assertions on it inside the test body pass vacuously. Anyone
requesting the fixture sees the warning; suites that escalate warnings to
errors (`-W error`, or `filterwarnings = error` in pytest configuration) go
from green to red on every test that requests it. Either move in-test
assertions to the `diagnose_queries()` context manager, whose report is
populated when the `with` block exits:

```python
from query_doctor.context_managers import diagnose_queries


def test_book_list_is_optimized():
    with diagnose_queries() as report:
        list(Book.objects.select_related("author").all())
    assert report.issues == 0
```

or suppress the category:

```ini
[pytest]
filterwarnings =
    error
    ignore::query_doctor.QueryDoctorWarning
```

## From 2.0.x to 2.1.0

### Breaking / behavior changes

**1. Regenerate your baselines.** `nplusone`, `duplicate`, and
`missing_index` now honor `ANALYZERS.<name>.enabled`, and every dispatch
path (middleware, pytest plugin, Celery integration, context manager,
`check_queries`/`diagnose_project`) runs the full set of discovered
analyzers instead of a hardcoded subset. The widened coverage means a
baseline saved on 2.0.x reports newly-covered findings as regressions:

```bash
python manage.py check_queries --save-baseline=.query-baseline.json
```

Baselines now also record the query-doctor version; comparing against a
baseline from a different version prints a non-blocking warning.

**2. `fat_select` threshold key renamed.** 2.0.x read
`ANALYZERS.fat_select.field_count_threshold`; 2.1.0 reads
`ANALYZERS.fat_select.threshold`. The old key is silently ignored — rename
it in your settings:

```python
QUERY_DOCTOR = {
    "ANALYZERS": {
        "fat_select": {"threshold": 8},  # was: "field_count_threshold": 8
    },
}
```

**3. `fix_queries --issue-type` now validates its values.** Previously any
string was accepted and a typo silently produced zero fixes. Now the flag
rejects anything outside `n_plus_one`, `duplicate_query`, `fat_select`,
`queryset_eval`, `missing_index`. Scripts passing analyzer names instead of
issue-type values (e.g. `duplicate` or `nplusone`) will fail fast — update
them to the enum values.

**4. `DRFSerializerAnalyzer` removed.** The runtime DRF analyzer (which
always returned no results) was deleted; importing
`query_doctor.analyzers.drf_serializer` now raises `ImportError`. DRF
serializer N+1 detection is covered by the static `SerializerMethodAnalyzer`
(`python manage.py check_serializers`), whose findings now carry
`IssueType.SERIALIZER_METHOD_FIELD`. `IssueType.DRF_SERIALIZER` remains in
the enum for plugin/fixer compatibility. If your settings contain an
`ANALYZERS["drf_serializer"]` entry, replace it with `"serializer_method"`.

### If you ran `fix_queries --apply` on 2.0.0

2.0.0 was the only published release for ~4 months and its `--apply` carried
two source-mutating defects. Neither fix reached PyPI before 2.1.0 (2.0.1 was
never uploaded). Dry runs were harmless - damage requires an explicit
`--apply`. Both defects are detectable in your committed source.

#### Defect 1 - appended calls on the wrong line (fixed in unpublished 2.0.1)

**Symptom.** 2.0.0 appended `.select_related('X')` / `.prefetch_related('X')`
(N+1 fixes), or `.defer('<field>')` (fat-SELECT fixes on models with large
fields), to the END of the flagged line. The flagged line is frequently the
in-loop attribute-access or queryset-evaluation line rather than the queryset
definition. The canonical damage shape is a single-level relation access in a
loop:

```python
_ = book.author.select_related('author')   # was: _ = book.author
```

which crashes at runtime (model instances have no `.select_related`). Deeper
chains (`_ = book.author.name.select_related('author')`) crash the same way;
appends onto loop headers produce a SyntaxError; appends onto lines with a
trailing comment are swallowed into the comment (a silent no-op). For
fat-SELECT fixes on models without large fields, 2.0.0 appended the literal
placeholder `.only('field1', 'field2', ...)` - that placeholder is the only
`.only(` shape 2.0.0 could write, so the exact search below is exhaustive for
`.only` damage.

**Trigger.** `python manage.py fix_queries --apply` on 2.0.0, where the run
produced `n_plus_one` or `fat_select` fixes. 2.0.0 had no safety allowlist
and no syntax validation; 2.0.1+ refuses to write these fix types.

**Detection.** The authoritative check: if you still have the `.bak` files
2.0.0 wrote next to each modified file (created by default unless
`--no-backup`), run `diff file.py.bak file.py` to see exactly what `--apply`
changed. Otherwise review history around the run (this regex pickaxe covers
all four call names the fixer could append):

```bash
git log -p -G"\.(select_related|prefetch_related|defer|only)\(" -- "*.py"
```

Exact signature of the fat-SELECT placeholder bug (any hit is damage):

```bash
grep -rnF ".only('field1', 'field2', ...)" --include="*.py" .
```

Review-aid search - hits are candidates, not proof; legitimate chained
querysets also match, but every appended-call damage shape ends the line
this way:

```bash
grep -rnE "\.(select_related|prefetch_related|defer|only)\('[^)]*'\)[[:space:]]*$" --include="*.py" .
```

The syntactically-broken subset (loop-header appends) is caught by:

```bash
python -m compileall -q your_app/
```

**Remediation.** There is no programmatic repair - revert damaged hunks from
git history (or the `.bak` files), then re-run `fix_queries` on 2.1.0, where
these fix types are shown as `[MANUAL FIX ONLY]` and never written.

#### Defect 2 - em dash written into your source (fixed in 2.1.0)

**Symptom.** Missing-index fixes inserted a comment line containing a
non-ASCII em dash (U+2014):

```python
# TODO: Consider adding an index via Meta.indexes — Add db_index=True to the 'published_date' field
```

Harmless to Python, but breaks ASCII-only linters/CI and pre-commit hooks
that reject non-ASCII source.

**Trigger.** `python manage.py fix_queries --apply` on 2.0.0 where the run
produced `missing_index` fixes.

**Detection.** Search for the em dash byte sequence itself (hits mean damage
even after upgrading - 2.1.0 writes this comment in pure ASCII, which does
not match):

```bash
git grep -n $'\xe2\x80\x94' -- '*.py'
```

With GNU grep (Linux; the `-P` flag is not available in macOS/BSD grep), you
can also scan for any non-ASCII byte:

```bash
grep -rnP "[^\x00-\x7F]" --include="*.py" .
```

**Remediation.** Replace the em dash with `-` (or delete the comment).

---

2.1.0's `--apply` writes only allowlisted issue types (`queryset_eval`,
`duplicate_query`, `missing_index`), tags the rest `[MANUAL FIX ONLY]`,
validates candidate files with `ast.parse()` before writing, and exits
nonzero when fixes are skipped or rejected.

---

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
