# Comparison with Other Tools

This document provides a detailed feature comparison between django-query-doctor and other Django query analysis tools, along with guidance on when to use each tool and how they can work together.

---

## Feature Matrix

| Feature | django-query-doctor | django-debug-toolbar | django-silk | nplusone | django-auto-prefetch |
|---------|:-------------------:|:--------------------:|:-----------:|:--------:|:--------------------:|
| **Detection** | | | | | |
| N+1 query detection | Yes | No (manual inspection) | No (manual inspection) | Yes | N/A (prevents, not detects) |
| Duplicate query detection | Yes | Partial (shows count) | No | No | No |
| Missing index detection | Yes | No | No | No | No |
| Fat SELECT detection | Yes | No | No | No | No |
| Query complexity scoring | Yes | No | No | No | No |
| DRF serializer analysis | Yes | No | No | No | No |
| QuerySet evaluation issues | Yes | No | No | No | No |
| **Diagnostics** | | | | | |
| File:line source location | Yes | No | Partial (request only) | Partial (model only) | No |
| Auto-fix suggestions | Yes | No | No | No | N/A |
| Copy-paste fix code | Yes | No | No | No | No |
| Prescription severity levels | Yes | No | No | No | No |
| SQL fingerprinting | Yes | No | No | No | No |
| **Environments** | | | | | |
| Works without `DEBUG=True` | Yes | No | Yes | Yes | Yes |
| Production-safe | Yes | No | Partial (overhead) | Yes | Yes |
| Zero required dependencies | Yes | No | No | No | No |
| **Integration** | | | | | |
| Management commands | Yes | No | No | No | No |
| Pytest plugin | Yes | No | No | Partial | No |
| Celery task support | Yes | No | Yes | No | No |
| Async Django support | Yes | Yes | No | No | Yes |
| CI/CD integration | Yes | No | No | No | No |
| Git diff-aware filtering | Yes | No | No | No | No |
| Query budgets (per-view) | Yes | No | No | No | No |
| **Output** | | | | | |
| Console output | Yes | No (browser only) | No (browser only) | Yes (warnings) | No |
| JSON output | Yes | No | Yes (API) | No | No |
| HTML dashboard | Yes | Yes | Yes | No | No |
| OpenTelemetry export | Yes | No | No | No | No |
| **Extensibility** | | | | | |
| Custom analyzer plugins | Yes | No | No | No | No |
| Custom reporter plugins | Yes | Yes (panels) | No | No | No |
| Ignore rules | Yes | No | Yes | Yes | No |
| **Configuration** | | | | | |
| Zero-config setup | Yes | Partial | No | Yes | Yes |
| Per-view configuration | Yes | No | No | No | No |
| Sampling support | Yes | No | Yes | No | No |

---

## Tool-by-Tool Comparison

### vs. django-debug-toolbar

**django-debug-toolbar** is the most widely used Django debugging tool. It provides a browser-based panel showing SQL queries, template rendering, cache hits, signals, and more.

**Strengths of debug-toolbar:**
- Comprehensive debugging beyond just SQL (templates, cache, signals, headers)
- Interactive browser UI with collapsible query details
- Mature ecosystem with many third-party panels
- Shows EXPLAIN output for individual queries

**Where django-query-doctor adds value:**
- Automatic pattern detection (N+1, duplicates) instead of manual inspection
- Works in non-browser contexts (API endpoints, management commands, Celery tasks)
- Works without `DEBUG=True`, enabling staging and production analysis
- Generates fix suggestions, not just query lists
- CI/CD integration for automated regression detection

> **Tip:** These tools solve different problems. debug-toolbar is an interactive debugging tool; django-query-doctor is an automated analysis tool. They work well together. See "Using Tools Together" below.

### vs. django-silk

**django-silk** is a profiling and request inspection tool that stores request/response data and SQL queries in the database for later analysis.

**Strengths of django-silk:**
- Persistent storage of profiling data across requests
- Code profiling (cProfile integration) beyond just SQL
- Request/response body inspection
- Historical comparison of request performance

**Where django-query-doctor adds value:**
- No database tables or storage overhead required
- Automatic issue detection instead of manual analysis
- Fix suggestions with exact code changes
- Lighter weight: no UI server, no database writes per request
- CI/CD integration

### vs. nplusone

**nplusone** is the closest existing tool in concept. It specifically detects N+1 queries by monitoring lazy-loaded relationship access.

**Strengths of nplusone:**
- Focused, simple implementation
- Low overhead for its specific use case
- Integrates with pytest via warnings

**Where django-query-doctor adds value:**
- Six additional detection categories beyond N+1
- Exact file:line references (nplusone reports the model/relationship only)
- Copy-paste fix code generation
- Management commands for full-project scanning
- Query budgets and CI/CD enforcement
- Git diff-aware filtering for incremental adoption

### vs. django-auto-prefetch

**django-auto-prefetch** takes a fundamentally different approach: instead of detecting and reporting issues, it automatically adds `select_related` to ForeignKey access at the model level.

**Strengths of django-auto-prefetch:**
- Zero developer effort after initial setup
- Immediate performance improvement for ForeignKey N+1
- No reports to read or fixes to apply

**Where django-query-doctor adds value:**
- Visibility into what is happening (auto-prefetch is invisible)
- Handles ManyToMany relationships (auto-prefetch does not)
- Detects issues beyond N+1 (duplicates, missing indexes, etc.)
- Does not modify query behavior (auto-prefetch changes JOINs globally)
- Helps developers learn to write better querysets
- Per-view control instead of global behavior change

> **Warning:** django-auto-prefetch modifies your application's query behavior globally. While this can improve performance, it can also lead to unexpected query shapes and makes it harder to reason about database access patterns. django-query-doctor prefers explicit fixes over implicit behavior changes.

---

## When to Use What

### Use django-query-doctor when:

- You want to systematically find and fix query issues across your project
- You need CI/CD enforcement to prevent query regressions
- You are working on API endpoints (not just browser-rendered pages)
- You need to analyze queries in staging or production (without `DEBUG=True`)
- You want prescriptive fixes, not just detection
- You are onboarding a team to better ORM practices

### Use django-debug-toolbar when:

- You are actively debugging a specific page in the browser
- You need to inspect template rendering, cache behavior, or signals
- You want to run EXPLAIN on a specific query interactively
- You are in local development with `DEBUG=True`

### Use django-silk when:

- You need to profile Python code execution (not just SQL)
- You want to store and compare historical request performance
- You need to inspect request/response bodies
- You have a dedicated profiling environment

### Use nplusone when:

- You only care about N+1 detection and want a minimal tool
- You want N+1 detection as pytest warnings without any setup

### Use django-auto-prefetch when:

- You want an immediate fix for ForeignKey N+1 without changing any view code
- You understand and accept the trade-off of invisible query modification
- Your N+1 issues are predominantly on ForeignKey relationships (not M2M)

---

## Using Tools Together

These tools are not mutually exclusive. Here are recommended combinations:

### Development Stack

```python
# settings/local.py
INSTALLED_APPS = [
    # ...
    "debug_toolbar",  # Interactive browser debugging
]

MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",  # Browser UI
    "query_doctor.middleware.QueryDoctorMiddleware",    # Automated analysis
    # ...
]
```

Use debug-toolbar for interactive exploration and django-query-doctor for automated detection. When debug-toolbar shows you a page with many queries, django-query-doctor tells you exactly which ones are problems and how to fix them.

### CI Stack

```yaml
# .github/workflows/ci.yml
steps:
  - name: Run tests with query analysis
    run: pytest --query-doctor --fail-on-query-issues

  - name: Full project scan
    run: python manage.py diagnose_queries --format=json --fail-on-issues
```

In CI, only django-query-doctor and nplusone can run (debug-toolbar and silk require a browser/server). django-query-doctor provides the most comprehensive CI analysis.

### Production Stack

```python
# settings/production.py
QUERY_DOCTOR = {
    "ENABLED": True,
    "SAMPLE_RATE": 0.01,           # 1% of requests
    "REPORT_FORMAT": "json",
    "CAPTURE_STACK_TRACES": False,  # Minimize overhead
}
```

In production, only django-query-doctor and django-auto-prefetch are suitable. django-auto-prefetch provides automatic mitigation; django-query-doctor provides visibility and detection. They can coexist: auto-prefetch handles ForeignKey N+1 automatically while django-query-doctor catches everything else.

---

## Migration Guide

### From django-debug-toolbar (adding django-query-doctor)

No migration needed. Keep debug-toolbar for interactive debugging and add django-query-doctor alongside it:

```python
MIDDLEWARE = [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
    "query_doctor.middleware.QueryDoctorMiddleware",
    # ...
]
```

### From nplusone to django-query-doctor

1. Replace `nplusone.middleware.NPlusOneMiddleware` with `query_doctor.middleware.QueryDoctorMiddleware`.
2. Remove `nplusone` from `INSTALLED_APPS` and `MIDDLEWARE`.
3. django-query-doctor covers all of nplusone's detection and more.

```python
# Before
INSTALLED_APPS = ["nplusone.ext.django", ...]
MIDDLEWARE = ["nplusone.ext.django.NPlusOneMiddleware", ...]

# After
MIDDLEWARE = ["query_doctor.middleware.QueryDoctorMiddleware", ...]
```

### From django-auto-prefetch (adding django-query-doctor)

Keep django-auto-prefetch if it is working well for you. Add django-query-doctor to catch the issues auto-prefetch does not handle (M2M, duplicates, missing indexes, etc.):

```python
MIDDLEWARE = [
    "query_doctor.middleware.QueryDoctorMiddleware",
    # ...
]

# django-auto-prefetch is configured at the model level, not in middleware
```

> **Note:** With both tools active, django-query-doctor will not report N+1 issues on ForeignKey relationships that django-auto-prefetch has already resolved. You will still see reports for M2M relationships and other issue categories.

---

## Summary Table

| Scenario | Recommended Tool(s) |
|----------|---------------------|
| Find all query issues in a project | django-query-doctor |
| Interactive page debugging | django-debug-toolbar |
| CI/CD query regression prevention | django-query-doctor |
| Production query monitoring | django-query-doctor (sampled) |
| Quick ForeignKey N+1 mitigation | django-auto-prefetch |
| Python code profiling | django-silk |
| Minimal N+1 detection only | nplusone |
| Comprehensive development setup | django-debug-toolbar + django-query-doctor |
| Comprehensive production setup | django-auto-prefetch + django-query-doctor (sampled) |

For details on django-query-doctor's architecture, see [Architecture](./architecture.md). For performance characteristics, see [Performance](./performance.md). For the reasoning behind these design choices, see [Background & Design](./background.md).
