"""Pytest plugin for django-query-doctor.

Provides a ``query_doctor`` fixture that captures SQL queries during a
test. The fixture is opt-in by usage: request it as a test argument and
capture runs for that test only.

NOTE: The returned DiagnosisReport is populated in a test *finalizer*,
i.e. after the test body has finished. Assertions on it inside the test
body see an empty report. For in-test assertions, use the
``diagnose_queries()`` context manager instead. The fixture emits a
QueryDoctorWarning at use for exactly this reason; suppress it with
``ignore::query_doctor.QueryDoctorWarning`` if you accept the behavior.

Observable output: each populated report is stashed on the session's
config and surfaced by ``pytest_terminal_summary`` at end of session.
The summary prints one header line plus one line per test that had
findings; tests with zero issues produce no line, so the section stays
proportionate to the problems found rather than to the number of tests
using the fixture.

Registration:
    The plugin is auto-discovered via the ``pytest11`` entry point
    defined in pyproject.toml.
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any

import pytest

from query_doctor.exceptions import QueryDoctorWarning

if TYPE_CHECKING:
    from _pytest.terminal import TerminalReporter

    from query_doctor.types import DiagnosisReport

logger = logging.getLogger("query_doctor")

# Per-session store mapping a test's nodeid to its populated DiagnosisReport.
# Lives on ``config.stash`` rather than a module global so state is owned by
# the session object (per project convention: no module-level mutable state),
# and is written by each fixture's finalizer, read once at terminal summary.
_REPORTS_KEY: pytest.StashKey[dict[str, DiagnosisReport]] = pytest.StashKey()


@pytest.fixture()
def query_doctor(request: pytest.FixtureRequest) -> DiagnosisReport:
    """Fixture that captures SQL queries during a test.

    Returns a DiagnosisReport that is populated in a test finalizer,
    i.e. AFTER the test body finishes. Assertions on it inside the test
    body see an empty report (they pass vacuously). For in-test
    assertions, use the diagnose_queries() context manager instead:

        from query_doctor.context_managers import diagnose_queries

        def test_optimized():
            with diagnose_queries() as report:
                list(Book.objects.select_related('author').all())
            assert report.issues == 0

    Emits QueryDoctorWarning at use (see module docstring). No integer
    stacklevel can point into the requesting test - the fixture is invoked
    from pytest's fixture machinery, not from the test's frame - so the
    warning embeds request.node.nodeid and uses stacklevel=2 to skip this
    plugin frame; pytest's warnings summary attributes it to the
    requesting test regardless.
    """
    from query_doctor.interceptor import build_interceptor
    from query_doctor.types import DiagnosisReport

    warnings.warn(
        f"query_doctor fixture ({request.node.nodeid}): the returned "
        "DiagnosisReport is empty until test teardown, so assertions on it "
        "inside the test body pass vacuously. For in-test assertions use "
        "the diagnose_queries() context manager instead "
        "(from query_doctor.context_managers import diagnose_queries). "
        "Suppress this warning with ignore::query_doctor.QueryDoctorWarning.",
        QueryDoctorWarning,
        stacklevel=2,
    )

    report = DiagnosisReport()
    interceptor = build_interceptor()

    try:
        from django.db import connection

        wrapper_ctx = connection.execute_wrapper(interceptor)
        wrapper_ctx.__enter__()

        def _finalize() -> None:
            """Finalize the report after the test completes."""
            try:
                wrapper_ctx.__exit__(None, None, None)
            except Exception:
                logger.warning(
                    "query_doctor: failed to exit execute_wrapper",
                    exc_info=True,
                )

            try:
                queries = interceptor.get_queries()
                report.captured_queries = queries
                report.total_queries = len(queries)
                report.total_time_ms = sum(q.duration_ms for q in queries)

                _run_analyzers(report, queries)
            except Exception:
                logger.warning(
                    "query_doctor: pytest fixture analysis failed",
                    exc_info=True,
                )

            # Stash the populated report so pytest_terminal_summary can surface
            # it; keyed by nodeid so each test contributes at most one entry.
            try:
                registry = request.config.stash.setdefault(_REPORTS_KEY, {})
                registry[request.node.nodeid] = report
            except Exception:
                logger.warning(
                    "query_doctor: failed to stash fixture report",
                    exc_info=True,
                )

        request.addfinalizer(_finalize)
    except Exception:
        logger.warning(
            "query_doctor: failed to set up pytest fixture",
            exc_info=True,
        )

    return report


def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Print a proportionate summary of fixture reports at end of session.

    Reads the reports stashed by each ``query_doctor`` fixture use and emits a
    single header line followed by one line per test that had findings. Tests
    with zero issues produce no line, so the section scales with the number of
    problems, not the number of tests using the fixture. Emits nothing when the
    fixture was not used.

    Args:
        terminalreporter: pytest's terminal reporter, used to write output.
        exitstatus: The session exit status (unused; part of the hook spec).
        config: The session config carrying the stashed reports.
    """
    reports = config.stash.get(_REPORTS_KEY, {})
    if not reports:
        return

    with_findings = {nodeid: r for nodeid, r in reports.items() if r.issues}
    observed = len(reports)
    clean = observed - len(with_findings)

    terminalreporter.write_sep("=", "query_doctor")
    terminalreporter.write_line(
        f"observed {observed} test(s); {clean} clean, {len(with_findings)} with findings"
    )
    for nodeid, report in with_findings.items():
        terminalreporter.write_line(
            f"  {nodeid}: {report.total_queries} queries, {report.issues} issue(s)"
        )


def _run_analyzers(report: DiagnosisReport, queries: list[Any]) -> None:
    """Run all enabled analyzers on the captured queries.

    Args:
        report: The report to populate with prescriptions.
        queries: The captured queries to analyze.
    """
    from query_doctor.pipeline import analyze as pipeline_analyze

    report.prescriptions.extend(pipeline_analyze(queries, source="pytest_plugin"))
