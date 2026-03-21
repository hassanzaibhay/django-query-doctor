---
hide:
  - navigation
---

# django-query-doctor

**Automated diagnosis and prescriptions for slow Django ORM queries.**

django-query-doctor intercepts your Django ORM queries at runtime, fingerprints them, runs them through 7 built-in analyzers, and produces actionable prescriptions with exact file:line references and copy-paste code fixes.

---

## Why django-query-doctor?

Every Django project eventually hits ORM performance problems — N+1 queries hiding behind serializers, duplicate queries scattered across views, missing indexes silently slowing down every page load. Finding them means digging through django-debug-toolbar panels or manually adding `select_related` everywhere.

**django-query-doctor catches these automatically.** Drop in the middleware, and every request gets analyzed. Or run the management commands in CI and catch regressions before they ship.

## Key Features

- **7 Analyzers** — N+1, duplicate, missing index, fat SELECT, queryset evaluation, DRF serializer N+1, query complexity
- **5 Reporters** — Rich console, JSON, HTML dashboard, Python logging, OpenTelemetry
- **6 Management Commands** — `check_queries`, `query_budget`, `fix_queries`, `diagnose_project`, `check_serializers`, `query_doctor_report`
- **Auto-Fix Mode** — Automatically apply suggested `select_related`/`prefetch_related` fixes
- **Pytest Plugin** — Assert query counts and detect issues in your test suite
- **Celery & Async Support** — Works with Celery tasks and async/ASGI views
- **Admin Dashboard** — Visual query health overview in Django admin
- **Custom Plugins** — Write your own analyzers via Python entry points
- **CI/CD Ready** — Diff-aware mode, `.queryignore` file, query budgets

## Quick Example
```python
# settings.py
INSTALLED_APPS = [
    ...,
    "query_doctor",
]

MIDDLEWARE = [
    ...,
    "query_doctor.middleware.QueryDoctorMiddleware",
]
```

That's it. Every request now gets analyzed automatically.

## Numbers

| Metric | Value |
|--------|-------|
| Built-in analyzers | 7 |
| Reporters | 5 |
| Management commands | 6 |
| Test cases | 625+ |
| Code coverage | 87%+ |
| Python | 3.10 – 3.13 |
| Django | 4.2 – 6.0 |
| License | MIT |

---

[Get Started :material-arrow-right:](getting-started/installation.md){ .md-button .md-button--primary }
[View on GitHub :material-github:](https://github.com/hassanzaibhay/django-query-doctor){ .md-button }
[View on PyPI :material-language-python:](https://pypi.org/project/django-query-doctor/){ .md-button }
