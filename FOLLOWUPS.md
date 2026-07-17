# Follow-ups

Entries 1-12 came out of the 2.1.0 documentation remediation (PR #7). None of
those are regressions introduced by that work — all are pre-existing
conditions the audit surfaced. Entries 5, 6, and 10 were found by the final
directed checks, and entry 12 by the post-review pass, i.e. the audit was
still finding items on its last passes; treat this list as a floor, not a
ceiling. Entries 13-15 were surfaced during the 2.1.1 follow-up work
(2026-07-16): 13 by the stream-encoding investigation, 14 by the fixture
analysis (filed alongside the 2.1.1 fixture change), 15 by the review of
the Rich-path test corrections. Entry 16 was surfaced by the 2.1.1
version-bump sweep (2026-07-17).

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
- **Resolved:** 2.1.1 - `QueryDoctorWarning` (new public category,
  `exceptions.py`, exported from `__init__`) emitted at fixture use
  (`pytest_plugin.py:61`), naming the vacuous-pass failure mode, embedding
  the requesting test's nodeid, and steering to `diagnose_queries()`;
  suppressible via `ignore::query_doctor.QueryDoctorWarning`. Also in
  2.1.1: `docs/guides/ci-integration.md` prescribed the exact pattern the
  warning flags (in-test assertions on the fixture object) and claimed
  those assertions gate CI; the sample was removed in favour of the pytest
  guide's `diagnose_queries()` patterns, so the warning and the shipped
  docs now steer the same direction. The deprecation question continues as
  entry 14.

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
- **Additional finding (2.1.1 work, 2026-07-16):** the skip guard is not
  the only gap. `tests/test_coverage_gaps.py::TestConsoleReporterRich`
  (tests at `:81`, `:88`, `:117`) goes through the public `render()`, which
  swallows `ImportError` and falls back (`reporters/console.py:49-52`);
  with `rich` absent the three tests pass vacuously against
  `_render_plain`, asserting only strings both renderers emit. Unlike the
  four skipping tests, these emit no CI signal at all. The fourth test in
  the class (`:138`, `test_plain_fallback_when_rich_unavailable`) patches
  `_render_rich` to raise and is correct.
- **Disposition (decided 2026-07-16, shipping in 2.1.1):**
  1. `rich` goes into the `dev` extra so CI executes the four direct
     `_render_rich` tests (the skip disappears) and `render()` exercises
     the Rich path.
  2. The three `render()` tests are renamed to state what they cover
     (content common to both renderers), and a distinguishing test is
     added: with rich importable, `render(report) != _render_plain(report)`
     - `_render_plain` emits the `"=" * 60` header
     (`reporters/console.py:156,163`); `_render_rich` renders a Panel and
     never does, on both the ASCII-box and unicode-box branches.
  3. `box=box.ASCII` is **declined**, not deferred: no shipped document
     claims ASCII console output (every ASCII claim in shipped docs is
     `UPGRADING.md:120-147`, about bytes written into user source files),
     and Rich's `safe_box` already degrades to ASCII on terminals that
     cannot render box-drawing, so pinning ASCII would only degrade the
     terminals that can. Decided: keep Rich's default box behavior;
     `safe_box` owns platform degradation.

  Note for whoever revisits box behavior: on a legacy-Windows dev session
  (`legacy_windows=True`, cp1252) `_render_rich` emits zero non-ASCII, so
  a box-drawing assertion is GREEN there for platform reasons; a
  deterministic RED requires monkeypatching `rich.console.Console` with a
  real subclass forcing `legacy_windows=False` and a utf-8 encoding (a
  lambda or partial breaks the `isinstance` check at
  `reporters/console.py:129`). The encoding-divergence question this
  investigation surfaced is filed as entry 13.
- Pre-existing condition surfaced by PR #7's review, not a regression -
  the Rich path has always behaved this way.
- **Resolved (partial):** 2.1.1 - closed: `rich` added to the `dev` extra, CI now
  exercises the Rich path on utf-8, and the ImportError→skip guards are deleted
  from the four direct tests, so a future loss of rich fails loudly instead of
  skipping; `test_ascii_output.py` extension moot by the box=box.ASCII decline.
  Open: CI is ubuntu-only (`ci.yml:11,45,59`), so the legacy-Windows/cp1252
  substitution branch is still exercised by no CI run.

## 13. ConsoleReporter probes stdout but writes to a different stream

- **Evidence:** `reporters/console.py:37` sets the destination
  (`stream or sys.stderr`); `console.py:102` builds
  `Console(file=None, force_terminal=False)`, whose encoding and
  legacy-Windows detection probe **stdout**; `console.py:63` prints the
  captured string to the **destination**. The renderer decides
  Unicode-vs-ASCII from one stream and writes to a different one.
  Repro (2026-07-16, rich 15.0.0, in-process;
  `rich.console.detect_legacy_windows` patched to return `False` to
  simulate the non-legacy branch - the piped dev session genuinely detects
  legacy Windows - with stdout replaced by a utf-8 wrapper):
  - sanity: `_render_rich` emits U+2500, U+2502, U+256D-U+2570;
  - destination `TextIOWrapper(..., encoding='cp1252')` (strict errors -
    the shape of `open('report.txt', 'w')` on a cp1252 locale):
    `report()` raises `UnicodeEncodeError: 'charmap' codec can't encode
    characters in position 0-32`;
  - destination cp1252 with `errors='backslashreplace'` (CPython's
    unconditional default for `sys.stderr`): no raise; the stream receives
    the literal text `\u256d\u2500...` in place of the box drawing. The
    escape text is the observed artifact - it is what
    `errors='backslashreplace'` writes to the stream - and it is
    recorded verbatim here because rendering it as box characters would
    document the opposite of the finding.
- **Impact:** the default path can never raise - `sys.stderr` is
  `backslashreplace` - so divergent stream encodings garble the report
  (mojibake) rather than crash it. A crash needs an API user passing their
  own strict non-utf8 stream (the constructor documents accepting "any
  writable stream", `reporters/console.py:32-33`) while stdout probes
  utf-8/non-legacy. Shipped constructors do not diverge: `middleware.py:47`
  uses the default; `management/commands/check_queries.py:225` and
  `management/commands/check_serializers.py:176` pass
  `OutputWrapper(sys.stdout)` - the same underlying stream the Console
  probes. Latent through 2.0.0 and 2.1.0; not a regression.
- **Disposition:** ruled out of 2.1.1 (2026-07-16) - latent for two
  releases, nothing shipped constructs the crashing stream, and the 2.1.1
  PR already carries enough behavior change. Candidate fix:
  `Console(file=self._stream)` - probe the stream actually written to;
  with one stream the encodings cannot disagree, and `safe_box` resolves
  the box choice automatically. (`box=box.ASCII` would have masked this
  bug by making output unconditionally encodable - a green light for the
  wrong reason.) Verified on Django 6.0.7/Linux: the candidate is safe
  with Django's `OutputWrapper` - its MRO is `['OutputWrapper', 'object']`
  (nothing shadows), it defines no `encoding` (`__getattr__` delegates),
  `w.encoding == sys.stdout.encoding == 'utf-8'`, `w.isatty()` matches
  `sys.stdout.isatty()`, `w.fileno() == 1`. **Open question:** the package
  supports `django>=4.2`; whether `OutputWrapper.isatty` and the
  `__getattr__` encoding delegation hold across 4.2-5.x is unverified - a
  CI-matrix question, part of why this is not a one-line change.

## 14. `query_doctor` fixture has zero observable effect - deprecation case for 2.2

- **Evidence:** `src/query_doctor/pytest_plugin.py:81-104` - the finalizer
  populates the report and runs analyzers after the test body, and nothing
  consumes the result: no hook prints it, no summary line is emitted, and
  user code cannot read it after teardown (finalizers run LIFO - the
  fixture's own finalizer, registered during setup at `:104`, runs after
  any finalizer or fixture teardown the test could register later, so no
  user code observes the populated report). Found 2026-07-16 during the
  2.1.1 fixture work.
- **Impact:** every use of the fixture is either vacuous (in-test reads
  see the empty report - entry 1) or invisible (the populated report is
  discarded unread). The 2.1.1 `QueryDoctorWarning` makes the vacuous half
  audible; it does not give the fixture a purpose.
- **Disposition:** argue deprecation for 2.2 - a warning is a signpost on
  a road that likely should be closed. If a real in-test use case is
  wanted instead, the report must be wired somewhere observable (e.g. a
  pytest terminal-summary hook). Decision deferred to 2.2 planning; 2.1.1
  ships the warning only (entry 1).

## 15. Unfalsifiable assertion in a direct Rich-path test

- **Evidence:** `tests/test_console_reporter.py:352`
  (`test_rich_empty_report`, def at `:347`): `assert "No issues" in
  output or "0" in output`, run against
  `DiagnosisReport(total_queries=0, total_time_ms=0.0)`. The rendered
  header always contains a `0` ("Total queries: 0", "Time: 0.0ms"), so
  the `or` branch is unconditionally true and the assertion cannot fail.
  The other three direct Rich tests were checked for the same shape and
  are falsifiable: `test_rich_renders_nonempty_string` (`:320`) asserts
  prescription content ("author"), `test_rich_warning_severity` (`:354`)
  and `test_rich_info_severity` (`:374`) assert severity labels a broken
  renderer would drop. One instance, not four.
- **Impact:** the empty-report branch of `_render_rich`
  (`reporters/console.py:119-120`, the green "No issues detected." line)
  is effectively untested - the test passes whether or not that line
  renders.
- **Disposition:** 2.2 - strengthen the assertion to the actual marker
  (`"No issues detected"`), or delete the test as redundant with
  `test_render_empty_report_content` (`tests/test_coverage_gaps.py`).
  Out of scope for 2.1.1: correctness-only release, not a test refactor.

## 16. Version is declared in two places with no cross-check

- **Evidence:** `pyproject.toml:7` declares `version = "2.1.0"` statically;
  `src/query_doctor/__init__.py:18` declares `__version__ = "2.1.0"`
  statically. There is no `[tool.hatch.version]` and no `dynamic = ["version"]`
  - `pyproject.toml` carries only `[tool.hatch.build.targets.sdist]` (`:72`)
  and `[tool.hatch.build.targets.wheel]` (`:78`), so hatchling reads the
  version from `[project]` and nothing derives one declaration from the
  other. `tests/test_public_api.py:69` pins `__init__` to a hardcoded literal
  and never compares it to the distribution metadata (`importlib.metadata`
  appears nowhere in the test suite).
- **Impact:** the two can disagree silently. Distribution metadata (what
  `pip show` and PyPI report) comes from `pyproject.toml`; the runtime
  `__version__` comes from `__init__.py`. `baseline.py:115` stamps every
  saved baseline with `__version__`, and `check_queries.py:265` compares
  `baseline.version != __version__` to warn that analyzer coverage may
  differ - so a disagreement mislabels baselines relative to the installed
  distribution, and `test_public_api.py:69` cannot catch it because it only
  ever checks `__init__` against a hardcoded string. Release discipline is
  the only guard, and it is manual.
- **Disposition:** 2.2. Either single-source it (`dynamic = ["version"]`
  plus `[tool.hatch.version]` with `path = "src/query_doctor/__init__.py"`),
  or make the test an actual cross-check:
  `assert query_doctor.__version__ == importlib.metadata.version("django-query-doctor")`,
  which fails when the two drift regardless of which is authoritative. Out
  of scope for 2.1.1: this changes how the artifact is built, and a
  correctness-only patch release is the wrong place to change the build on
  the eve of publish.
