---
hide:
  - navigation
---

# django-query-doctor

Automated diagnosis and prescriptions for slow Django ORM queries — with exact file:line references and copy-paste code fixes.

## Where to Start

| Goal | Page |
|------|------|
| First-time setup | [Quick Start](getting-started/quickstart.md) |
| Catch issues in CI | [Baseline Regression](guides/baseline.md) |
| Faster query compilation | [QueryTurbo](guides/queryturbo.md) |
| Integrate with test suite | [Pytest Plugin](guides/pytest-plugin.md) |
| Analyze DRF serializers | [DRF Serializer Analyzer](analyzers/drf-serializer.md) |
| Full configuration reference | [Configuration](getting-started/configuration.md) |

## What's New in v2.0

- **QueryTurbo** — SQL compilation cache with 3-phase trust lifecycle (UNTRUSTED → TRUSTED → POISONED). Skips `as_sql()` on trusted hits.
- **Prepared Statements** — Automatic protocol-level prepared statements on PostgreSQL with psycopg3.
- **AST SerializerMethodField Analyzer** — Static analysis of `get_<field>` methods catches hidden N+1s without running code.
- **Baseline Snapshots** — Save known issues, detect only new regressions in CI.
- **Benchmark Dashboard** — Interactive HTML report with Chart.js showing cache hit rates and top optimized queries.
- **Smart Grouping** — Group prescriptions by file+analyzer, root cause, or view.

[Full changelog →](changelog.md)

## Quick Install

```python
# settings.py
INSTALLED_APPS = [..., "query_doctor"]
MIDDLEWARE = [..., "query_doctor.middleware.QueryDoctorMiddleware"]
```

---

[Get Started :material-arrow-right:](getting-started/installation.md){ .md-button .md-button--primary }
[View on GitHub :material-github:](https://github.com/hassanzaibhay/django-query-doctor){ .md-button }
[View on PyPI :material-language-python:](https://pypi.org/project/django-query-doctor/){ .md-button }
