# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-03-20

### Added
- **QueryTurbo**: SQL compilation cache that skips redundant `as_sql()`
  calls for recurring query patterns. Caches the compiled SQL template keyed
  by a structural fingerprint (blake2b) of the Django ORM Query tree.
  Thread-safe LRU cache with configurable max size.
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
- **`check_serializers` command**: Dedicated management command for AST-based
  DRF serializer analysis with `--app`, `--file`, `--format`, and `--fail-on`
  flags.
- **`turbo_enabled()` / `turbo_disabled()` context managers**: Thread-local
  overrides for QueryTurbo activation.
- **Post-migrate cache invalidation**: Automatic cache clear on Django
  `post_migrate` signal to prevent stale SQL after schema changes.

### Changed
- Minimum Python version remains 3.10
- All existing v1.x APIs remain backward compatible
- Version bumped to 2.0.0

## [1.0.3] - 2026-03-18

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
- **Duplicate Query Detection** — exact and near-duplicate identification
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
