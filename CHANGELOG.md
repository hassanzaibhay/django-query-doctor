# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- A claims gate (`scripts/claims_check.py` + `claims.json`) that regenerates
  every quantitative claim this project publishes — analyzer count, test count,
  coverage, supported Django and Python ranges, open follow-up count — from the
  tree and fails on drift. Surfaces in this repository are read on every run;
  surfaces published elsewhere are fetched over HTTP on every run; in both cases
  a recorded locator must appear verbatim, so a reworded claim fails loudly
  rather than leaving its row checking nothing. A surface that can be neither
  fetched nor corrected from a commit must say so in `unverifiable_reason` and
  is reported on every run, including clean ones, because such a row proves the
  manifest is self-consistent and proves nothing about the surface.
  The gate also rejects two shapes of claim outright: build durations quoted as
  facts, and dated assertions about something's *current* status, which rot
  without an edit. Dated *provenance* ("comparisons current as of ...") is
  exempt, because recording when a comparison was made stays true permanently.
  A row whose surface currently disagrees and cannot be corrected from here can
  be marked deferred; a deferral must carry a reason and a named action, is
  printed on every run, and fails the gate once the surface agrees again.
- The docs truth sweep and the claims gate now run in CI and as pre-push hooks.
  Neither was wired into anything before; both had to be remembered.

### Changed
- Settings that were accepted and then ignored now take effect.
  `STACK_TRACE_EXCLUDE` reaches the callsite finder, `QUERYIGNORE_PATH`
  selects the `.queryignore` file to load, and `ADMIN_DASHBOARD.max_reports`
  sizes the dashboard buffer. All three were present in the defaults,
  documented as having no effect, and read by nothing.
- An unrecognized `REPORTERS` entry now warns instead of silently producing no
  reporter. A typo and an unsupported name were previously indistinguishable
  from a working configuration. Suites running `-W error` will fail on such an
  entry — see `UPGRADING.md`.
- A `QUERYIGNORE_PATH` that cannot be resolved warns and falls back to
  discovery beside `manage.py`, rather than being dropped silently.

- The distribution metadata and the runtime `__version__` can no longer
  disagree. The version was previously declared independently in
  `pyproject.toml` and `src/query_doctor/__init__.py`, with a third copy pinned
  in a test, and nothing derived any one from the others; the module is now the
  single source and the suite fails if the installed distribution reports
  anything else. Note for contributors: bumping the version requires
  `pip install -e "."` before the suite passes, because distribution metadata is
  snapshotted at install time.
- The claims gate now reads published surfaces instead of trusting its own
  manifest about them. As first shipped it compared only the recorded value
  against the tree for anything outside this repository, so 7 of its 13 rows
  were never read at all and a drifted profile page could not be detected by
  any code path — the entry above is worded to describe what the gate does
  after this change, not what it did when the row was written. Five rows now
  fetch the surface (`Cache-Control: no-cache`, since the host is CDN-served
  and a stale read is a false green); a fetch failure is a violation, never a
  skip.
- A failed `pytest --collect-only` no longer yields a test count. The exit code
  was previously unchecked, and the count regex reads the denominator of
  `N/M tests collected`, so a broken collection produced an inflated number
  rather than an error.
- CI and the pre-push hooks now invoke the gate scripts identically
  (`python -m scripts.x`). The paths already matched; the invocation form did
  not, and the two forms put different directories on `sys.path[0]`.
- `Upload coverage` in CI sets `fail_ci_if_error: true`. It previously reported
  success on a run whose upload was refused outright.
- `scripts/` is now linted and type-checked. `ruff` and `mypy` covered
  `src/` and `tests/` only, in both the hooks and CI, while `scripts/` holds the
  docs truth sweep, the claims gate and the hook launcher that every other check
  runs through.
- Pre-push hooks no longer resolve `ruff`, `mypy` and `pytest` from `PATH`.
  Every entry now runs through `scripts/hookenv.py`, which resolves this
  repository's virtualenv explicitly (both the `Scripts/` and `bin/` layouts),
  fails loudly when a tool is not importable in that interpreter instead of
  falling back, and prints which interpreter it used so each run states its own
  provenance. Contributor-facing only; no runtime behaviour changes. Verified
  from a shell with no venv on `PATH`: previously `Executable ruff not found`,
  `Executable mypy not found`, and a `pytest` hook exiting 1 with no output
  from an unrelated system interpreter; now all four pass under the repository
  venv.

### Removed
- `IGNORE_PATTERNS` from the default configuration. No code path ever read it;
  `.queryignore` is the supported way to suppress findings. Leaving the key in
  your settings is harmless — unknown keys are merged and ignored.

### Fixed
- `docs/deep-dive/comparison.md` no longer asserts that Django's fetch modes are
  "unreleased as of 2026-07-14". That parenthetical would have become false when
  Django 6.1 reaches final release, with no code change and nobody touching the
  file; the linked release notes now carry the status instead. The dated
  disclaimers at `comparison.md:5` and `faq.md:131` are deliberately unchanged —
  those record when a comparison was made and stay true permanently.

## [2.1.2] - 2026-07-22

### Changed
- **`QueryDoctorMiddleware.async_capable` is now `False`** (was `True`). This is
  the fix for the two ASGI defects below, not a withdrawal of ASGI support —
  ASGI capture works for the first time in this release. Django adapts
  sync-only middleware with `sync_to_async(thread_sensitive=True)`, which runs
  it in the same thread-sensitive executor Django runs ORM work in; because
  database connections are thread-local, that co-location is what lets the
  interceptor see the queries. Request concurrency is unaffected: Django opens
  a thread-sensitive context per request, so requests do not serialise.
  One consequence worth knowing: Django assigns middleware modes from the
  inside out (`django/core/handlers/base.py`, `load_middleware`), so every
  middleware listed *before* `QueryDoctorMiddleware` in `MIDDLEWARE` now runs
  in sync mode as well. With the recommended last position, that is the whole
  chain. This is standard Django behaviour for any sync-only middleware — a
  great deal of third-party middleware is sync-only — and it does not affect
  request concurrency, but async-capable middleware in your stack will run
  synchronously while query-doctor is installed. Note this is not a change
  relative to 2.1.1: the missing coroutine marker described below already
  forced those middleware into sync mode, while also breaking them.
  `async_capable` is a public class attribute — if you subclass
  `QueryDoctorMiddleware` and re-declare it as `True`, remove that override.
  The `async_capable = False` subclass workaround circulating in issue #11
  becomes redundant but stays harmless.

### Fixed
- **ASGI requests failed with `TypeError: object HttpResponse can't be used in
  'await' expression`** (`HttpResponseServerError` when `DEBUG = False`), raised
  at `django/core/handlers/base.py` in `get_response_async`. The middleware
  declared `async_capable = True` without marking its instance as a coroutine
  function, so Django recorded the handler as async while
  `convert_exception_to_response` wrapped it synchronously. Every middleware
  listed before it then degraded to sync mode and was handed an un-awaited
  coroutine. Three of Django's seven `startproject` defaults —
  `SecurityMiddleware`, `CommonMiddleware`, `XFrameOptionsMiddleware` — touch
  the response object unconditionally and raised on it, so any stack built from
  those defaults with query-doctor anywhere but first position failed on every
  request. Reported in #11 under Daphne + Channels. (`SessionMiddleware`,
  `CsrfViewMiddleware`, and `AuthenticationMiddleware` pass the object through
  untouched on an ordinary GET, so some stacks returned 200 — and hit the next
  defect instead.)
- **No queries were captured under ASGI at all**, in any middleware
  configuration that did not crash, in every release that shipped the
  middleware. The middleware ran on the event loop thread while Django ran all
  ORM work — from `async def` views and sync views alike — in a thread-sensitive
  executor thread. Database connections are thread-local, so the
  `execute_wrapper` was installed on a connection object the queries never
  touched, and every ASGI report was silently empty. A 200 response was not
  evidence the tool had run.
- **Docs:** `docs/guides/async-support.md` recommended `with diagnose_queries():`
  inside `async def` views as an alternative to the middleware. Measured under a
  real ASGI handler, that block reports zero queries — same thread-locality
  cause as the middleware defect, applied to the context manager. The
  recommendation has been removed and the limitation documented. No code change;
  the fix is tracked in `FOLLOWUPS.md` entry 22.
- The async predicate now comes from `asgiref.sync` rather than `inspect`, which
  is the predicate Django itself uses. `inspect.iscoroutinefunction` does not
  recognise asgiref-wrapped callables before Python 3.12
  (`inspect.markcoroutinefunction` arrived in 3.12), so on Python 3.10 and 3.11
  a `QueryDoctorMiddleware` constructed directly around a `sync_to_async`
  handler took the sync path and ran its analysis stage *before* the view body,
  producing an always-empty report. Not reachable through Django's middleware
  chain — `load_middleware` never hands a `sync_capable` middleware an
  asgiref-wrapped handler — so this affected direct instantiation only.

## [2.1.1] - 2026-07-17

### Added
- `QueryDoctorWarning` (subclass of `UserWarning`), exported from
  `query_doctor` — the package's warning category for runtime advisories,
  filterable by category (`ignore::query_doctor.QueryDoctorWarning`)
  without touching other `UserWarning`s.

### Changed
- The `query_doctor` pytest fixture now emits a `QueryDoctorWarning` when
  requested: its `DiagnosisReport` is populated only during test teardown,
  so assertions on it inside the test body pass vacuously. Use the
  `diagnose_queries()` context manager for in-test assertions. Suites
  running `-W error` (or `filterwarnings = error`) will start failing on
  fixture use — that is the intended signal; suppress just this category
  with `ignore::query_doctor.QueryDoctorWarning`.

### Fixed
- The CI integration guide prescribed in-test assertions on the
  `query_doctor` fixture object and claimed they gate CI — those
  assertions pass vacuously (see the fixture warning above; users who
  copied that sample are exactly who the warning fires on). The sample was
  removed in favour of the pytest guide's `diagnose_queries()` patterns,
  which do fail the test when violated.

## [2.1.0] - 2026-07-16

> **PyPI note:** 2.1.0 is the first release published to PyPI since 2.0.0.
> The `[2.0.1]` and `[1.0.3]` entries below describe versions that were
> merged and tagged in this repository but never uploaded to PyPI (PyPI has
> only 1.0.0, 1.0.1, 1.0.2, and 2.0.0). If you are upgrading from 2.0.0,
> this release is therefore your first with the 2.0.1 `fix_queries --apply`
> corruption fix. If you ever ran `--apply` on 2.0.0, follow the damage
> detection steps in `UPGRADING.md` ("If you ran fix_queries --apply on
> 2.0.0") before trusting that source.

### Upgrading to 2.1.0

`nplusone`, `duplicate`, and `missing_index` now respect their
`ANALYZERS.<name>.enabled` config setting, and every dispatch path
(middleware, pytest plugin, Celery integration, context manager,
`check_queries`/`diagnose_project`) now runs the full set of discovered
analyzers instead of a hardcoded subset. If you use `check_queries
--baseline`, **regenerate your baseline** after upgrading — the widened
analyzer coverage means an old baseline will report newly-covered findings as
regressions until it's refreshed. Comparing against a baseline saved with a
different query-doctor version now prints a non-blocking warning rather than
failing the check. See `UPGRADING.md` for the full 2.1.0 upgrade checklist.

### Added
- `IssueType.SERIALIZER_METHOD_FIELD` — findings from `SerializerMethodAnalyzer`
  (the `check_serializers` static analyzer) now carry their own issue type
  instead of sharing `IssueType.DRF_SERIALIZER` with the deleted runtime
  analyzer. `DRF_SERIALIZER` remains in the enum for plugin/fixer compatibility.

### Fixed
- `nplusone`, `duplicate`, and `missing_index` analyzers now respect their
  `ANALYZERS.<name>.enabled` config setting. Previously, disabling these
  three analyzers had no effect outside `fix_queries` — they still ran and
  reported issues through the middleware, pytest plugin, Celery integration,
  context manager, and `check_queries`/`diagnose_project` commands.
- Middleware, context manager, `check_queries`, Celery integration, and the
  pytest plugin now dispatch through `discover_analyzers()` instead of five
  separate hardcoded, inconsistent analyzer lists (3-5 of the built-ins each).
  Every analyzer's own `is_enabled()` gate (above) is what keeps config
  toggles honored now that dispatch is no longer hand-filtered per site.
- `serializer_method` now has a `DEFAULT_CONFIG` entry, so
  `ANALYZERS.serializer_method.enabled = False` actually disables it.
  Previously there was no config key to set, so the analyzer always ran.
- `fat_select`'s column-count threshold config key was **renamed** from
  `ANALYZERS.fat_select.field_count_threshold` (the key 2.0.x read) to
  `ANALYZERS.fat_select.threshold`, matching the other analyzers. The old
  key is now **silently ignored** — if you set `field_count_threshold` in
  your settings, rename it to `threshold` when upgrading.
- `fix_queries --issue-type` now validates against the five fixer-backed
  issue types instead of silently accepting any string and producing zero
  fixes on a typo.
- `check_queries --baseline` now tracks the query-doctor version the baseline
  was saved with (previously hardcoded to a stale `"2.0.0"` literal) and
  prints a non-blocking warning — not a failure — when comparing against a
  baseline saved with a different version.

### Removed
- Removed `DRFSerializerAnalyzer`, a builtin analyzer that always returned no
  results through any code path reachable from `fix_queries`, the middleware,
  or any management command. DRF serializer N+1 detection is unaffected —
  it's covered by the static `SerializerMethodAnalyzer` (`check_serializers`
  command), which is unchanged aside from its issue type (see Added). The
  built-in analyzer count is now 7.

## [2.0.1] - 2026-07-13

> **Never published to PyPI.** This version was merged and tagged in the
> repository but not uploaded; PyPI's latest remained 2.0.0. Its changes —
> including the `fix_queries --apply` corruption fix below — first reach
> PyPI in 2.1.0. To check whether a 2.0.0 `--apply` run already damaged
> your source, see `UPGRADING.md`.

### Added
- `.github/pull_request_template.md` — PR template (summary, type, changelog
  entry, testing, checklist).

### Changed
- `CONTRIBUTING.md` codifies the PR workflow: all changes via `feat/*` or
  `fix/*` branch → PR → review → squash-merge to `main`. No direct pushes
  to `main`.
- `CHANGELOG.md` adopts [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
  format with an `[Unreleased]` section at the top. Every PR adds its entry
  here; on release, `[Unreleased]` is promoted to the version heading.
- `.github/pull_request_template.md`: replaced the changelog-entry example
  (previously tied to this very fix, before it shipped) with a generic
  placeholder; split `breaking` out of the mutually-exclusive `## Type` list
  into its own `Breaking change?` question; dropped the redundant
  no-direct-to-main checkbox now that the branch ruleset enforces it.
- `docs/getting-started/configuration.md`: full rewrite. The previous
  example used dotted class paths for `ANALYZERS` and dotted-path
  `REPORTERS`, neither of which the code accepts; documented fictional keys
  (`MIN_SEVERITY`, `QUERY_DOCTOR_ENABLED`, `EXCLUDE_PATHS`,
  `JSON_OUTPUT_DIR`/`HTML_OUTPUT_DIR`); and implied `HTMLReporter` works via
  `REPORTERS`, which it doesn't. Rewritten against the real
  `DEFAULT_CONFIG` and each key's call site, including three keys
  (`STACK_TRACE_EXCLUDE`, `IGNORE_PATTERNS`, `QUERYIGNORE_PATH`) that exist
  in defaults but aren't read by any code path yet.
- `docs/guides/auto-fix.md`: updated to describe the new safe/unsafe split
  and the `ast.parse()` validation floor.

### Fixed
- **`fix_queries --apply` could write broken code into your source files.**
  The fixer edits the query's *callsite* line, but for `n_plus_one` and
  `fat_select` prescriptions that's frequently the in-loop attribute-access
  line, not the queryset definition — appending `.select_related(...)` or
  `.only(...)` there produced invalid or silently-wrong Python. This shipped
  in 2.0.0. **If you ran `fix_queries --apply` on 2.0.0, check your diffs
  (`git diff` or the `.bak` files it created) for corrupted lines before
  trusting them.**

  As of 2.0.1, `--apply` only writes fixes for issue types verified safe
  (`queryset_eval`, `duplicate_query`, `missing_index`) via a fixed
  allowlist (`fixer.AUTO_APPLIABLE_ISSUE_TYPES`). `n_plus_one`, `fat_select`,
  and `drf_serializer` are shown in the diff tagged `[MANUAL FIX ONLY]` and
  refused at write time — apply those by hand. Before writing anything, the
  candidate file content is also validated with `ast.parse()`; a fix that
  would produce syntactically invalid Python is rejected instead of written
  (this catches syntax errors only, not semantic correctness). `fix_queries
  --apply` now exits nonzero if any fixes were skipped as unsafe or failed
  validation, even when other fixes in the same run succeeded.

  Post-patch, `--apply` performs exactly one real code transform
  (`queryset_eval`) plus two `# TODO`-comment insertions (`duplicate_query`,
  `missing_index`). `n_plus_one` and `fat_select` are dry-run only.
  `drf_serializer` is never emitted by the runtime pipeline `fix_queries`
  uses, so it never reaches the fixer at all.

## [2.0.0] - 2026-03-21

### Added
- **QueryTurbo**: SQL compilation cache with three-phase trust lifecycle
  (UNTRUSTED → TRUSTED → POISONED). On cache miss, compiles and caches.
  On untrusted hit, validates cached SQL against fresh `as_sql()` output
  and promotes to TRUSTED after `VALIDATION_THRESHOLD` (default 3)
  successful validations. On trusted hit, skips `as_sql()` entirely and
  extracts params directly from the Query tree via `turbo/params.py`.
  On mismatch, poisons the entry for the lifetime of the process (persists across cache clears triggered by migrations).
- **True SQL Compilation Skipping**: `turbo/params.py` extracts params
  from the Django Query tree without calling `as_sql()`. Uses
  `lookup.as_sql(compiler, connection)` per WHERE node for exact param
  transformations (handles `__contains` wrapping, `__isnull` discarding,
  etc.) at a fraction of the cost of full SQL compilation.
- **Prepared Statement Bridge**: Multi-database prepared statement support.
  Automatic protocol-level preparation on PostgreSQL + psycopg3 after a
  configurable hit-count threshold. Oracle implicit cursor caching. Graceful
  fallback (TypeError → permanent disable) on unsupported backends.
- **AST SerializerMethodField Analyzer**: Static analysis of DRF `get_<field>`
  methods using `ast.parse()` to detect hidden N+1 queries at serialization
  time. Detects four patterns: related manager access, Model.objects calls,
  deep attribute chains, and for-loop queryset iteration.
- **Per-File Analysis**: `--file` and `--module` flags on `check_queries`
  and `diagnose_project` commands for focused diagnosis via substring matching.
- **Benchmark Dashboard**: `query_doctor_report` management command generates
  standalone HTML report with Chart.js graphs showing cache hit rates, top
  optimized queries, and prepared statement statistics.
- **GitHub Actions CI Integration**: `ci.github` module with
  `format_github_annotations()` for inline PR diff annotations,
  `generate_pr_comment()` for Markdown PR summaries, and
  `write_json_report()` for CI consumption. Example workflow in
  `examples/github-actions/query-doctor.yml`.
- **Baseline Snapshots**: `baseline.py` with `BaselineSnapshot` class for
  saving/loading issue snapshots. SHA-256 hashing ignores line numbers for
  stable identity across code movement. `--save-baseline`, `--baseline`,
  and `--fail-on-regression` flags on `check_queries` and `diagnose_project`.
- **Smart Prescription Grouping**: `grouping.py` with `group_prescriptions()`
  supporting `file_analyzer`, `root_cause`, and `view` strategies. `--group`
  flag on `check_queries` and `diagnose_project`. Console reporter supports
  grouped output mode.
- **Async-Safe Context Managers**: `turbo_enabled()` / `turbo_disabled()`
  now use `contextvars.ContextVar` instead of `threading.local()`, making
  them safe for ASGI deployments with concurrent coroutines.
- **`check_serializers` command**: Dedicated management command for AST-based
  DRF serializer analysis with `--app`, `--file`, `--format`, and `--fail-on`
  flags.
- **Post-migrate cache invalidation**: Automatic cache clear on Django
  `post_migrate` signal to prevent stale SQL after schema changes.
- **Fingerprint collision detection**: Cache hit path validates SQL matches
  and poisons mismatched entries permanently.
- **`__in` lookup length in fingerprint**: Different `__in` list sizes
  produce different fingerprints, preventing SQL/param count mismatch.
- **`select_for_update` in fingerprint**: Queries with `FOR UPDATE`,
  `NOWAIT`, and `SKIP LOCKED` produce distinct fingerprints.
- **Annotation source field fingerprinting**: Annotations with the same
  name but different field targets produce different fingerprints.

### Changed
- Minimum Python version remains 3.10
- All existing v1.x APIs remain backward compatible
- Version bumped to 2.0.0
- Context managers switched from `threading.local()` to `contextvars.ContextVar`
- Cache entries now track `validated_count`, `trusted`, `poisoned` state
- New config key: `VALIDATION_THRESHOLD` (default 3) controls trust promotion

## [1.0.3] - 2026-03-18

> **Never published to PyPI.** This version exists only in the repository
> history; its changes first shipped to PyPI as part of 2.0.0.

### Fixed
- Missing Index analyzer now recommends `Meta.indexes` with `models.Index()` instead of `db_index=True`, following Django's official recommendation since 4.2 (fixes #1)
- Auto-fix for missing indexes now generates `Meta.indexes` suggestion instead of `db_index=True`
- `_field_is_indexed` now checks `Meta.constraints` for `UniqueConstraint` (modern Django 4.2+ pattern) in addition to `unique_together`

### Changed
- Full audit of all prescription texts across all 7 analyzers to align with Django 4.2–6.0 best practices
- Fat SELECT prescriptions now mention `.values()`/`.values_list()` as alternatives when model instances aren't needed
- N+1 prescriptions for `prefetch_related` now mention `Prefetch()` objects for advanced filtering scenarios
- QuerySet evaluation prescriptions now mention `.iterator()` for large querysets to reduce memory usage
- Updated docs, README, and all affected tests to reflect new recommendation text

## [1.0.2] - 2026-03-16

### Fixed
- Fixed SVG terminal renders not displaying on GitHub (switched to absolute URLs)
- Removed Google Fonts @import from SVGs blocked by GitHub CSP

## [1.0.1] - 2026-03-15

### Changed
- Added SVG terminal renders to README for visual feature showcase
- Added Django 6.0 mention in README requirements
- Cleaned up committed __pycache__ artifacts
- Updated .gitignore with additional exclusions

## [1.0.0] - 2026-03-13

> **Historical note (added during the 2.1.0 remediation):** two features
> listed below never functioned in any release. The runtime "DRF Serializer
> N+1" analyzer returned no results through any reachable code path and was
> removed in 2.1.0 (see the [2.1.0] "Removed" entry; static DRF analysis via
> `check_serializers` replaces it). "Admin dashboard integration showing
> latest project scan results" never activated: `record_project_report` has
> no caller in any released version and the dashboard template does not
> render project-report data. The original entries are preserved unchanged
> below.

### Added

#### Core Pipeline
- Query interception via `connection.execute_wrapper()` — works without `DEBUG=True`
- SQL fingerprinting with normalization and SHA-256 hashing
- Source code mapping with file:line references via stack trace analysis
- Django middleware with zero-config setup (one line in `MIDDLEWARE`)
- `diagnose_queries()` context manager for targeted analysis
- `@diagnose` and `@query_budget` decorators
- Full configuration system via `QUERY_DOCTOR` Django settings

#### Analyzers
- **N+1 Detection** — fingerprint-based grouping with FK pattern matching
- **Duplicate Query Detection** — exact-duplicate identification (same SQL and parameters, hashed and grouped)
- **Missing Index Detection** — WHERE/ORDER BY columns without indexes
- **Fat SELECT Detection** — flags `SELECT *` when fewer columns suffice
- **QuerySet Evaluation** — suggests `.count()`, `.exists()`, `.first()` alternatives
- **DRF Serializer N+1** — detects missing prefetch in DRF views

#### Reporters
- **Console** — Rich terminal output with fallback to plain text
- **JSON** — structured output for CI/CD pipelines
- **Log** — Python logging integration
- **HTML** — standalone dashboard report
- **OpenTelemetry** — span and event export for observability stacks

#### Ecosystem
- Celery task support via `@diagnose_task` decorator
- Async Django/ASGI middleware support
- Custom analyzer plugin API via Python entry points
- Pytest plugin with `query_doctor` fixture
- `check_queries` management command for CI analysis
- `query_budget` management command for budget enforcement

#### Project-Wide Diagnosis
- **diagnose_project** management command — crawls all project URLs and generates app-wise health report
- Standalone HTML report with health scores, sortable app scoreboard, and per-URL prescription detail
- JSON report output for CI integration
- Admin dashboard integration showing latest project scan results

#### Auto-Fix & CI
- **Auto-Fix Mode** — `fix_queries` management command applies diagnosed fixes with dry-run default and .bak backups
- **Diff-Aware CI** — `--diff` flag for `check_queries` to analyze only files changed vs a git ref
- **.queryignore** — project-level file to suppress known false positives by SQL pattern, file, callsite, or issue type

#### Monitoring
- **Admin Dashboard** — staff-only in-memory dashboard showing recent query diagnosis reports
- **Query Complexity Scorer** — regex-based SQL complexity analysis flagging excessive JOINs, subqueries, and OR chains

#### Developer Experience
- Every prescription includes severity, description, file:line, and exact code fix
- Zero required dependencies beyond Django
- Optional extras: Rich, Celery, OpenTelemetry
- Full type annotations with `py.typed` (PEP 561)
- CI matrix: Python 3.10-3.13 x Django 4.2-6.0
