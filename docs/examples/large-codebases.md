# Large Codebase Strategies

When adopting django-query-doctor in a large Django project, you need a
strategy that avoids overwhelming developers with hundreds of prescriptions at
once. This page covers incremental adoption, CI integration, and techniques for
managing query health at scale.

---

## Strategy Overview

| Approach | Best For | Description |
|----------|----------|-------------|
| Middleware off + CI commands | Large existing codebases | Run analysis in CI only, no runtime overhead |
| Diff-aware mode | Active development teams | Analyze only files changed in a PR |
| `.queryignore` | Known exceptions | Suppress false positives and accepted trade-offs |
| Per-app scanning | Monoliths | Analyze one Django app at a time |
| Query budgets | Performance-critical endpoints | Enforce hard limits on query counts |
| Gradual rollout | Any large project | Enable analyzers one at a time |

---

## Middleware Off + Commands in CI

For large codebases, running the middleware on every development request can be
noisy. Instead, disable the middleware and run analysis through management
commands in CI:

```python title="settings.py"
QUERY_DOCTOR = {
    "ENABLED": False,  # Middleware disabled
}
```

```yaml title=".github/workflows/query-check.yml"
name: Query Analysis

on: [pull_request]

jobs:
  query-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run query analysis
        run: python manage.py check_queries --reporter json --output reports/

      - name: Enforce zero critical issues
        run: |
          CRITICAL=$(cat reports/query-doctor/*.json | \
            jq '[.prescriptions[] | select(.severity == "critical")] | length')
          if [ "$CRITICAL" -gt 0 ]; then
            echo "::error::Found $CRITICAL critical query issues"
            exit 1
          fi
```

!!! tip "Targeted local analysis"
    Developers can still use the context manager or decorator for targeted
    analysis during development without enabling the middleware globally:
    ```python
    from query_doctor.context_managers import diagnose_queries

    with diagnose_queries():
        response = client.get("/api/orders/")
    ```

---

## Diff-Aware Mode

The `--diff` flag for `check_queries` restricts analysis to files that changed
relative to a git ref. This prevents existing issues from blocking PRs:

```bash
# Analyze only files changed vs main branch
python manage.py check_queries --diff origin/main

# Analyze only files changed in the last commit
python manage.py check_queries --diff HEAD~1
```

### CI Integration

```yaml title=".github/workflows/query-check.yml"
- name: Diff-aware query check
  run: |
    python manage.py check_queries \
      --diff origin/${{ github.base_ref }} \
      --reporter json \
      --output reports/
```

!!! info "How diff-aware mode works"
    The command runs `git diff --name-only` against the specified ref, then
    filters prescriptions to only include those whose `location.file` matches
    a changed file. This means new N+1 queries introduced in a PR are caught,
    but existing issues in unchanged files are ignored.

---

## .queryignore

The `.queryignore` file lets you suppress known false positives, accepted
trade-offs, and third-party code issues. Place it in your project root:

```text title=".queryignore"
# Syntax: one rule per line
# Prefix with the rule type: sql:, file:, callsite:, issue:

# Ignore queries from Django admin (acceptable trade-off)
file:django/contrib/admin/*

# Ignore a specific query pattern from a third-party package
sql:SELECT * FROM "django_session"

# Ignore a specific callsite that we've audited and accepted
callsite:myapp/legacy_views.py:142

# Ignore all fat-select issues in the reporting module (intentional SELECT *)
issue:FatSelectAnalyzer file:reporting/*

# Ignore duplicate queries in the caching layer (by design)
issue:DuplicateQueryAnalyzer file:myapp/cache.py
```

### Rule Types

| Prefix | Matches Against | Example |
|--------|----------------|---------|
| `sql:` | SQL fingerprint pattern | `sql:SELECT * FROM "auth_user"` |
| `file:` | Source file path (glob) | `file:myapp/legacy/*` |
| `callsite:` | Specific file:line | `callsite:views.py:42` |
| `issue:` | Analyzer class name | `issue:FatSelectAnalyzer` |

Rules can be combined on a single line: `issue:FatSelectAnalyzer file:reporting/*`
matches fat-select issues only in the reporting directory.

!!! warning "Review .queryignore periodically"
    Suppressed issues can mask real problems. Review your `.queryignore` file
    quarterly and remove rules for code that has been refactored.

---

## Per-App Scanning with diagnose_project

For Django monoliths with many apps, scan one app at a time using the
`diagnose_project` command:

```bash
# Scan a single app
python manage.py diagnose_project --app orders

# Scan multiple apps
python manage.py diagnose_project --app orders --app products --app users

# Scan all apps and generate a per-app scoreboard
python manage.py diagnose_project --all --reporter html --output reports/project.html
```

### Per-App Health Report

The HTML output from `diagnose_project` includes an app scoreboard:

```
App Scoreboard
+-------------+--------+-----------+----------+-------+-------+
| App         | Score  | Critical  | Warnings | Info  | URLs  |
+-------------+--------+-----------+----------+-------+-------+
| orders      | 45/100 | 3         | 7        | 2     | 12    |
| products    | 78/100 | 0         | 3        | 5     | 8     |
| users       | 92/100 | 0         | 1        | 1     | 5     |
| reporting   | 100    | 0         | 0        | 0     | 3     |
+-------------+--------+-----------+----------+-------+-------+
```

!!! tip "Assign app owners"
    Use the per-app scoreboard to assign query health ownership. Each team
    owns their app's score and is responsible for addressing critical issues.

---

## Query Budgets per Endpoint

Set hard query count limits on specific endpoints. Exceeding the budget causes
a warning in development and can fail CI builds:

### Using the Decorator

```python title="orders/views.py"
from query_doctor.decorators import query_budget


@query_budget(max_queries=10)
def order_list(request):
    """This view must execute no more than 10 queries."""
    orders = Order.objects.select_related("customer").prefetch_related("items")
    return render(request, "orders/list.html", {"orders": orders})
```

### Using the Management Command

```bash
# Check all budgets
python manage.py query_budget

# Fail if any endpoint exceeds its budget
python manage.py query_budget --strict
```

### Setting Budgets in Configuration

```python title="settings.py"
QUERY_DOCTOR = {
    "QUERY_BUDGETS": {
        "/api/orders/": 10,
        "/api/products/": 15,
        "/api/users/me/": 5,
        "/dashboard/": 25,
    },
}
```

!!! note "Choosing budget values"
    Start by measuring current query counts, then set budgets at that level
    to prevent regressions. Tighten budgets over time as you optimize.

---

## Gradual Rollout Strategy

For large codebases, enable analyzers incrementally rather than all at once:

### Phase 1: Critical Issues Only

Start with just the N+1 analyzer to catch the highest-impact issues:

```python title="settings.py"
QUERY_DOCTOR = {
    "ANALYZERS": [
        "query_doctor.analyzers.NPlusOneAnalyzer",
    ],
    "MIN_SEVERITY": "CRITICAL",
}
```

### Phase 2: Add Duplicate Detection

Once N+1 issues are under control, add duplicate query detection:

```python title="settings.py"
QUERY_DOCTOR = {
    "ANALYZERS": [
        "query_doctor.analyzers.NPlusOneAnalyzer",
        "query_doctor.analyzers.DuplicateQueryAnalyzer",
    ],
    "MIN_SEVERITY": "WARNING",
}
```

### Phase 3: Full Analysis

Enable all analyzers once the team is comfortable with the workflow:

```python title="settings.py"
QUERY_DOCTOR = {
    "ANALYZERS": [
        "query_doctor.analyzers.NPlusOneAnalyzer",
        "query_doctor.analyzers.DuplicateQueryAnalyzer",
        "query_doctor.analyzers.MissingIndexAnalyzer",
        "query_doctor.analyzers.FatSelectAnalyzer",
        "query_doctor.analyzers.QuerySetEvalAnalyzer",
        "query_doctor.analyzers.DRFSerializerAnalyzer",
        "query_doctor.analyzers.QueryComplexityAnalyzer",
    ],
}
```

### Rollout Timeline

| Week | Action | Expected Outcome |
|------|--------|-----------------|
| 1-2 | Enable N+1 analyzer, CI warning only | Identify worst offenders |
| 3-4 | Fix critical N+1 issues, add `.queryignore` for accepted ones | Critical count reaches 0 |
| 5-6 | Enable duplicate analyzer | Catch redundant queries |
| 7-8 | Enable remaining analyzers, set query budgets | Full coverage |
| 9+ | Enforce in CI (fail on critical), tighten budgets | Continuous improvement |

!!! info "Team buy-in"
    Share the per-app scoreboard with the team before enforcing in CI.
    Developers are more receptive to new tooling when they can see the
    concrete impact on their code.

---

## Performance Considerations

Running analysis on every request in a large application adds overhead. Here
are strategies to manage it:

### Sample Requests

Analyze only a percentage of requests in development:

```python title="settings.py"
QUERY_DOCTOR = {
    "SAMPLE_RATE": 0.1,  # Analyze 10% of requests
}
```

### Exclude High-Traffic Paths

Skip analysis on paths that are called frequently but are already optimized:

```python title="settings.py"
QUERY_DOCTOR = {
    "EXCLUDE_PATHS": [
        "/admin/",
        "/static/",
        "/__debug__/",
        "/health/",
        "/api/v1/heartbeat/",
    ],
}
```

### CI-Only Analysis

The lowest-overhead approach: disable the middleware entirely and run
`check_queries` only in CI:

```python title="settings/production.py"
QUERY_DOCTOR = {
    "ENABLED": False,
}
```

```python title="settings/ci.py"
QUERY_DOCTOR = {
    "ENABLED": True,
    "REPORTERS": ["query_doctor.reporters.JSONReporter"],
}
```

See also: [Real-World Examples](real-world.md) | [DRF ViewSet Examples](drf-viewsets.md) | [Configuration](../getting-started/configuration.md)
