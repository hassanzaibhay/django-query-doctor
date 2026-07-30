"""Measure ``pipeline.analyze()`` cost against captured-query count.

Regenerates the analysis-stage figures quoted in
``docs/guides/async-support.md``. Run on demand; this is not a CI gate, because
timings on a shared runner are noisy and a flaky required check is worse than an
unsourced figure.

    python -m scripts.bench_analyze

Why the workload shape is printed rather than described in prose: every grouping
analyzer is O(distinct fingerprints), not O(queries), and ``write_nplusone``
inspects only non-SELECT captures. So the same "500 queries" can differ by an
order of magnitude depending on how many fingerprints it spans and how many of
those queries are writes. A figure quoted without that shape cannot be
reproduced, which is how the previous generation of these numbers went stale
unnoticed.

Deliberately self-contained: stdlib timing only, no new dependencies, and no
imports from ``benchmarks/`` or ``tests/``. This module is covered by the
``ruff`` and ``mypy`` gates, and importing either of those trees would pull their
current errors into the typecheck gate.

No database is touched. Analyzers parse SQL strings and read model ``_meta``;
none of them executes a query, so ``django.contrib.auth`` models are configured
purely to give model resolution real work to do.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from time import perf_counter
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from query_doctor.types import CapturedQuery

# Query counts to report. Mirrors the rows the async guide quotes so the
# published figures can be compared directly against a fresh run.
DEFAULT_COUNTS = (0, 1, 10, 50, 100, 500)

# Captures per distinct SELECT fingerprint. Twenty-five is comfortably over the
# nplusone and duplicate thresholds, so the grouping analyzers do the work of
# building prescriptions rather than just counting groups and discarding them.
SELECTS_PER_GROUP = 25

# Share of the workload that is non-SELECT. write_nplusone examines only these,
# so an all-SELECT workload would measure seven analyzers rather than eight.
WRITE_SHARE = 0.25


class Stats(NamedTuple):
    """Timing summary for one query count, in milliseconds per call."""

    queries: int
    median: float
    p10: float
    p90: float
    fastest: float
    slowest: float


class Shape(NamedTuple):
    """The composition of a generated workload, reported alongside the timings."""

    total: int
    selects: int
    writes: int
    fingerprints: int
    callsites: int


def _configure_django() -> None:
    """Configure the minimum Django needed for analyzers to resolve models."""
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            DATABASES={},
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ],
            USE_TZ=True,
        )

    import django

    django.setup()


def _build_workload(total: int) -> tuple[list[CapturedQuery], Shape]:
    """Build ``total`` synthetic captures with a documented, fixed composition.

    SELECTs are spread over several fingerprints at ``SELECTS_PER_GROUP`` each so
    the grouping analyzers produce real findings; writes share one fingerprint,
    which is the shape a ``.save()`` loop actually produces. Callsites are
    pre-attached, so the harness measures analysis only and never exercises stack
    capture.
    """
    from query_doctor.fingerprint import fingerprint, normalize_sql
    from query_doctor.types import CallSite, CapturedQuery

    writes = int(total * WRITE_SHARE)
    selects = total - writes

    queries: list[CapturedQuery] = []
    fingerprints: set[str] = set()
    callsites: set[tuple[str, int]] = set()

    def add(sql: str, *, is_select: bool, group: int, tables: list[str]) -> None:
        callsite = CallSite(
            filepath="/app/myapp/views.py",
            line_number=100 + group,
            function_name=f"view_{group}",
            code_context="for row in qs:",
        )
        queries.append(
            CapturedQuery(
                sql=sql,
                params=None,
                duration_ms=0.4,
                fingerprint=fingerprint(sql),
                normalized_sql=normalize_sql(sql),
                callsite=callsite,
                is_select=is_select,
                tables=tables,
            )
        )
        fingerprints.add(queries[-1].fingerprint)
        callsites.add((callsite.filepath, callsite.line_number))

    for index in range(selects):
        group = index // SELECTS_PER_GROUP
        add(
            'SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_login", '
            '"auth_user"."is_superuser", "auth_user"."username", "auth_user"."first_name", '
            '"auth_user"."last_name", "auth_user"."email", "auth_user"."is_staff", '
            '"auth_user"."is_active", "auth_user"."date_joined" '
            f'FROM "auth_user" WHERE "auth_user"."id" = %s ORDER BY "auth_user"."username" '
            f"-- group {_group_token(group)}",
            is_select=True,
            group=group,
            tables=["auth_user"],
        )

    for _ in range(writes):
        add(
            'UPDATE "auth_user" SET "last_login" = %s WHERE "auth_user"."id" = %s',
            is_select=False,
            group=0,
            tables=[],
        )

    return queries, Shape(
        total=len(queries),
        selects=selects,
        writes=writes,
        fingerprints=len(fingerprints),
        callsites=len(callsites),
    )


def _group_token(index: int) -> str:
    """Render a group index as letters, e.g. 0 -> "a", 26 -> "ba".

    Numeric markers cannot be used to separate fingerprint groups: normalize_sql
    replaces numeric literals with a placeholder, so "group 0" and "group 1"
    collapse to the same normalized text and land in one group. Measured -- the
    first version of this harness reported two fingerprints at every query count
    for exactly that reason, which the printed shape column exposed.
    """
    token = ""
    remaining = index
    while True:
        token = chr(ord("a") + remaining % 26) + token
        remaining = remaining // 26 - 1
        if remaining < 0:
            return token


def _percentile(values: list[float], fraction: float) -> float:
    """Return the value at ``fraction`` through a sorted sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _time_analyze(count: int, repetitions: int, warmup: int) -> tuple[Stats, Shape, int]:
    """Time ``pipeline.analyze()`` over a workload of ``count`` captures.

    Warm-up calls are discarded: the first call populates the
    ``discover_analyzers()`` entry-point cache, which costs milliseconds of
    filesystem I/O once per process and would otherwise dominate the small counts
    exactly as it did before that cache existed.
    """
    from query_doctor.pipeline import analyze

    queries, shape = _build_workload(count)

    for _ in range(warmup):
        analyze(queries, source="bench_analyze")

    findings = len(analyze(queries, source="bench_analyze"))

    samples: list[float] = []
    for _ in range(repetitions):
        started = perf_counter()
        analyze(queries, source="bench_analyze")
        samples.append((perf_counter() - started) * 1000.0)

    return (
        Stats(
            queries=count,
            median=statistics.median(samples),
            p10=_percentile(samples, 0.10),
            p90=_percentile(samples, 0.90),
            fastest=min(samples),
            slowest=max(samples),
        ),
        shape,
        findings,
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.bench_analyze",
        description=(
            "Measure pipeline.analyze() cost per captured-query count. "
            "Regenerates the analysis-stage figures in docs/guides/async-support.md."
        ),
    )
    parser.add_argument(
        "--counts",
        type=int,
        nargs="+",
        default=list(DEFAULT_COUNTS),
        help=f"Query counts to measure (default: {' '.join(map(str, DEFAULT_COUNTS))}).",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=200,
        help="Timed calls per count (default: 200).",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="Discarded calls before timing, to warm the discovery cache (default: 5).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark and print a report."""
    args = _parse_args(argv)

    if args.repetitions < 1:
        print("error: --repetitions must be at least 1", file=sys.stderr)
        return 2

    _configure_django()

    from query_doctor.plugin_api import discover_analyzers

    analyzers = discover_analyzers()

    print("pipeline.analyze() -- analysis stage only, no reporters")
    print(f"python {sys.version.split()[0]} on {sys.platform}")

    import django

    print(f"django {django.get_version()}")
    print(f"analyzers enabled: {len(analyzers)} ({', '.join(sorted(a.name for a in analyzers))})")
    print(f"repetitions: {args.repetitions} timed, {args.warmup} discarded as warm-up")
    print(
        "no .queryignore present, so prescription filtering is skipped; "
        "a project with rules pays more"
    )
    print()

    rows: list[tuple[Stats, Shape, int]] = [
        _time_analyze(count, args.repetitions, args.warmup) for count in sorted(args.counts)
    ]

    header = (
        f"| {'queries':>7} | {'selects':>7} | {'writes':>6} | {'fprints':>7} | "
        f"{'sites':>5} | {'findings':>8} | {'median ms':>9} | {'p10 ms':>7} | "
        f"{'p90 ms':>7} | {'min ms':>7} | {'max ms':>7} |"
    )
    print(header)
    print(
        "|"
        + "|".join(
            [
                "-" * 9,
                "-" * 9,
                "-" * 8,
                "-" * 9,
                "-" * 7,
                "-" * 10,
                "-" * 11,
                "-" * 9,
                "-" * 9,
                "-" * 9,
                "-" * 9,
            ]
        )
        + "|"
    )
    for stats, shape, findings in rows:
        print(
            f"| {stats.queries:>7} | {shape.selects:>7} | {shape.writes:>6} | "
            f"{shape.fingerprints:>7} | {shape.callsites:>5} | {findings:>8} | "
            f"{stats.median:>9.3f} | {stats.p10:>7.3f} | {stats.p90:>7.3f} | "
            f"{stats.fastest:>7.3f} | {stats.slowest:>7.3f} |"
        )

    print()
    print(
        f"Workload shape: {int(WRITE_SHARE * 100)}% non-SELECT, "
        f"SELECTs spread over one fingerprint per {SELECTS_PER_GROUP} captures, "
        "one callsite per fingerprint group, callsites pre-attached."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
