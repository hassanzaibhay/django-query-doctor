# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/).

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

## [1.0.1] - 2026-03-15

### Patch (1.0.1)
- Added SVG terminal renders to README for visual feature showcase
- Added Django 6.0 mention in README requirements
- Cleaned up committed __pycache__ artifacts
- Updated .gitignore with additional exclusions
