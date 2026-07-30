"""Measure ``pipeline.analyze()`` cost against captured-query count.

Regenerates the analysis-stage figures quoted in
``docs/guides/async-support.md``. Run on demand; this is not a CI gate, because
timings on a shared runner are noisy and a flaky required check is worse than an
unsourced figure.

    python -m scripts.bench_analyze
    python -m scripts.bench_analyze --select-width narrow

Why the workload shape is printed rather than described in prose: every grouping
analyzer is O(distinct fingerprints), not O(queries), and ``write_nplusone``
inspects only non-SELECT captures. So the same "500 queries" can differ by an
order of magnitude depending on how many fingerprints it spans and how many of
those queries are writes. A figure quoted without that shape cannot be
reproduced, which is how the previous generation of these numbers went stale
unnoticed.

Every claim the guide makes about this workload is a knob here, for the same
reason. ``--select-width`` varies SELECT width with count and fingerprint spread
held fixed, which is the wide-versus-narrow ratio; the per-analyzer breakdown
attributes the pipeline total across the eight analyzers, which is the
"complexity dominates" claim. A published number whose knob is missing is a
number nobody can check.

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

# The two SELECT shapes, differing only in projected column count. Everything
# that governs grouping -- the table, the WHERE, the trailing group marker -- is
# identical, so switching width holds the fingerprint spread fixed and varies
# only how much SQL each analyzer has to parse.
SELECT_TEMPLATES = {
    "wide": (
        'SELECT "auth_user"."id", "auth_user"."password", "auth_user"."last_login", '
        '"auth_user"."is_superuser", "auth_user"."username", "auth_user"."first_name", '
        '"auth_user"."last_name", "auth_user"."email", "auth_user"."is_staff", '
        '"auth_user"."is_active", "auth_user"."date_joined" '
        'FROM "auth_user" WHERE "auth_user"."id" = %s ORDER BY "auth_user"."username" '
        "-- group {token}"
    ),
    "narrow": (
        'SELECT "auth_user"."id" FROM "auth_user" WHERE "auth_user"."id" = %s -- group {token}'
    ),
}


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


def _build_workload(total: int, select_width: str = "wide") -> tuple[list[CapturedQuery], Shape]:
    """Build ``total`` synthetic captures with a documented, fixed composition.

    SELECTs are spread over several fingerprints at ``SELECTS_PER_GROUP`` each so
    the grouping analyzers produce real findings; writes share one fingerprint,
    which is the shape a ``.save()`` loop actually produces. Callsites are
    pre-attached, so the harness measures analysis only and never exercises stack
    capture.

    Args:
        total: Number of captures to generate.
        select_width: Key into :data:`SELECT_TEMPLATES`. Only the projected
            column list differs between the two, so the shape columns this
            returns are identical either way and the timing difference is
            attributable to SQL width alone.
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

    template = SELECT_TEMPLATES[select_width]
    for index in range(selects):
        group = index // SELECTS_PER_GROUP
        add(
            template.format(token=_group_token(group)),
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


def _time_analyze(
    count: int, repetitions: int, warmup: int, select_width: str
) -> tuple[Stats, Shape, int]:
    """Time ``pipeline.analyze()`` over a workload of ``count`` captures.

    Warm-up calls are discarded: the first call populates the
    ``discover_analyzers()`` entry-point cache, which costs milliseconds of
    filesystem I/O once per process and would otherwise dominate the small counts
    exactly as it did before that cache existed.
    """
    from query_doctor.pipeline import analyze

    queries, shape = _build_workload(count, select_width)

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


def _time_per_analyzer(
    count: int, repetitions: int, warmup: int, select_width: str
) -> tuple[list[tuple[str, float]], float]:
    """Time each analyzer separately over one workload, alongside the pipeline.

    The parts do not sum to the whole, and both are printed so the gap is
    visible rather than asserted. ``pipeline.analyze()`` additionally pays
    ``discover_analyzers()`` dispatch and one ``load_queryignore()`` call per
    invocation, neither of which is attributable to any analyzer.

    Every analyzer self-gates in its own ``analyze()``, so a disabled one is
    timed exactly as the pipeline pays for it: near zero, but not skipped.

    Returns:
        Per-analyzer medians in milliseconds, sorted slowest first, and the
        median of the whole ``pipeline.analyze()`` call over the same workload.
    """
    from query_doctor.pipeline import analyze
    from query_doctor.plugin_api import discover_analyzers

    queries, _ = _build_workload(count, select_width)
    analyzers = discover_analyzers()

    for _ in range(warmup):
        analyze(queries, source="bench_analyze")

    samples: dict[str, list[float]] = {analyzer.name: [] for analyzer in analyzers}
    pipeline_samples: list[float] = []
    for _ in range(repetitions):
        for analyzer in analyzers:
            started = perf_counter()
            analyzer.analyze(queries)
            samples[analyzer.name].append((perf_counter() - started) * 1000.0)
        started = perf_counter()
        analyze(queries, source="bench_analyze")
        pipeline_samples.append((perf_counter() - started) * 1000.0)

    medians = [(name, statistics.median(values)) for name, values in samples.items()]
    medians.sort(key=lambda item: item[1], reverse=True)
    return medians, statistics.median(pipeline_samples)


def _print_breakdown(count: int, repetitions: int, warmup: int, select_width: str) -> None:
    """Print the per-analyzer attribution of the pipeline total at ``count``."""
    medians, pipeline_median = _time_per_analyzer(count, repetitions, warmup, select_width)
    analyzers_total = sum(value for _, value in medians)

    print()
    print(f"per-analyzer at {count} captures, {select_width} SELECTs (median ms per call)")
    for name, value in medians:
        share = (value / pipeline_median * 100.0) if pipeline_median else 0.0
        print(f"  {name:<20} {value:>9.3f} ms  {share:>5.1f}% of pipeline")
    print(f"  {'analyzers total':<20} {analyzers_total:>9.3f} ms")
    print(f"  {'pipeline total':<20} {pipeline_median:>9.3f} ms")
    print(
        f"  {'unattributed':<20} {pipeline_median - analyzers_total:>9.3f} ms  "
        "(discovery dispatch and load_queryignore, paid once per call)"
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
    parser.add_argument(
        "--select-width",
        choices=sorted(SELECT_TEMPLATES),
        default="wide",
        help=(
            "SELECT shape: 'wide' projects all 11 auth_user columns with an ORDER BY, "
            "'narrow' projects one column. Count and fingerprint spread are identical "
            "either way (default: wide)."
        ),
    )
    parser.add_argument(
        "--per-analyzer",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Also time each analyzer separately at the largest count, "
            "against the pipeline total (default: enabled)."
        ),
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

    from query_doctor.ignore import load_queryignore

    # Measured, not asserted: pipeline.analyze() calls load_queryignore() on
    # every invocation, and filter_prescriptions() only when it returns rules.
    # Printing the count means a run inside a project that has a .queryignore
    # discloses the cost it is paying instead of denying it.
    rule_count = len(load_queryignore())
    filtering = (
        "prescription filtering runs" if rule_count else "prescription filtering is skipped"
    )
    print(
        f".queryignore rules loaded: {rule_count} ({filtering}; "
        "the file is looked up on every analyze() call either way)"
    )
    print()

    rows: list[tuple[Stats, Shape, int]] = [
        _time_analyze(count, args.repetitions, args.warmup, args.select_width)
        for count in sorted(args.counts)
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
        f"{args.select_width} SELECTs spread over one fingerprint per "
        f"{SELECTS_PER_GROUP} captures, one callsite per fingerprint group, "
        "callsites pre-attached."
    )

    if args.per_analyzer and args.counts:
        _print_breakdown(max(args.counts), args.repetitions, args.warmup, args.select_width)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
