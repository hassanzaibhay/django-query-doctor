# Performance

django-query-doctor is designed to have minimal impact on application performance. This document details the overhead model, memory usage, and strategies for controlling cost in different environments.

---

## Overhead Model

The overhead of django-query-doctor comes from three sources:

1. **Query interception**: Recording each SQL query as it executes
2. **Analysis**: Processing the captured queries at the end of the request
3. **Reporting**: Formatting and outputting the results

### Query Interception Cost

For each SQL query, the interceptor performs:

| Operation | Typical Cost | Notes |
|-----------|-------------|-------|
| `time.perf_counter()` (2 calls) | ~0.5 microseconds | Two calls: before and after query execution |
| `traceback.extract_stack()` | ~10-40 microseconds | Depends on call stack depth |
| Stack trace filtering | ~2-5 microseconds | Iterates frames, checks against ignore list |
| `CapturedQuery` construction | ~1-2 microseconds | Dataclass instantiation |
| List append | ~0.1 microseconds | Amortized O(1) |
| **Total per query** | **~15-50 microseconds** | **Excluding the SQL query itself** |

For context, a typical Django ORM query to PostgreSQL takes 0.5-5 milliseconds. The interception overhead of 15-50 microseconds represents 0.3-10% of query execution time, depending on query complexity.

### Analysis Cost Per Request

Analysis runs once at the end of the request, not per query.

| Operation | Complexity | Typical Cost |
|-----------|-----------|-------------|
| Fingerprinting (all queries) | O(n) where n = query count | ~0.5-2ms for 100 queries |
| N+1 detection | O(n) grouping + O(g) pattern matching | ~0.2-1ms |
| Duplicate detection | O(n) grouping | ~0.1-0.5ms |
| Missing index analysis | O(n) SQL inspection | ~0.2-1ms |
| Fat SELECT analysis | O(n) SQL inspection | ~0.1-0.5ms |
| Complexity scoring | O(n) SQL inspection | ~0.1-0.3ms |
| DRF serializer analysis | O(n) stack trace inspection | ~0.1-0.5ms |
| QuerySet eval analysis | O(n) pattern matching | ~0.1-0.3ms |
| **Total analysis** | **O(n)** | **~1-5ms for 100 queries** |

### Total Overhead by Request Type

| Request Type | Typical Query Count | Interception Overhead | Analysis Overhead | Total Overhead |
|-------------|:------------------:|:--------------------:|:-----------------:|:--------------:|
| Simple API endpoint | 3-10 | 0.05-0.5ms | 0.1-0.5ms | 0.15-1ms |
| List view (paginated) | 10-30 | 0.15-1.5ms | 0.3-1.5ms | 0.5-3ms |
| Dashboard page | 30-80 | 0.5-4ms | 1-3ms | 1.5-7ms |
| Complex report | 80-200 | 1.2-10ms | 2-5ms | 3-15ms |
| Unoptimized N+1 page | 200-500+ | 3-25ms | 3-8ms | 6-33ms |

> **Info:** The overhead scales linearly with the number of queries. For requests that execute fewer than 50 queries, the total overhead is typically under 3ms --- well within noise for most applications.

---

## Memory Usage

### Per-Query Memory

Each `CapturedQuery` object consumes approximately:

| Component | Size |
|-----------|------|
| SQL string reference | ~50 bytes (pointer + small string, or shared with Django) |
| Parameters tuple | ~100-200 bytes (varies with parameter count) |
| Timing floats (2x) | ~16 bytes |
| Stack trace (filtered, ~3-5 frames) | ~300-500 bytes |
| Fingerprint hash string | ~64 bytes (SHA-256 hex) |
| Dataclass overhead | ~50 bytes |
| **Total per query** | **~600-900 bytes** |

A rough estimate of **~800 bytes per query** is useful for capacity planning.

### Per-Request Memory

| Request Type | Query Count | Estimated Memory |
|-------------|:-----------:|:----------------:|
| Simple API endpoint | 5 | ~4 KB |
| List view | 20 | ~16 KB |
| Dashboard page | 50 | ~40 KB |
| Complex report | 150 | ~120 KB |
| Unoptimized N+1 page | 500 | ~400 KB |

All captured query data is released at the end of the request when the context variable is cleared. There is no accumulation across requests.

> **Tip:** If memory is a concern for requests with very high query counts (500+), consider fixing the underlying query issues first --- that is exactly what django-query-doctor is for. A request with 500 queries has far bigger problems than 400 KB of diagnostic memory.

---

## Zero-Overhead Mode

When django-query-doctor is disabled, the overhead is effectively zero. The middleware checks the `ENABLED` setting at the start of each request and short-circuits immediately:

```python
# middleware.py (simplified)
class QueryDoctorMiddleware:
    def __call__(self, request):
        config = get_config()
        if not config["ENABLED"]:
            return self.get_response(request)  # Zero overhead path
        # ... interception and analysis ...
```

To disable:

```python
# settings.py
QUERY_DOCTOR = {
    "ENABLED": False,
}
```

The overhead of the disabled path is a single dictionary lookup and boolean check --- roughly 0.1 microseconds per request.

### Environment-Based Toggle

A common pattern is to enable django-query-doctor only in specific environments:

```python
# settings.py
import os

QUERY_DOCTOR = {
    "ENABLED": os.environ.get("QUERY_DOCTOR_ENABLED", "false").lower() == "true",
}
```

This allows you to deploy the same code everywhere but only activate diagnostics when needed:

```bash
# Enable for a staging deploy
QUERY_DOCTOR_ENABLED=true gunicorn myapp.wsgi

# Disable for production (default)
gunicorn myapp.wsgi
```

---

## Stack Trace Optimization

Stack trace capture (`traceback.extract_stack()`) is the single most expensive per-query operation, accounting for roughly 60-80% of the interception overhead. If you need to reduce overhead, you can disable stack traces:

```python
QUERY_DOCTOR = {
    "CAPTURE_STACK_TRACES": False,
}
```

### Impact of Disabling Stack Traces

| Aspect | With Stack Traces | Without Stack Traces |
|--------|:-----------------:|:-------------------:|
| Per-query overhead | ~15-50 microseconds | ~3-8 microseconds |
| Per-query memory | ~800 bytes | ~300 bytes |
| File:line in prescriptions | Yes | No |
| Suggested fix location | Exact file and line | General suggestion only |
| N+1 detection | Full accuracy | Full accuracy |
| Duplicate detection | Full accuracy | Full accuracy |
| DRF serializer analysis | Full accuracy | Reduced (cannot identify serializer source) |

> **Warning:** Without stack traces, prescriptions will still identify the issue and suggest the fix, but they cannot tell you *where* in your code the fix needs to be applied. This makes django-query-doctor significantly less useful in large codebases where the same model is accessed from many locations.

### Stack Depth Limiting

An alternative to fully disabling stack traces is to limit the depth:

```python
QUERY_DOCTOR = {
    "STACK_TRACE_MAX_DEPTH": 10,  # Default: no limit
}
```

This captures only the 10 most recent frames, which is usually sufficient to reach user code while reducing the cost of deep call stacks (common in DRF, Celery, and deeply nested view logic).

---

## Recommended Workflows

### Local Development

Use the full feature set. The overhead is negligible compared to development server response times:

```python
# settings/local.py
QUERY_DOCTOR = {
    "ENABLED": True,
    "REPORT_FORMAT": "console",
    "CAPTURE_STACK_TRACES": True,
}
```

### CI/CD Pipeline

Run the management command or pytest plugin to catch regressions. Overhead does not matter since these are batch jobs:

```yaml
# .github/workflows/ci.yml
- name: Query Doctor Check
  run: python manage.py diagnose_queries --format=json --fail-on-issues
```

### Staging Environment

Enable with full features for targeted debugging. Consider using path-based filtering to reduce noise:

```python
# settings/staging.py
QUERY_DOCTOR = {
    "ENABLED": True,
    "REPORT_FORMAT": "json",
    "CAPTURE_STACK_TRACES": True,
    "INCLUDE_PATHS": ["/api/v2/", "/dashboard/"],  # Only analyze these paths
}
```

### Production (Sampling)

If you need production visibility, enable with sampling to control overhead:

```python
# settings/production.py
import random

QUERY_DOCTOR = {
    "ENABLED": True,
    "SAMPLE_RATE": 0.01,  # Analyze 1% of requests
    "REPORT_FORMAT": "json",
    "CAPTURE_STACK_TRACES": False,  # Minimize overhead
}
```

> **Note:** Even at 1% sampling, you will quickly surface the most common query issues since they tend to appear on high-traffic endpoints. A single hour of 1% sampling on a 1000-rps application gives you ~36,000 analyzed requests.

### Production (Zero Overhead)

If you do not need runtime diagnostics in production, disable entirely and rely on CI/CD for regression detection:

```python
# settings/production.py
QUERY_DOCTOR = {
    "ENABLED": False,
}
```

---

## Benchmarking Your Own Overhead

You can measure django-query-doctor's overhead in your specific application:

```python
import time
from django.test import RequestFactory
from myapp.views import BookListView

factory = RequestFactory()
request = factory.get("/api/books/")

# Warm up
for _ in range(10):
    BookListView.as_view()(request)

# Measure without django-query-doctor
times_without = []
for _ in range(100):
    start = time.perf_counter()
    BookListView.as_view()(request)
    times_without.append(time.perf_counter() - start)

# Enable django-query-doctor and measure again
# (toggle via settings or context manager)
from query_doctor.context_managers import diagnose_queries

times_with = []
for _ in range(100):
    start = time.perf_counter()
    with diagnose_queries(report=False):  # Suppress output
        BookListView.as_view()(request)
    times_with.append(time.perf_counter() - start)

avg_without = sum(times_without) / len(times_without) * 1000
avg_with = sum(times_with) / len(times_with) * 1000
overhead = avg_with - avg_without

print(f"Without: {avg_without:.2f}ms")
print(f"With:    {avg_with:.2f}ms")
print(f"Overhead: {overhead:.2f}ms ({overhead / avg_without * 100:.1f}%)")
```

---

## QueryTurbo Compilation-Skip Benchmarks *(v2.0)*

When [QueryTurbo](../guides/queryturbo.md) is enabled and a query reaches TRUSTED state, the `as_sql()` call is skipped entirely. Parameters are extracted directly from the Django Query tree.

### Compilation-Skip Speedups

Measured on SQLite (compilation-only, no DB I/O). Run `python benchmarks/run.py` to reproduce.

| Query Pattern | Speedup | Saved per Query |
|---|---|---|
| Simple filter | 123x | 38.8 μs |
| Multi filter | 153x | 49.2 μs |
| select_related | 294x | 92.5 μs |
| Deep select_related | 374x | 121.1 μs |
| Annotate | 214x | 68.6 μs |
| Complex (JOINs + Q + annotate) | 1,050x | 337.9 μs |

### Prepared Statement Savings (PostgreSQL + psycopg3)

On PostgreSQL with psycopg3, prepared statements provide additional savings of 0.5--5ms of query planner time per repeat query, with the greatest benefit on complex queries with multiple JOINs.

### Database Backend Support

| Backend | Compilation Cache | Prepared Statements | Notes |
|---------|:-:|:-:|---|
| PostgreSQL (psycopg3) | Yes | Yes | Full support |
| PostgreSQL (psycopg2) | Yes | No | Cache only |
| MySQL | Yes | No | Cache only |
| SQLite | Yes | No | Good for dev/test |
| Oracle | Yes | Implicit | Via cx_Oracle cursor cache |

### QueryTurbo Memory Overhead

The compilation cache stores SQL templates and metadata. Each cache entry uses approximately 500-2000 bytes depending on SQL length. With the default `MAX_SIZE` of 1024 entries, the cache uses at most ~2 MB of memory.

The cache is process-local. In multi-process deployments (e.g., gunicorn with 4 workers), each worker maintains its own cache, so total memory usage is `~2 MB × worker_count`.

See [QueryTurbo](../guides/queryturbo.md) for configuration details and the [Benchmark Dashboard](../guides/benchmark-dashboard.md) for monitoring cache performance.

---

For a detailed comparison of how this overhead compares to other tools, see [Comparison](./comparison.md). For the architectural reasons behind these performance characteristics, see [Background & Design](./background.md).
