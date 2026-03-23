# Benchmark Dashboard

The benchmark dashboard is a self-contained HTML report showing QueryTurbo cache performance. It is generated from a point-in-time snapshot of the current process's `SQLCompilationCache` state.

---

## Generating the Report

```bash
python manage.py query_doctor_report
```

By default, the report is written to `query_doctor_report.html` in the current directory.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--output`, `-o` | `query_doctor_report.html` | Output file path |

```bash
# Custom output path
python manage.py query_doctor_report --output=reports/turbo-dashboard.html
```

!!! warning "Schema Information"
    The report contains SQL query templates (without parameter values) that may reveal database schema information. Do not share the report publicly if your schema is confidential.

---

## What the Dashboard Shows

### Summary Cards

Five cards showing aggregate cache metrics:

| Card | Description |
|------|-------------|
| **Cache Hits** | Total number of cache hits |
| **Cache Misses** | Total number of cache misses |
| **Hit Rate** | `hits / (hits + misses)` as a percentage |
| **Cache Utilization** | `current_size / max_size` as a percentage |
| **Evictions** | Number of LRU evictions |

### Charts

The dashboard includes Chart.js visualizations:

- **Cache Hits vs Misses** — Doughnut chart showing the hit/miss ratio
- **Top Queries by Hit Count** — Horizontal bar chart showing the top 10 most-hit cached queries
- **Prepared vs Non-Prepared Queries** — Bar chart showing how many of the top queries use prepared statements (only shown when prepared statement data is available)

### Top Optimized Queries Table

A sortable table of the top 20 cached queries, sorted by hit count:

| Column | Description |
|--------|-------------|
| `#` | Rank by hit count |
| SQL Preview | First 200 characters of the compiled SQL template |
| Model | The Django model label |
| Hit Count | Number of cache hits |
| Prepared | Whether the query uses prepared statements |

Click any column header to sort.

---

## When to Use

The dashboard is most useful after your application has been running for a while and the cache has warmed up. It provides insight into:

- Whether the cache is being utilized effectively (high hit rate = good)
- Which queries benefit most from caching
- Whether poisoned entries indicate fingerprint collisions
- Whether prepared statements are active (PostgreSQL + psycopg3)

!!! note "Process-Local Data"
    The cache resets on server restart. The dashboard reflects the current process's cache state only. In multi-process deployments, each worker has its own cache.

---

## Further Reading

- [QueryTurbo](queryturbo.md) — How the compilation cache works
- [Performance & Benchmarks](../deep-dive/performance.md) — Overhead model and benchmark numbers
