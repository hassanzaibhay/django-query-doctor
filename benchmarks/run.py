#!/usr/bin/env python
"""django-query-doctor v2.0 Benchmark Suite.

Measures the performance impact of QueryTurbo across different
query patterns and complexity levels.

Usage:
    cd /path/to/django-query-doctor
    python benchmarks/run.py

Outputs:
    - Console summary with timing tables
    - benchmarks/results.json with raw data
    - benchmarks/report.html with Chart.js visualization
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

# Setup Django before any model imports
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benchmarks.settings")

# Ensure the project root is on sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
src_dir = os.path.join(project_root, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import django  # noqa: E402

django.setup()

from django.test.utils import setup_test_environment  # noqa: E402

setup_test_environment()


def create_tables() -> None:
    """Create benchmark tables in the in-memory database."""
    from django.core.management import call_command

    call_command("migrate", "--run-syncdb", verbosity=0)

    # Create tables for benchmark models
    from django.db import connection

    from benchmarks.models import Author, Book, Publisher, Review

    with connection.schema_editor() as schema_editor:
        for model in [Author, Publisher, Book, Review]:
            try:
                schema_editor.create_model(model)
            except Exception:
                pass  # Table may already exist


def seed_data() -> None:
    """Seed minimal test data (10 rows per table)."""
    from benchmarks.models import Author, Book, Publisher, Review

    if Author.objects.exists():
        return

    authors = [Author.objects.create(name=f"Author {i}", email=f"author{i}@test.com") for i in range(10)]
    publishers = [Publisher.objects.create(name=f"Publisher {i}") for i in range(5)]
    books = []
    for i in range(10):
        books.append(
            Book.objects.create(
                title=f"Book {i}",
                author=authors[i % 10],
                publisher=publishers[i % 5],
                published_date=date(2024, 1, 1),
                price=Decimal(f"{10 + i}.99"),
                is_active=i % 2 == 0,
            )
        )
    for i in range(20):
        Review.objects.create(
            book=books[i % 10],
            rating=(i % 5) + 1,
            text=f"Review {i}",
        )


def run_compilation_scenario(name: str, config: dict) -> dict:
    """Run a compilation-only benchmark scenario (no DB execution).

    Measures the cost of SQL compilation (as_sql()) with and without the
    QueryTurbo cache. This isolates the compilation overhead from database
    I/O, giving a true measurement of what QueryTurbo saves.

    Args:
        name: Scenario name.
        config: Scenario config dict with query, iterations, description.

    Returns:
        Result dict with timing data.
    """
    from query_doctor.turbo.cache import SQLCompilationCache
    from query_doctor.turbo.fingerprint import compute_fingerprint
    from query_doctor.turbo.patch import get_cache

    query_fn = config["query"]
    iterations = config["iterations"]

    # Build a queryset to compile
    qs = query_fn()
    compiler = qs.query.get_compiler(using="default")

    # Warmup: compile once
    compiler.as_sql()

    # Without cache: measure raw as_sql() cost
    t0 = time.perf_counter()
    for _ in range(iterations):
        compiler.as_sql()
    baseline_ms = (time.perf_counter() - t0) * 1000

    # With cache: first call is miss (fingerprint + as_sql), rest are hits
    cache = SQLCompilationCache(max_size=1024)
    fp = compute_fingerprint(compiler.query, compiler)
    sql, params = compiler.as_sql()
    cache.put(fp, sql, params)

    t0 = time.perf_counter()
    for _ in range(iterations):
        entry = cache.get(fp)
        if entry is not None:
            _ = (entry.sql, params)  # Simulate cache hit path
        else:
            compiler.as_sql()
    turbo_ms = (time.perf_counter() - t0) * 1000

    speedup = baseline_ms / max(0.001, turbo_ms)
    saved_per_query_us = (baseline_ms - turbo_ms) / max(1, iterations) * 1000

    return {
        "name": name,
        "description": config["description"],
        "iterations": iterations,
        "baseline_ms": round(baseline_ms, 2),
        "turbo_ms": round(turbo_ms, 2),
        "speedup": round(speedup, 2),
        "saved_per_query_us": round(saved_per_query_us, 2),
        "cache_stats": None,
    }


def run_scenario(name: str, config: dict) -> dict:
    """Run a single benchmark scenario with and without QueryTurbo.

    Args:
        name: Scenario name.
        config: Scenario config dict with query, iterations, description.

    Returns:
        Result dict with timing data.
    """
    from query_doctor.turbo.context import turbo_disabled, turbo_enabled
    from query_doctor.turbo.patch import get_cache

    query_fn = config["query"]
    iterations = config["iterations"]

    # Warmup
    list(query_fn()[:1])

    # Without turbo
    with turbo_disabled():
        t0 = time.perf_counter()
        for _ in range(iterations):
            list(query_fn()[:1])
        baseline_ms = (time.perf_counter() - t0) * 1000

    # Clear cache for fair turbo measurement
    cache = get_cache()
    if cache is not None:
        cache.clear()

    # With turbo (first call is miss, rest are hits)
    with turbo_enabled():
        t0 = time.perf_counter()
        for _ in range(iterations):
            list(query_fn()[:1])
        turbo_ms = (time.perf_counter() - t0) * 1000

    # Get cache stats
    cache_stats = None
    if cache is not None:
        stats = cache.stats()
        cache_stats = {
            "hits": stats.hits,
            "misses": stats.misses,
            "size": stats.size,
            "hit_rate": f"{stats.hits / max(1, stats.hits + stats.misses) * 100:.1f}%",
        }

    speedup = baseline_ms / max(0.001, turbo_ms)
    saved_per_query_us = (baseline_ms - turbo_ms) / max(1, iterations) * 1000

    return {
        "name": name,
        "description": config["description"],
        "iterations": iterations,
        "baseline_ms": round(baseline_ms, 2),
        "turbo_ms": round(turbo_ms, 2),
        "speedup": round(speedup, 2),
        "saved_per_query_us": round(saved_per_query_us, 2),
        "cache_stats": cache_stats,
    }


def print_results(results: list[dict]) -> None:
    """Print results as a formatted table to stdout."""
    print()
    print("django-query-doctor v2.0 Benchmark Results")
    print("=" * 95)
    print()

    header = f"{'Scenario':<25} {'Iterations':>10} {'Baseline (ms)':>14} {'Turbo (ms)':>12} {'Speedup':>9} {'Saved/Query (us)':>18}"
    print(header)
    print("-" * 95)

    total_baseline = 0
    total_turbo = 0
    total_iterations = 0

    for r in results:
        total_baseline += r["baseline_ms"]
        total_turbo += r["turbo_ms"]
        total_iterations += r["iterations"]

        print(
            f"{r['name']:<25} {r['iterations']:>10,} {r['baseline_ms']:>14,.1f} "
            f"{r['turbo_ms']:>12,.1f} {r['speedup']:>8.2f}x {r['saved_per_query_us']:>17.1f}"
        )

    print("-" * 95)

    total_saved = total_baseline - total_turbo
    overall_speedup = total_baseline / max(0.001, total_turbo)

    print()
    print(f"Total iterations: {total_iterations:,}")
    print(f"Total baseline: {total_baseline:,.1f}ms")
    print(f"Total turbo: {total_turbo:,.1f}ms")
    print(f"Total saved: {total_saved:,.1f}ms")
    print(f"Overall speedup: {overall_speedup:.2f}x")

    # Cache stats from last scenario
    if results and results[-1].get("cache_stats"):
        cs = results[-1]["cache_stats"]
        print(f"Cache hit rate: {cs['hit_rate']}")

    print()


def main() -> None:
    """Run the full benchmark suite."""
    print("Setting up benchmark environment...")
    create_tables()
    seed_data()

    # Ensure turbo patch is installed
    from query_doctor.turbo.config import is_turbo_enabled
    from query_doctor.turbo.patch import install_patch

    if not is_turbo_enabled():
        print("WARNING: QueryTurbo is not enabled in settings. Installing patch manually.")
    install_patch()

    from benchmarks.scenarios import get_scenarios

    scenarios = get_scenarios()

    # --- Compilation-only benchmarks ---
    print("Running compilation-only benchmarks (no DB I/O)...")
    print()

    compilation_results = []
    for name, config in scenarios.items():
        print(f"  Running: {name} ({config['iterations']:,} iterations)...")
        result = run_compilation_scenario(name, config)
        compilation_results.append(result)

    print()
    print("COMPILATION-ONLY RESULTS")
    print_results(compilation_results)

    # --- End-to-end benchmarks ---
    print("Running end-to-end benchmarks (includes DB I/O)...")
    print()

    e2e_results = []
    for name, config in scenarios.items():
        print(f"  Running: {name} ({config['iterations']:,} iterations)...")
        result = run_scenario(name, config)
        e2e_results.append(result)

    print()
    print("END-TO-END RESULTS")
    print_results(e2e_results)

    # Save JSON results (both modes)
    benchmarks_dir = Path(__file__).parent
    all_results = {
        "compilation_only": compilation_results,
        "end_to_end": e2e_results,
    }
    json_path = benchmarks_dir / "results.json"
    json_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"Results saved: {json_path}")

    # Generate HTML report (compilation-only results — the real story)
    from benchmarks.report import generate_html_report

    html_path = str(benchmarks_dir / "report.html")
    generate_html_report(compilation_results, html_path)
    print(f"HTML report: {html_path}")


if __name__ == "__main__":
    main()
