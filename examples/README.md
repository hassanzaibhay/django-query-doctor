# django-query-doctor — Examples

This directory contains runnable examples, pre-generated outputs, and configuration templates for every feature of django-query-doctor.

## Quick Start

```bash
cd examples/sample_project
pip install django-query-doctor djangorestframework
python setup_and_run.py
```

This creates a sample database, runs every feature, and saves output to `outputs/`.

## Directory Guide

| Directory | What's Inside |
|-----------|--------------|
| `sample_project/` | Self-contained Django project demonstrating all issues |
| `scripts/` | One script per feature — read, learn, adapt |
| `outputs/` | Pre-generated output files (HTML, JSON, text) |
| `screenshots/` | Visual samples for documentation |
| `configs/` | Settings templates: minimal, production, CI, full reference |
| `quick_start/` | Copy-paste snippets to get started in 30 seconds |

## Scripts Overview

| # | Script | Feature |
|---|--------|---------|
| 01 | `basic_middleware.py` | Zero-config middleware setup |
| 02 | `context_manager.py` | `diagnose_queries()` for tests and scripts |
| 03 | `decorator.py` | `@diagnose` and `@query_budget` |
| 04 | `pytest_usage.py` | Built-in pytest fixture |
| 05 | `management_commands.sh` | All 4 management commands |
| 06 | `celery_tasks.py` | Background task diagnosis |
| 07 | `async_views.py` | Async Django support |
| 08 | `custom_analyzer.py` | Writing analyzer plugins |
| 09 | `queryignore.py` | Suppressing false positives |
| 10 | `opentelemetry.py` | OTel span export |
| 11 | `auto_fix.sh` | Auto-applying fixes |
| 12 | `project_diagnosis.sh` | Full project health scan |
| 13 | `diff_aware_ci.sh` | PR-only query checking |
| 14 | `admin_dashboard.py` | Admin panel setup |

## Output Samples

| File | Description |
|------|-------------|
| `outputs/console_output.txt` | What you see in the terminal |
| `outputs/report.json` | JSON reporter output |
| `outputs/report.html` | HTML single-request report |
| `outputs/auto_fix_diff.txt` | Fix preview diff output |
| `outputs/query_budget_output.txt` | Budget enforcement output |

## Configuration Templates

| File | Use Case |
|------|----------|
| `configs/settings_minimal.py` | Getting started (1 line) |
| `configs/settings_production.py` | Production deployment |
| `configs/settings_ci.py` | CI/CD pipeline |
| `configs/settings_full.py` | Every option documented |
| `configs/queryignore_example` | .queryignore reference |
| `configs/ci_integration.yml` | GitHub Actions workflow |
