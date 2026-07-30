"""Smoke tests for the analysis-cost benchmark harness.

``scripts/bench_analyze.py`` is the sole thing standing behind the timing
figures published in ``docs/guides/async-support.md``. It is not a CI timing
gate -- timings on a shared runner are noisy -- but it does need to still run:
a signature change in ``pipeline.analyze()`` or a renamed ``CapturedQuery``
field would leave it unrunnable, and the published figures unregenerable, which
is the defect the harness was added to close.

So these tests assert that the harness executes end to end and reports the
shape it claims, at counts small enough to add no meaningful runtime. They
assert nothing about how long anything took.

The harness runs here under ``tests.settings``, so ``settings.configured`` is
already true and the ``settings.configure()`` branch of ``_configure_django()``
stays uncovered. That is the point of the branch: it exists for the standalone
``python -m scripts.bench_analyze`` invocation, which has no settings module.
"""

from __future__ import annotations

import pytest

from query_doctor import ignore
from scripts import bench_analyze

SMOKE_ARGS = ["--counts", "1", "--repetitions", "1", "--warmup", "0"]


class TestMain:
    """End-to-end runs of the command-line entry point."""

    @pytest.mark.parametrize("width", ["wide", "narrow"])
    def test_runs_and_reports_both_widths(
        self, capsys: pytest.CaptureFixture[str], width: str
    ) -> None:
        """Both SELECT widths run to completion and print a row plus a breakdown."""
        assert bench_analyze.main([*SMOKE_ARGS, "--select-width", width]) == 0

        output = capsys.readouterr().out
        assert f"{width} SELECTs" in output
        assert "per-analyzer at 1 captures" in output
        assert "pipeline total" in output

    def test_reports_the_queryignore_rule_count_it_measured(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The .queryignore disclosure is measured, not printed unconditionally.

        ``pipeline.analyze()`` calls ``load_queryignore()`` on every invocation,
        so a run inside a project that has rules is paying for filtering. An
        earlier version of the harness stated "no .queryignore present" whatever
        was on disk, which such a run would have made a false disclosure. Both
        cases are exercised: rules present must not print the empty wording.
        """
        rules = [
            ignore.IgnoreRule(rule_type="ignore", pattern="n_plus_one:app/views.py"),
            ignore.IgnoreRule(rule_type="file", pattern="app/legacy.py"),
        ]
        monkeypatch.setattr(ignore, "load_queryignore", lambda *a, **k: rules)

        assert bench_analyze.main(SMOKE_ARGS) == 0

        output = capsys.readouterr().out
        assert ".queryignore rules loaded: 2" in output
        assert "prescription filtering runs" in output
        assert "skipped" not in output

    def test_reports_zero_rules_when_none_are_loaded(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive control for the case above: no rules reports 0, not 2."""
        monkeypatch.setattr(ignore, "load_queryignore", lambda *a, **k: [])

        assert bench_analyze.main(SMOKE_ARGS) == 0

        output = capsys.readouterr().out
        assert ".queryignore rules loaded: 0" in output
        assert "prescription filtering is skipped" in output

    def test_per_analyzer_breakdown_can_be_turned_off(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``--no-per-analyzer`` skips the breakdown and still reports the table."""
        assert bench_analyze.main([*SMOKE_ARGS, "--no-per-analyzer"]) == 0

        output = capsys.readouterr().out
        assert "per-analyzer" not in output
        assert "Workload shape:" in output

    def test_rejects_zero_repetitions(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A run with nothing to time exits non-zero rather than dividing by nothing."""
        assert bench_analyze.main(["--counts", "1", "--repetitions", "0"]) == 2
        assert "--repetitions must be at least 1" in capsys.readouterr().err


class TestWorkload:
    """The generated workload, whose shape the published figures depend on."""

    def test_width_changes_sql_length_but_not_grouping(self) -> None:
        """Narrow and wide differ in SQL size only, so a timing delta is attributable."""
        wide, wide_shape = bench_analyze._build_workload(100, "wide")
        narrow, narrow_shape = bench_analyze._build_workload(100, "narrow")

        assert wide_shape == narrow_shape
        assert len(wide[0].sql) > 3 * len(narrow[0].sql)

    def test_group_tokens_keep_fingerprints_distinct(self) -> None:
        """Letter markers survive normalization where numeric ones would collapse.

        ``normalize_sql`` replaces numeric literals, so "group 0" and "group 1"
        would land in one fingerprint group and the shape column would report
        two groups at every count.
        """
        _, shape = bench_analyze._build_workload(500, "wide")

        assert shape.fingerprints == 16
