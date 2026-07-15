# Follow-ups

This list came out of the 2.1.0 documentation remediation (PR #7). None of
these are regressions introduced by that work — all are pre-existing
conditions the audit surfaced. Entries 5, 6, and 10 were found by the final
directed checks, and entry 12 by the post-review pass, i.e. the audit was
still finding items on its last passes; treat this list as a floor, not a
ceiling.

Each entry: evidence, current user-visible impact, proposed disposition.

---

## 1. Inert `query_doctor` pytest fixture

- **Evidence:** `src/query_doctor/pytest_plugin.py:70-93` — the report is
  populated in an `addfinalizer` callback, i.e. after the test body
  finishes. Verified empirically: in-test reads see `total_queries == 0`,
  `issues == 0`.
- **Impact:** in-test assertions on the fixture pass vacuously — false
  confidence. Docs, examples, and the comparison matrix now say "Fixture
  only" and steer users to `diagnose_queries()`, but the code still ships
  the footgun with no runtime signal.
- **Disposition:** runtime `UserWarning`/deprecation at fixture use,
  scoped as a **fast-follow before the r/django announcement** — a warning
  at the point of use is the only signal that reaches users who don't read
  the docs. Behavior change, so it gets its own TDD commit.

## 2. `OTelReporter` / `HTMLReporter` unreachable via settings

- **Evidence:** `src/query_doctor/middleware.py:44-52` dispatches only
  `"console"`, `"json"`, `"log"`. `OTelReporter`
  (`reporters/otel_exporter.py:34`) and `HTMLReporter`
  (`reporters/html_reporter.py:29`) are invocable manually only.
- **Impact:** `REPORTERS: ["otel"]`-style config silently does nothing.
- **Disposition:** wire the names into the dispatch, or delete the classes.
  Docs are already truthful about the manual-invocation reality.

## 3. Dead config keys in `DEFAULT_CONFIG`

- **Evidence:** `src/query_doctor/conf.py:18` (`STACK_TRACE_EXCLUDE`),
  `:29` (`IGNORE_PATTERNS`), `:33` (`QUERYIGNORE_PATH`) — read by no code
  path. `ADMIN_DASHBOARD.max_reports` (`conf.py:32`) vs the hardcoded
  `MAX_REPORTS = 50` (`admin_panel.py:22`).
- **Impact:** setting any of them silently has no effect.
- **Disposition:** implement each key or remove it from the defaults.

## 4. `.queryignore` dispatch trap

- **Evidence:** rules applied only at `middleware.py:210-214` and
  `management/commands/fix_queries.py:164-168`; `check_queries` and
  `diagnose_project` never load them.
- **Impact:** findings suppressed in dev (middleware) reappear in CI
  commands.
- **Disposition:** wire `ignore.filter_prescriptions` into both commands.

## 5. Admin dashboard project-scan integration is dead code

- **Evidence:** `record_project_report` (`admin_panel.py:67`) has no caller
  in v1.0.0, v2.0.0, or the current tree; `_latest_project_report`
  (`admin_panel.py:25`) is written by nothing;
  `templates/query_doctor/dashboard.html` never renders project-report
  data (the `project_report` context key set at `admin_panel.py:119` is
  unused by the template).
- **Impact:** the feature advertised in the `[1.0.0]` changelog entry
  ("admin dashboard integration showing latest project scan results") has
  never worked in any release. (Distinct from #2 — different code,
  different fix. The dashboard view itself and `diagnose_project --format
  html` are live.)
- **Disposition:** wire it into `diagnose_project`, or delete the function,
  its global, and the context key.

## 6. `should_ignore_query` has no caller

- **Evidence:** `src/query_doctor/ignore.py:62-88`; nothing in the pipeline
  invokes it.
- **Impact:** it is the only implementation of per-query `.queryignore`
  matching (including `sql:` rules against raw SQL); without a caller,
  `sql:` rules only ever match prescription descriptions
  (`ignore.py:149-153`) — already documented in the query-ignore guide.
- **Disposition:** call it during capture/analysis, or delete it.

## 7. False source docstrings — audit method

- **Evidence:** three false docstrings fixed in PR #7
  (`pytest_plugin.py` module docstring, `reporters/otel_exporter.py`,
  `celery_integration.py`), plus the `query_doctor` fixture's own docstring
  found only on a later pass — after two earlier sweeps reported clean.
- **Impact:** docstrings are documentation surfaces; read-through audits
  demonstrably miss them.
- **Disposition:** any future docstring audit should be programmatic — AST
  walk over every module/class/function docstring, claims checked the same
  way doc pages are.

## 8. SVG line data is hand-authored transcription

- **Evidence:** `examples/generate_svgs.py` carries terminal text
  transcribed from `examples/screenshots/*.capture.txt` (which
  `scripts/regen_examples.py` regenerates from real runs). Nothing enforces
  that the script's line data matches the captures, and
  `scripts/docs_truth_sweep.py` does not parse SVGs.
- **Impact:** the SVGs can silently drift from real output on the next
  format change.
- **Disposition:** add a check comparing capture text to the script's line
  data, or generate the SVG line data from the captures directly.

## 9. Truth-sweep discovery gap (repo-root markdown ungated)

- **Evidence:** `scripts/docs_truth_sweep.py:155` discovers `docs/**/*.md`
  plus `README.md` only; `CHANGELOG.md`, `UPGRADING.md`, and
  `CONTRIBUTING.md` are outside the gate.
- **Impact:** the release-critical upgrade/changelog docs get no automated
  token verification. Measured cost of closing it (review re-run with
  discovery repointed): exactly **2 violations, both legitimate historical
  `field_count_threshold` -> `threshold` references**.
- **Disposition:** extend discovery with an explicit repo-root file list
  (NOT a glob — a glob pulls in gitignored CLAUDE.md/SPEC.md/scratch
  files) plus a two-entry inline allowlist, one comment per historical
  token.

## 10. Programmatic no-caller sweep results (run 2026-07-15)

AST enumeration of all 93 public module-level symbols in
`src/query_doctor/`, cross-referenced for in-src usage: 11 symbols have
zero in-src references. Classification:

- **Already tracked above:** `record_project_report` (#5),
  `should_ignore_query` (#6), `HTMLReporter` (#2).
- **Never-raised exception classes:** `ConfigError` (`exceptions.py:19`),
  `AnalyzerError` (`exceptions.py:23`), `InterceptorError`
  (`exceptions.py:27`). Public API surface no code path can produce; not
  exported from `__init__.py`; not referenced in any doc. Disposition:
  raise them where they belong or remove them.
- **Deprecated shim:** `set_thread_override` (`turbo/patch.py:102`,
  docstring points to `context.set_turbo_override`). Disposition: schedule
  removal.
- **Alive by convention — no action:** `QueryDoctorConfig` (`apps.py:16`,
  Django AppConfig loaded via `INSTALLED_APPS`);
  `format_github_annotations` / `generate_pr_comment` /
  `write_json_report` (`ci/github.py:16,38,73` — user-facing CI helpers
  documented in UPGRADING.md).

## 11. Pre-push hook integrity is PATH-dependent

- **Evidence:** `.pre-commit-config.yaml` — every pre-push entry
  (including `pytest`) is `language: system`, so the executable resolves
  from `PATH`, not the project venv. During PR #7 this failed loudly (a
  broken Python 3.11 shim exiting 1 with no output), which was
  recoverable.
- **Impact:** the same mechanism can fail QUIETLY — a system Python with a
  partial dependency set could run a subset of the suite and exit 0,
  producing a green gate that proves nothing. The per-commit green-bar
  discipline rests on this hook resolving correctly, and nothing pins it.
- **Disposition:** pin the interpreter in the hook config, or move the
  entries off `language: system`. Pre-existing condition surfaced by this
  PR, not a regression.

## 12. Rich console path is unverified in CI and by the ASCII test

- **Evidence:** `rich` is not in the `dev` extra (`pyproject.toml:48-59`)
  and CI installs `pip install -e ".[dev]"`
  (`.github/workflows/ci.yml:33,66`), so the four Rich-gated tests in
  `tests/test_console_reporter.py` (tests at `:322,352,362,385`, each with
  a `try/except ImportError -> pytest.skip` guard) skip on every CI run
  and have never executed there. `tests/test_ascii_output.py:115` asserts
  ASCII-cleanliness against `ConsoleReporter()._render_plain` only.
  `ConsoleReporter._render_rich` (`console.py:96-117`) renders through
  `rich.panel.Panel` (`:114`).
- **Impact:** the "ASCII-only output surfaces" guarantee from the 2.1.0
  remediation is verified for the plain renderer only. The Rich renderer
  is the DEFAULT path whenever `rich` is installed (a documented extra,
  included in `[all]`), and it is untested for ASCII and unexercised by
  CI. Its output is platform-dependent - verified as a matched pair on
  rich 15.0.0 with `Console(file=None, force_terminal=False)`:
  - Linux/UTF-8 session (`legacy_windows=False`, `encoding=utf-8`,
    `safe_box=True`, `is_terminal=False`): `_render_rich` emits Unicode
    box-drawing (U+2500, U+2502, U+256D-U+2570).
  - Legacy-Windows session (`legacy_windows=True`, `encoding=cp1252`,
    `safe_box=True`, `is_terminal=False`): the same call emits pure ASCII
    (`legacy_windows=True` triggers Rich's box substitution).

  Because Rich substitutes ASCII exactly on the platform at risk of
  `UnicodeEncodeError` (legacy Windows/cp1252), no crash scenario is
  claimed. The backed finding is the smaller problem: console output
  silently differs by platform, and CI exercises NEITHER branch, so a
  regression on the default (Rich) path cannot be caught.
- **Disposition** (deliberately not implemented in this recording commit):
  add `rich` to the `dev` extra so CI runs the four Rich tests; extend
  `test_ascii_output.py` to cover `_render_rich` (expect RED in
  box-drawing environments); then decide deliberately whether Unicode
  box-drawing is acceptable console output or the Panel should use
  `box=box.ASCII` - given Rich's own downgrade behavior, that is a design
  choice about output consistency, not a crash fix. Pair with the entry-1
  fixture warning as a fast-follow before the r/django announcement -
  both are small.
- Pre-existing condition surfaced by PR #7's review, not a regression -
  the Rich path has always behaved this way.
