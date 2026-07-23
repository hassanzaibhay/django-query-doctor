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
version-bump sweep (2026-07-17). Entries 17-21 came out of the 2.1.2 ASGI
work (2026-07-22): 17 and 19 from the middleware rewrite, 18 from the docs
sweep, 20 from the middleware-chain matrix, 21 from the claim-by-claim
disposition of the async-support guide, and 22 by the directed measurement
of the one claim that disposition initially skipped. Entries 23-24 came out of
the PR #12 review pass (2026-07-22); 23 duplicated 11 and has been merged into
it, leaving a tombstone at its number. Entry 26 came out of S9a (2026-07-22),
from checking whether the coverage badge could be made dynamic; 25 is reserved
for the phase-1 branch disposition and is not yet written.

Each entry: evidence, current user-visible impact, proposed disposition.

**Admission rule (from S9a.1):** an entry may be added only if it is closable
within 2.2.0, or it carries a named destination for S13. S13 deletes this file;
every surviving entry becomes a GitHub issue or is closed with a recorded
reason.

Every gate built in this release carries a rule governing what enters it; this
file was the only artifact that did not. The count below makes "the backlog is
shrinking" a measured claim rather than an asserted one -- it is checked by
`scripts/claims_check.py` (row `followups-open-count`), which counts headings,
minus tombstones, minus entries carrying a `- **Resolved:**` line.
`- **Resolved (partial):**` does not count as resolved, and a reserved number
with no heading (25) cannot inflate it.

**Open entries: 19**

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
- **Resolved:** 2.2.0 - **ratified (R3), neither wired nor deleted**, and the
  actual defect fixed separately (R4). Under the S3 wire-versus-delete rule
  (recorded in entry 3), both classes are *duplicate paths*: each is already
  reachable by a supported, documented route, so a second route via
  `REPORTERS` would be two mechanisms for one job.
  The premise this entry shares with entry 19 - "shipped code with no
  reachable caller" - is **false for these two**, measured across `src/`,
  `tests/`, `docs/`, `examples/` and `scripts/`: `HTMLReporter` is imported by
  `scripts/regen_examples.py:51,77`, which generates the committed
  `examples/outputs/report.html`, and by
  `examples/sample_project/setup_and_run.py:155`; `OTelReporter` is imported
  and invoked by `examples/scripts/10_opentelemetry.py:30,35`. Both are
  rendered into the API reference by mkdocstrings
  (`docs/api/reference.md:174`, `:192`) and both are fully tested (14 and 10
  tests). The entry title is precise - *unreachable via settings* - but
  entry 19's "Same shape as entries 2 and 3" is not, and is corrected there.
  On the stated impact, `REPORTERS: ["otel"]` silently doing nothing: wiring
  the two names would **not** have fixed it. `_get_reporters` was three
  membership tests with no `else`, so `REPORTERS: ["consoel"]` was equally
  silent and always would have been. Unrecognized entries now emit
  `QueryDoctorWarning` naming the entry, the recognized names, and - for
  `html`/`otel` - the direct-invocation route, so a typo and an
  un-dispatched-but-real reporter read differently. That closes the whole
  class rather than two names of it.

## 3. Dead config keys in `DEFAULT_CONFIG`

- **Evidence:** `src/query_doctor/conf.py:18` (`STACK_TRACE_EXCLUDE`),
  `:29` (`IGNORE_PATTERNS`), `:33` (`QUERYIGNORE_PATH`) — read by no code
  path. `ADMIN_DASHBOARD.max_reports` (`conf.py:32`) vs the hardcoded
  `MAX_REPORTS = 50` (`admin_panel.py:22`).
- **Impact:** setting any of them silently has no effect.
- **Disposition:** implement each key or remove it from the defaults.
- **Resolved:** 2.2.0 - three wired, one removed, decided by a stated rule
  rather than per item. **The rule (S3), which S4 inherits for entries 5, 6
  and 19:**
  - **R0** - delete only against a measured no-caller sweep across `src/`,
    `tests/`, `docs/` (including mkdocstrings `:::` directives), `examples/`
    and `scripts/`, output shown. A live import is a caller; "not dispatched
    by settings" is not "no caller".
  - **R1** - *wiring gap* (implemented and tested, only the connection
    missing) -> wire it, with a test that fails before and passes after.
  - **R2** - *unbuilt surface* (a name with no implementation behind it) ->
    delete the surface; it re-enters later as a scoped feature, never as
    "wiring".
  - **R3** - *duplicate path* (already reachable by a supported, documented
    route) -> ratify and record why.
  - **R4** - silent-ignore traps are fixed as a class, not per name: a config
    surface that discards unrecognized input emits `QueryDoctorWarning`.

  This replaced a candidate axis of "does it carry a user-visible promise,
  and does the release keep or withdraw it". That axis was rejected for a
  specific reason worth recording, because a wrong reason was drafted first
  and struck: it is **not** that the axis would have deleted the reporters -
  their promise is the documented direct-invocation route
  (`docs/reporters/index.md:150-156`) and the working example, both of which
  the axis reads as promises kept, so it would have said ratify too. The axis
  was rejected because it carries **no requirement to measure callers before
  deleting**. R0 is that requirement.

  Applied:
  - `STACK_TRACE_EXCLUDE` - **R1, wired.** The filtering was already
    implemented and tested (`stack_tracer.py:33-54`,
    `test_stack_tracer.py:45,53`); only the argument was never passed.
    `QueryInterceptor` now takes `exclude_modules` and forwards it to
    `capture_callsite`; `middleware.py:126,161` supply the setting. Honoured
    exactly where `CAPTURE_STACK_TRACES` already was - see entry 27, which is
    the rest of that story.
  - `QUERYIGNORE_PATH` - **R1, wired.** Not merely "a setting S4 will want":
    `load_queryignore()` already had two live callers
    (`middleware.py:224-226`, `fix_queries.py:164-166`), both falling through
    to `_find_project_root()`. It names the ignore file itself; an explicit
    `project_root` argument still wins. A configured path that does not
    resolve degrades to project-root discovery **and warns** - degrading
    silently would be R4's exact failure, leaving a configured path
    observably identical to an unset one.
  - `IGNORE_PATTERNS` - **R2, removed** from `DEFAULT_CONFIG` with its docs.
    Nothing implemented it, and `.queryignore` already does the job; adding it
    would have been a feature, not a wiring fix. R0 sweep showed no reader -
    only the declaration, two test settings dicts that merely passed it, and
    doc disclaimers.
  - `ADMIN_DASHBOARD.max_reports` - **R1, wired.** The ring buffer is now
    built on first use and sized from config instead of at import
    (`admin_panel.py:_get_buffer`). `MAX_REPORTS` survives for importers but
    is **derived** from `DEFAULT_CONFIG` rather than re-declared as a second
    `50` - keeping a second literal would have reintroduced entry 16's defect
    one release after closing it.

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
- **Recurrence (2026-07-22, PR #12 review pass — filed separately as entry
  23, merged here):** a push from a shell without the project venv
  activated produced ``Executable `mypy` not found`` and a `pytest`
  failure, because `pytest` resolved to a system Python 3.11 install with
  no project dependencies while `mypy` and `ruff` were absent from `PATH`
  entirely. Prepending `.venv/Scripts` fixed it; the push was never run
  with `--no-verify`. The argument that entry added: this failure was
  loud, but a `PATH` carrying a *different* project's venv would run that
  project's `pytest` against this repository's `pyproject.toml`, and a
  green result would mean nothing. Nothing in the config asserted which
  interpreter ran. Candidate fixes it listed: pin to the project
  interpreter (hardcodes a platform path), move to pre-commit-managed
  environments (`language: python` with `additional_dependencies`), or add
  a guard hook asserting `sys.prefix`.
- **Third occurrence (2026-07-22, S12 push):** the pre-push hooks passed on
  the `docs/comparison-undate` push, but only because `.venv/Scripts` was
  prepended to `PATH` for that one command. Same mechanism, third sighting.
- **Resolved:** 2.2.0 (S1). Every entry now runs through
  `scripts/hookenv.py`, which resolves the repository venv explicitly
  (`.venv/Scripts/python.exe` or `.venv/bin/python`, both layouts), refuses
  to fall back to `PATH`, fails loudly when a tool is not importable in the
  resolved interpreter, and prints the interpreter it used so each run
  states its own provenance. Entries moved to `language: python` so the
  launcher itself starts from a pre-commit-managed interpreter rather than
  from whatever `python` the pushing shell has. Verified as a red/green
  pair from a shell with no venv on `PATH`: before, `Executable ruff not
  found` / `Executable mypy not found` / `pytest` exit 1 with no output
  from a broken system 3.11 shim; after, all four Passed via
  `...\.venv\Scripts\python.exe [repo .venv]`. The guard-hook candidate was
  rejected because it detects the condition rather than removing it — it
  would have failed in exactly the shell the fix has to work in.
- **The quiet-failure half, measured 2026-07-22 rather than argued.** The
  red/green pair above only covers tools being *absent*, which fails loudly.
  The dangerous case named in this entry — a `PATH` carrying a different
  project's *populated* venv — was reproduced directly: a throwaway venv
  outside the repository holding `ruff 0.15.22`, `mypy 2.3.0` and
  `pytest 9.1.1` (versus the repo venv's `ruff 0.15.21` and `mypy 2.2.0`),
  placed first on `PATH` with no repo venv entry. Running the **old**
  `language: system` entries in that shell:
  - `ruff check src/ tests/` -> `All checks passed!`, **exit 0**
  - `ruff format src/ tests/ --check` -> `131 files already formatted`, **exit 0**
  - `mypy src/query_doctor/` -> `Error importing plugin "mypy_django_plugin.main"`, exit 2
  - `pytest -q` -> `47 errors during collection`, exit 2

  So two of the four hooks went **green from the wrong toolchain**. The
  quiet-green claim in this entry is therefore confirmed for the lint hooks
  and *not* reproduced for `pytest`, which failed loudly here only because
  this particular foreign venv lacks Django; one that happened to carry
  Django and pytest-django would get further. Running the **fixed** hooks in
  the same shell: all four `Passed`, every line reading
  `hookenv: <tool> via ...\.venv\Scripts\python.exe [repo .venv]`, `mypy`
  checking 63 source files and `pytest` collecting and passing 809 — none of
  which the foreign venv could have produced.

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
- **Resolved:** 2.2.0 - **both** dispositions, not one. The two are not
  alternatives: single-sourcing alone is a change that cannot be observed to
  fail, so the cross-check is what makes it checkable. `pyproject.toml` now
  carries `dynamic = ["version"]` plus `[tool.hatch.version]` with
  `path = "src/query_doctor/__init__.py"`, and the static `[project]` key is
  gone -- `__init__.py:18` is the sole authority. `tests/test_public_api.py`
  `test_version` compares `__version__` against
  `importlib.metadata.version("django-query-doctor")`, so a reversion to a
  static declaration that drifts fails the suite; a separate assertion keeps
  the informative failure when the attribute is removed. Both assertions live
  in the existing test rather than a new one, which is a minimisation for a
  step that needed no new collected test, not a constraint -- adding tests
  costs one profile README edit plus one `claims.json` bump.
  Two corrections to this entry as written. Its quoted literals were stale:
  both declarations read `2.1.0` above and had moved together to `2.1.2`
  before resolution, so the two *declarations in the tree* never actually
  disagreed - manual release discipline held. The *installed artifact* is a
  different matter: `pip show` in the development virtualenv reported `2.0.0`
  against a runtime `2.1.2`, i.e. two releases of drift between the runtime
  version and the metadata the suite was resolving entry points through. The
  new cross-check went red on the unmodified tree because of it, which is how
  it was found. And the entry undercounts: `tests/test_public_api.py:69` was
  not only a guard that could not catch the drift, it was a *third* hardcoded
  literal a release had to remember to edit.
  Not gated by `claims.json`: during development the tree version legitimately
  leads the published PyPI version, so an exact row against PyPI would be red
  for most of every release cycle. The cross-check test is the gate.

## 17. `_analyze_and_report` blocks the caller inside `__acall__`

- **Evidence:** `src/query_doctor/middleware.py:134` calls the synchronous
  `_analyze_and_report` directly from the `async def __acall__` body, so every
  analyzer and every reporter runs without yielding. Found 2026-07-22 during
  the 2.1.2 ASGI work.
- **Impact:** narrowed by the 2.1.2 fix, not removed. With
  `async_capable = False`, `load_middleware` never gives the middleware an
  async `get_response`, so `__acall__` is unreachable through Django's
  middleware chain and the blocking work now happens in Django's
  thread-sensitive executor thread rather than on the event loop. `__acall__`
  is still reachable by directly instantiating the middleware around an async
  handler (`QueryDoctorMiddleware(some_async_view)`), which is what
  `tests/test_async_support.py` does; in that shape the analysis blocks
  whatever loop the caller is running.
- **Disposition:** deferred. Deliberately not fixed in 2.1.2 — that release is
  scoped to the two ASGI defects. Candidate fix: `await
  sync_to_async(self._analyze_and_report, thread_sensitive=False)(...)` inside
  `__acall__`. Tied to entry 19: if `__acall__` is removed, this disappears
  with it.

## 18. `docs/guides/middleware.md` claims `threading.local()` per-request state

- **Evidence:** `docs/guides/middleware.md:35` — "The middleware uses
  `threading.local()` to store per-request state, so it is fully thread-safe
  under WSGI." `src/query_doctor/middleware.py` holds no per-request state at
  all: the interceptor is a local variable in `_sync_call`/`__acall__`, and
  `QueryInterceptor` uses `contextvars.ContextVar`
  (`docs/deep-dive/architecture.md` documents the contextvars design). No
  `threading.local` appears anywhere in `src/query_doctor/`.
- **Impact:** the stated mechanism is wrong. The conclusion (thread safety)
  happens to hold, for a different reason, so no user is misled about
  behaviour — only about implementation.
- **Disposition:** correct the sentence to describe the contextvars design and
  cross-link the architecture page. Out of scope for 2.1.2: that release
  corrects only doc text the fix falsified or changed, and this sentence was
  wrong before and after it.

## 19. `__acall__` is unreachable through Django's middleware chain

- **Evidence:** with `async_capable = False`
  (`src/query_doctor/middleware.py:76`), `BaseHandler.load_middleware` computes
  `middleware_is_async = False` and adapts the handler to sync, so
  `self._is_async` is always `False` for a middleware Django built, and
  `__call__` (`middleware.py:104-106`) always routes to `_sync_call`.
  `__acall__` (`middleware.py:108`) runs only when the middleware is
  instantiated directly around an async callable.
- **Impact:** ~30 lines of duplicated pipeline that no deployment path
  executes. ~~Same shape as entries 2 and 3 — shipped code with no reachable
  caller.~~ **Corrected in 2.2.0 (S3):** that equivalence is false for entry
  2. Its two classes have live callers — `scripts/regen_examples.py:51,77`
  generates a committed artifact with `HTMLReporter`, and
  `examples/scripts/10_opentelemetry.py:30,35` invokes `OTelReporter` — so
  entry 2 was *unreachable via settings*, not unreachable. Entry 3's dead
  keys genuinely had no reader. Whether `__acall__` belongs in either group
  is what entry 19 still has to decide, and it must be decided by the R0
  sweep recorded in entry 3, not by inheriting this sentence: the tests
  instantiate the middleware directly around an async callable, so it has
  callers, and the real question is whether that is a supported API.
- **Disposition:** decide in 2.2 along with entries 2, 3, 5 and 6: either
  delete `__acall__` and let direct async instantiation be unsupported, or
  document it as a supported API for embedding the middleware by hand. Not
  2.1.2 — removing a method is public API surface reduction and does not belong
  in a patch release.

## 20. A third-party `async_capable` middleware with the same missing marker breaks the chain

- **Evidence:** measured 2026-07-22 on Django 5.2.16 / Python 3.11.15. With
  `MIDDLEWARE = [XFrameOptionsMiddleware, QueryDoctorMiddleware, A]` where `A`
  is a middleware declaring `async_capable = True` with an `async def
  __call__` but no `markcoroutinefunction(self)` call, the request fails with
  `TypeError: object HttpResponseServerError can't be used in 'await'
  expression` — the same failure shape as issue #11, sourced from `A` rather
  than from us. `asgiref.sync.iscoroutinefunction` returns `False` for an
  instance whose `__call__` is a coroutine function unless the instance is
  explicitly marked, so `convert_exception_to_response`
  (`django/core/handlers/exception.py:37`) builds a sync wrapper for it.
- **Impact:** query-doctor is in the traceback but not the cause. A user hitting
  this after upgrading to 2.1.2 could reasonably re-report #11.
- **Disposition:** do not fix and do not add detection. Detecting other
  middleware's marking bugs means inspecting `settings.MIDDLEWARE` at startup
  and warning about third-party classes, which is well outside a query
  diagnosis tool's remit and would produce false positives against any
  middleware using a different async signalling mechanism. Recorded so the next
  reporter of this traceback can be triaged quickly.

## 21. ASGI claims in the docs that 2.1.2 tests do not cover

- **Evidence:** the 2.1.2 test suite covers ASGI capture for `async def` and
  sync views across Django's `startproject` defaults
  (`tests/test_asgi_middleware_chain.py`). It does not cover:
  `docs/guides/async-support.md` "Django Async ORM Methods" (`aget`, `acreate`,
  `acount`, `aexists`, async iteration are asserted nowhere under ASGI — the
  ASGI tests issue a raw `SELECT 1`).
  Two claims originally listed here were measured before release rather than
  deferred: the concurrent-isolation claim in `docs/deep-dive/architecture.md`
  now has a test (`TestConcurrentRequestIsolation`), and the
  `diagnose_queries()`-inside-`async def` recommendation turned out to be false
  and is entry 22.
- **Impact:** the async ORM claim is plausible and consistent with the measured
  mechanism — Django's async ORM methods route through the same thread-sensitive
  executor the middleware now shares — but it is unverified, and this release is
  the third time an ASGI claim of this kind turned out to be false when
  measured.
- **Disposition:** add ASGI coverage for `aget`/`acreate`/`acount`/`aexists` and
  async iteration in 2.2, then either keep the claim or qualify it. Not 2.1.2:
  the release is scoped to the measured defects.

## 22. `diagnose_queries()` captures nothing inside an `async def` function

- **Evidence:** measured 2026-07-22, Django 6.0.7 / Python 3.12.0, driving a
  real `django.core.handlers.asgi.ASGIHandler` (not `AsyncClient`) against
  Django's `startproject` middleware defaults, with no query-doctor middleware
  installed so the context manager is the only capture path:
  - `with diagnose_queries():` inside an `async def` view issuing one query:
    `report.total_queries=0`, `cm_thr=10036 query_thr=12896 same_thread=False
    same_conn=False wrappers_in_view=0`;
  - the same block inside a `def` view served under the same ASGI handler:
    `report.total_queries=1`, `same_thread=True same_conn=True
    wrappers_in_view=1`;
  - WSGI control (`django.test.Client`, `def` view): `report.total_queries=1`,
    `same_thread=True same_conn=True wrappers_in_view=1`.
  Same root cause as the 2.1.2 middleware defect: `context_managers.py:36`
  installs `connection.execute_wrapper` on the calling thread's connection, and
  in an `async def` body that is the event loop thread, while the ORM runs in
  Django's thread-sensitive executor on another thread with another connection
  object.
- **Impact:** `docs/guides/async-support.md` recommended exactly this pattern
  for async views, so anyone who followed it got an empty report and no signal
  that anything was wrong. The doc text was corrected in 2.1.2 (the
  recommendation now says to use the middleware); the code limitation ships
  unchanged.
  **This also corrects a standing assumption**: the read was that
  `diagnose_queries()` might already work inside Django Channels consumers
  because 2.0 shipped async-safe `contextvars`. That read was wrong.
  `contextvars` were never the binding constraint — Django's connection
  registry is thread-local (`django/db/utils.py`, `thread_critical = True`), so
  the wrapper lands on the wrong connection object before contextvars are ever
  consulted. Any answer given on that basis needs correcting.
- **Disposition:** deferred. Out of scope for 2.1.2, which is scoped to the
  middleware. Candidate fix: have `diagnose_queries()` install the wrapper on
  every connection Django may resolve for the block, or route the block through
  `sync_to_async(thread_sensitive=True)` so it shares the executor thread the
  way the middleware now does. Either is a behaviour change to a public API and
  needs its own release. Same underlying question as entry 19: how much of this
  package should be doing thread bookkeeping on Django's behalf.

## 23. Pre-push hook environment is unpinned — merged into entry 11

Filed 2026-07-22 during the PR #12 review pass without checking whether the
condition was already tracked. It was: same mechanism (`language: system`),
same quiet-failure argument, same disposition as entry 11. Its distinct
content — the second observed failure and the three candidate fixes — has
been carried into entry 11 as a dated recurrence, and entry 11 carries the
resolution. No separate disposition. Heading kept as a tombstone so the
number is not silently reused and the duplication stays visible.

## 24. `architecture.md` credits contextvars for cross-request isolation

- **Evidence:** `docs/deep-dive/architecture.md`, the paragraph following the
  `QueryInterceptor.__init__` sample in the *No Global State* build-up: "This
  ensures that concurrent requests in both multi-threaded WSGI servers (e.g.,
  gunicorn with sync workers) and ASGI servers (e.g., uvicorn, daphne) do not
  interfere with each other." The "This" is the per-instance
  `contextvars.ContextVar`. Pre-dates PR #12.
- **Impact:** same attribution class as entry 22. Under ASGI the operative
  mechanism for cross-request isolation is that Django opens a
  `ThreadSensitiveContext` per request, which makes asgiref allocate a separate
  executor thread per request — measured to hold from asgiref 3.6.0 (the floor
  reachable via `django>=4.2`) through 3.12.1. Thread separation alone is
  sufficient to produce the observed isolation, so contextvars cannot be shown
  to be the cause. The claim may still be true for the WSGI half and for
  coroutines sharing a thread; it is simply not established by anything, and no
  test can currently discriminate the two mechanisms.
- **Disposition:** 2.2. Either design a test that isolates contextvars from
  thread separation (concurrent work forced onto one thread), or rewrite the
  sentence to state thread/context separation as the mechanism and drop the
  contextvars causality. Deliberately not rewritten in 2.1.2: the sentence
  pre-dates this release, and PR #12 corrects only text the fix falsified or
  changed. `tests/test_asgi_middleware_chain.py::TestConcurrentRequestIsolation`
  must not be cited as backing for it — that test passes on thread separation
  alone.

## 26. The `Upload coverage` step cannot report failure

Numbered 26 rather than 25: 25 is reserved for the phase-1 branch disposition
(S13), which does not exist yet.

Retitled 2026-07-23. The original title — "Codecov uploads have never succeeded,
and the step reports success" — was half wrong. See the correction block below;
the original evidence and text are kept intact rather than edited away, because
the falsified half is the useful part of the record.

- **Evidence:** measured 2026-07-22 on the `main` CI run `29941974446`, job
  `test (3.12, 5.2)`, step `Upload coverage`:

  ```
  error - Report creating failed: {"message":"Token required - not valid tokenless upload"}
  error - Upload queued for processing failed: {"message":"Token required - not valid tokenless upload"}
  ```

  The step's own conclusion for the same run: `6. Upload coverage -> success`.
  The badge confirms the other end — the SVG at
  `codecov.io/gh/hassanzaibhay/django-query-doctor/graph/badge.svg` returns 200
  with text nodes `['codecov', 'codecov', 'unknown', 'unknown']`, i.e. Codecov
  holds no data for this project.
- **Impact:** same shape as entry 11, one level up. `ci.yml:42` sets
  `fail_ci_if_error: false`, so a rejected upload is indistinguishable from a
  successful one in the job summary. A step named "Upload coverage" has
  reported success on every run of every release while uploading nothing. The
  coverage number in CI is real — `pytest --cov` runs and enforces
  `fail_under` — but nothing external has ever received it, so no trend, no
  per-PR delta, and no dynamic badge is possible.
- **Consequence for the claims manifest:** the `86%+` coverage claim on the
  profile page has to stay a hardcoded floor row (`claims.json`,
  `profile-coverage`). A floor row detects overstatement only; it cannot detect
  decay, so that claim would stay green if coverage fell to 80%. Replacing it
  with a dynamic badge is the real fix and is blocked on this entry.
- **Correction (2026-07-23, S9a.1).** Hassan checked the Codecov project from a
  browser and it holds data: `main`, 87.97% (3057 of 3475 lines), sourced from
  commit `c779e0f` — the S9a squash merge. Re-measured independently here, with
  `Cache-Control: no-cache` on the request, the badge SVG now returns text nodes
  `['codecov', 'codecov', '88%', '88%']`, not `unknown`. Three claims above are
  therefore false:
  1. "Codecov holds no data for this project" — false.
  2. "has reported success on every run of every release while uploading
     nothing" — false; `c779e0f` landed.
  3. "there is no code change that closes this without it" — false; the
     `fail_ci_if_error` fix is a one-line code change.

  The error output recorded above was a real measurement of run
  `29941974446` and stands. What was wrong was generalising one run into
  "every run of every release" — an over-generalisation from a single data
  point, written as though it were a property of the configuration. The three
  months of `+87.97%` trend Codecov reports is consistent with `c779e0f` being
  its first data point, i.e. tokenless upload was rejected then and accepted
  later; its reliability in between is unmeasured.

  **The surviving defect is the only part that was ever a defect:** `ci.yml`
  sets `fail_ci_if_error: false`, so a step named "Upload coverage" is
  structurally incapable of reporting failure. Same shape as entry 11, and
  closable by code.
- **Coverage divergence, recorded before the badge work (S9a.1).** Two
  authorities now report this project's coverage and they disagree:

  | Source | Value | Counts |
  |---|---|---|
  | `coverage.xml` `line-rate` — what the claims gate measures | 87.94% | `lines-covered=3056` of `lines-valid=3475` |
  | Codecov, recounted from the same upload | 87.97% | 3057 of 3475 |

  One line in 3475, almost certainly an exclusion-handling difference rather
  than a defect in either. Harmless today — both clear the `profile-coverage`
  floor of 86. It stops being harmless the moment the badge becomes dynamic: if
  the badge reads from Codecov while `measure_coverage_percent` reads
  `line-rate`, the published number and the gated number drift apart by
  construction — one claim, two authorities, the exact pattern this release
  exists to end. Not reconciled here.
- **Resolved:** 2.2.0 (S9a.1) — `fail_ci_if_error: true` shipped, so a rejected
  upload now fails the job loudly instead of reporting success.
  `CODECOV_TOKEN` is **not** a blocker: the upload works without it today. It is
  recorded as the contingency if tokenless proves flaky. When that flag first
  fires, CI going red *is* the gate working on its first run — do not revert to
  `fail_ci_if_error: false`, and do not add `continue-on-error`, a conditional,
  or a retry-then-pass, all of which restore a step that cannot report failure.

  The dynamic coverage badge is **not** carried here. It is not a defect; it is
  a choice between Codecov's badge and a shields endpoint generated from the
  gate's own `coverage.xml` and published to the existing `gh-pages` branch. The
  single-authority argument favours the endpoint, but that is Hassan's call, and
  it is recorded as an S14 scope item rather than as a backlog entry. A defect
  backlog holds defects; keeping a decision here would have made this entry
  `Resolved (partial)` and put a second permanent resident in a category that
  never empties. Filed 2026-07-22 during S9a; corrected and closed 2026-07-23.

## 27. `CAPTURE_STACK_TRACES` is unread in 7 of 9 `QueryInterceptor` sites

- **Evidence:** measured 2026-07-23 during S3, while wiring
  `STACK_TRACE_EXCLUDE`. `grep -rn "QueryInterceptor(" src/` returns nine
  construction sites. Two pass configuration —
  `middleware.py:126` and `:161`. The other seven are bare
  `QueryInterceptor()` and take the `capture_stack: bool = True` default:
  `celery_integration.py:102`, `context_managers.py:33`,
  `project_diagnoser.py:218`, `pytest_plugin.py:73`,
  `management/commands/check_queries.py:189`,
  `management/commands/fix_queries.py:179`,
  `management/commands/query_budget.py:81`.
- **Impact:** `CAPTURE_STACK_TRACES: False` is honoured only by the
  middleware. `diagnose_queries()`, the pytest plugin, all three management
  commands, the Celery integration and the project diagnoser capture stacks
  regardless — the setting is documented without the qualifier, and the cost
  it exists to avoid is still paid on every one of those paths.
  `STACK_TRACE_EXCLUDE`, wired in the same release, inherits the same reach
  by construction: it was wired to parity rather than beyond it, so this
  entry covers both keys.
- **Not deliberate, as far as the tree shows:** each of the seven was read
  with surrounding context and none carries a comment, docstring clause, or
  argument mentioning stack capture or its cost. Two argue against a
  deliberate opt-out — `check_queries` and `fix_queries` emit `file:line`
  prescriptions, and `fix_queries` keys generated fixes on the callsite, so
  they need capture and were simply never offered the switch.
- **Disposition:** **R1** under the S3 rule (entry 3): mechanism implemented
  and tested, connection missing. Closable in 2.2.0; destination **S4**,
  alongside entry 6 — both are "wire an implemented-but-unconnected mechanism
  into the pipeline", and S4 already opens this code. Deliberately not folded
  into S3: it is a behaviour change on seven paths (a user setting
  `CAPTURE_STACK_TRACES: False` today still gets capture there and would stop),
  which is a different reviewable unit from wiring a key that was inert
  everywhere. Candidate fix: have `QueryInterceptor.__init__` read
  `get_config()` for its own defaults so every construction site inherits both
  keys, rather than adding the same two kwargs to seven call sites.
