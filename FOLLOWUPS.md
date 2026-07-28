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
for the phase-1 branch disposition and is not yet written. Entries 28-30 came
out of S7 (2026-07-27): 28 from the claim-by-claim disposition of entry 21,
where the one remaining async-ORM claim measured false on a second route rather
than being edited in passing; 29 from profiling the blocking call entry 17
names, which found the cost is analyzer *discovery* rather than analysis; and 30
from reading the three tests entry 29's fix moves, one of which asserts nothing
its name promises. Entry 31 came out of S8 (2026-07-28): a claim-by-claim
inventory of `docs/guides/async-support.md`, commissioned because four claims
in that one file measured false within a single release.

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

**Open entries: 4**

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

  **S4 refinements to the rule (2.2.0), from applying it to entries 5, 6 and
  19:**
  - **R2's mirror case (entry 5).** R2 reads "a name with no implementation
    behind it". `record_project_report` had an implementation; what was never
    built was the *consumer* — the template that renders it. R2 by intent, but
    the wording covers only the producer-missing direction; the consumer-missing
    direction deletes the same way.
  - **R3 carries a documentation obligation (entry 19).** When the code being
    ratified is the *only* implementation of the route being supported,
    ratifying must **document the route**, not merely record why — otherwise
    "reachable by a documented route" is asserted of a route no doc describes.
  - **R1 is a presumption, rebuttable by measurement (entry 6).** Entry 6 was a
    clean R1 by inspection — implemented, tested, no caller, only the connection
    missing — yet wiring it was *measured harmful* (it re-attributed and
    silently downgraded aggregate findings), so it was deleted and its goal
    delivered at a different layer. No R0–R4 clause covered "implemented,
    tested, no caller, and wiring it would be wrong". Record that R1's
    disposition can turn on a measurement rather than on classification.

## 4. `.queryignore` dispatch trap

- **Evidence:** rules applied only at `middleware.py:210-214` and
  `management/commands/fix_queries.py:164-168`; `check_queries` and
  `diagnose_project` never load them.
- **Impact:** findings suppressed in dev (middleware) reappear in CI
  commands.
- **Disposition:** wire `ignore.filter_prescriptions` into both commands.
- **Resolved:** 2.2.0 (S4) - `.queryignore` filtering consolidated into
  `pipeline.analyze()`, which every prescription-producing surface now routes
  through. The disposition named two surfaces (`check_queries`,
  `diagnose_project`); this wired **seven** — those two plus the pytest plugin,
  the `diagnose_queries()` context manager, the Celery integration, and (already
  honouring the file) the middleware and `fix_queries`. That exceeds the entry
  as written, deliberately: the five newly-covered surfaces are the class
  enumerated at `docs/guides/query-ignore.md:19-26`, and the standing
  expectation is to fix the class, not the flagged instances. `fix_queries`
  previously swallowed ignore-filter failures with a bare `pass`; through the
  shared pipeline it now logs them, matching the middleware. Stale evidence:
  the rules applied at `middleware.py:276-280` and `fix_queries.py:164-168`,
  not the `:210-214 / :164-168` line pair this entry recorded for the
  middleware.

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
- **Resolved:** 2.2.0 (S4) - **R0, deleted.** `record_project_report`, the
  `_latest_project_report` global, and the unrendered `project_report` context
  key are gone. Source-only no-caller sweep across `src/ tests/ docs/ examples/
  scripts/` returned zero hits for both symbols; the four-file result of a naive
  `grep project_report` is the **live** `query_doctor.reporters.project_report`
  module (reached from `diagnose_project.py:21`, `tests/test_project_report.py:12`,
  behind `diagnose_project --format html`), a module-versus-symbol collision, not
  a caller. `templates/query_doctor/dashboard.html` never rendered the key (zero
  hits). No test referenced the deleted symbols; suite green at 831. The
  `[1.0.0]` changelog claim gains an additive 2.2.0 note; nothing above it is
  rewritten. Stale symbol refs: `admin_panel.py:31` (`_latest_project_report`),
  `:97` (`record_project_report` def), `:150` (context key) — not the
  `:67 / :25 / :119` this entry recorded.

## 6. `should_ignore_query` has no caller

- **Evidence:** `src/query_doctor/ignore.py:62-88`; nothing in the pipeline
  invokes it.
- **Impact:** it is the only implementation of per-query `.queryignore`
  matching (including `sql:` rules against raw SQL); without a caller,
  `sql:` rules only ever match prescription descriptions
  (`ignore.py:149-153`) — already documented in the query-ignore guide.
- **Disposition:** call it during capture/analysis, or delete it.
- **Resolved:** 2.2.0 (S4) - **R0, deleted; goal delivered elsewhere.**
  `should_ignore_query` is removed. Its goal — `sql:` rules matching raw SQL —
  is delivered at prescription-filter time instead: `filter_prescriptions`
  gained an optional `queries` argument, and a `sql:` rule now matches a
  prescription when the pattern matches the description **or** the raw SQL of any
  captured query sharing the prescription's `fingerprint` (substring-style,
  `%`→`*`, wrapped in `*...*` — the same anchoring as the description arm). A
  strict superset: every rule matching today still matches. Wiring the function
  into capture, the disposition's first branch, was **measured harmful** and
  rejected — see the R1-negative refinement in entry 3. Recorded against R0
  itself: the S4 plan asserted this function had "zero callers — grep returns
  its definition only", citing the exact `src/ tests/ docs/ examples/ scripts/`
  sweep R0 mandates. The claim was false and the command had not been run; the
  sweep returned one import and seven assertions in `tests/test_queryignore.py`.
  R0 was invoked and violated in one sentence, in the first release where R0 is
  load-bearing, by the reviewer who wrote the rule. Deletion stayed valid — no
  production caller in `src/`, not exported, not documented — and the seven
  tests were reshaped: two `sql:` cases ported to the prescription level, an
  empty-fingerprint analogue added, four file/callsite cases dropped (the
  query-level semantics they exercised no longer exist). Stale evidence:
  `should_ignore_query` at `ignore.py:80-106` (not `:62-88`); the
  description-only `sql:` branch at `:167-171` (not `:149-153`).

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
- **Resolved:** 2.2.0 (S9) — check added (`tests/test_svg_capture_sync.py`),
  and it caught a real error on its first run.

  **Neither disposition option worked as written.** Generating line data from
  the captures directly is impossible: the captures embed absolute machine
  paths, and `auto_fix.capture.txt` embeds a pytest tmpdir whose counter
  changes every run (`...\pytest-of-<user>\pytest-46\...`). Regenerating from
  them would publish a developer's home directory into a shipped SVG and churn
  on every run. A verbatim comparison fails for the same reason, plus the SVGs
  deliberately relabel paths to `myapp/views.py` and drop lines for width.

  So the check pins the direction that actually matters: **every line an SVG
  displays must be traceable to a capture line.** A capture line the SVG omits
  is fine; an SVG line the tool never produced is not. Declared exceptions,
  each individually justified in the test: `Location:`/`--- `/`+++ ` are
  presentation-substituted and checked for presence only; one editorial caption
  in `auto_fix.svg` is not tool output at all. `@@ ` hunk headers are
  deliberately content-matched.

  **RED before GREEN, and the RED was a genuine defect, not a scaffold:**

  ```
  AssertionError: console_output.svg shows 1 line(s) with no source in
  console_output.capture.txt: ['Total queries: 15 | Time: 0.4ms | Issues: 4']
  ```

  The capture says `0.2ms`. The shipped SVG had claimed `0.4ms` since it was
  hand-transcribed — exactly the silent drift this entry predicted, already
  present. Fixed in `generate_svgs.py` and the SVG regenerated; the diff is
  that one line, and the other five SVGs regenerated byte-identical, which
  confirms the generator is deterministic and the change surgical.

  **Named residue.** `scripts/regen_examples.py` produces exactly two
  `.capture.txt` files, so only 2 of 6 SVGs can be pinned at all. The other
  four are hand-authored end to end and listed by relpath in `UNPINNED_SVGS`
  (`project_diagnosis.svg`, `query_budget.svg`, `quick_start.svg`,
  `test_usage.svg`). A second test asserts that set is *exactly* those four, so
  the gap is named and cannot widen silently — adding a seventh SVG without a
  capture fails. Closing this gap for real means teaching `regen_examples.py`
  to capture those four scenarios; that is not attempted here.

  The generator is read with `ast`, never imported: importing it would execute
  its module-level `create_terminal_svg` calls and rewrite the shipped SVGs as a
  side effect of running the test suite.

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
- **Resolved:** 2.2.0 (S9) — discovery extended via an explicit `ROOT_DOCS`
  tuple (`scripts/docs_truth_sweep.py`), exactly as the disposition specified
  and deliberately not a glob. The measured cost held to the entry's figure:
  repointing discovery produced precisely the predicted 2 violations, shown
  RED before allowlisting:

  ```
  2 violation(s):
    CHANGELOG.md:301: unknown option 'ANALYZERS.fat_select.field_count_threshold'
    UPGRADING.md:125: unknown option 'ANALYZERS.fat_select.field_count_threshold'
  exit=1
  ```

  Both name the 2.1.0 rename of that config key to
  `ANALYZERS.fat_select.threshold` — the CHANGELOG entry documenting the
  rename and the UPGRADING instruction telling 2.0.x users which key to
  change. Naming the dead key is the point of both, so both are allowlisted.
  Note the token is not entirely dead: `field_count_threshold` survives as a
  Python constructor kwarg (`analyzers/fat_select.py:57`); it is only the
  *config key* that was renamed, which is what the sweep checks.

  The allowlist is keyed on `(relpath, token)` rather than on the token
  alone, so it excuses exactly two references on two named pages. Verified by
  positive control rather than by reading: the same dead token written to a
  non-allowlisted page still fails.

  ```
  docs/__probe_tmp.md:1: unknown option 'ANALYZERS.fat_select.field_count_threshold'
  ```

  Without that control the GREEN would not distinguish a scoped allowlist
  from a blanket mute.

  Stale line reference: the entry cites `:155`; discovery was at `:160` by S9.

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
- **Resolved:** 2.2.0 (S9) — all four scheduled symbols removed:
  `ConfigError`, `AnalyzerError`, `InterceptorError` (`exceptions.py`) and
  `set_thread_override` (`turbo/patch.py`). Recorded under CHANGELOG
  `Removed`.

  **One premise of this entry was wrong and the removal was reclassified
  because of it.** The entry states the three exception classes are "not
  referenced in any doc". They are not named in any markdown — but
  `docs/api/reference.md:242` autodocs the entire `query_doctor.exceptions`
  module via mkdocstrings, so all three rendered on the published API
  reference page. Confirmed against built HTML before removing, not inferred
  from the absence of a grep hit:

  ```
  ConfigError rendered on API page: 7 occurrences
  AnalyzerError rendered on API page: 7 occurrences
  InterceptorError rendered on API page: 7 occurrences
  ```

  So this was a *documented* public-API removal, not the silent deletion of an
  unreferenced symbol, and the CHANGELOG entry says so and tells callers to
  catch `QueryDoctorError` instead. The general lesson: a module-level autodoc
  directive publishes every public symbol in that module, so `grep` over
  markdown cannot establish that something is undocumented.

  The three classes also had live test references
  (`tests/test_exceptions.py`), which the entry did not mention — three
  `issubclass` tests plus `test_can_raise_and_catch`, which raised
  `ConfigError`. The `issubclass` tests were removed with their subjects;
  `test_can_raise_and_catch` was kept and re-pointed at `QueryBudgetError`,
  since the property it tests is the single-except-clause contract, not that
  particular exception.

  Stale line references: `exceptions.py:19/:23/:27` had drifted to `:31/:35/:39`
  by S9. `turbo/patch.py:102` was exact.

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
- **Resolved:** 2.2.0 (S6, commit 05808a5). The open branch is now covered by two
  deterministic tests forcing the destination stream's encoding
  (`tests/test_console_reporter.py::TestRichBoxEncodingBranch`), which run on every
  platform and every CI run. **Correction, measured on rich 15.0.0:** the pure-ASCII
  substitution is driven by the destination stream's ENCODING (a non-utf encoding
  cannot represent U+2500-range box drawing), NOT by `legacy_windows`.
  `legacy_windows` only swaps rounded corners for square ones among Unicode boxes;
  the "`legacy_windows=True` emits pure ASCII" reading above conflated the two axes
  because that dev session was also cp1252. Scope boundary: the test proves "non-utf
  destination encoding => pure-ASCII box"; it does NOT test Rich's platform detection
  (`detect_legacy_windows`, which keys off VT support on the stdout handle and is
  version-independent, not a Windows-version question) - that is Rich's
  responsibility, not this package's. No `windows-latest` CI row was added: a piped
  GHA stdout reports `legacy_windows=True` today, but the row would silently stop
  exercising the branch the day GHA runs steps in a real console or enables VT.
  Stale evidence: `ci.yml:11,45,59` are wrong - `runs-on: ubuntu-latest` is at 11,
  55, 69 and 81 (four jobs: test, lint, typecheck, docs-gate); `:45` is a Codecov
  comment and `:59` a `with:`.

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
- **Resolved:** 2.2.0 (S6, commit 1488dd9 plus the `_probe_target` follow-up,
  commit 5). Django's `OutputWrapper` subclassed `TextIOBase` before 5.2, so on
  those versions `OutputWrapper.encoding` resolves to the inherited descriptor and
  reads `None`, and its `__getattr__` never forwards the wrapped stream's encoding;
  from 5.2 it forwards directly. So the one-line `Console(file=self._stream)`
  change (commit 1488dd9) fixed the middleware path (`sys.stderr`) on every
  version, but the command path - both entry points wrap `self.stdout` in an
  `OutputWrapper` (`check_queries.py:221`, `check_serializers.py:176`) - was fixed
  only from 5.2 up. Commit 5 adds `_probe_target()`, which unwraps
  `OutputWrapper._out` when `encoding` reads `None`, closing the command path
  across the whole supported 4.2-6.0 range. Safe because `_render_rich` renders
  through `console.capture()`: the Console's file is probed, never written to; the
  write is `print(output, file=self._stream)` at `console.py:63`. `_probe_target`
  affects encoding only - width comes from `_STD_STREAMS`, `is_terminal` is pinned
  by `force_terminal=False`. The cross-version pin is
  `test_cp1252_outputwrapper_destination_renders_ascii` (a cp1252 `OutputWrapper`
  destination renders a pure-ASCII box), green on all five matrix versions.
  `legacy_windows` is unaffected: it comes from `detect_legacy_windows()`, which
  probes the stdout handle globally, independent of the Console's file. Stale
  evidence: `check_queries.py:225` is actually `:221`, and the Impact line's
  `middleware.py:47` is actually `:83`; `console.py:37/:102/:129` were accurate.

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
- **Resolved:** 2.2.0 (S6 records; work shipped in PR #21, squash `2609681`).
  **Wired, not deprecated.** `pytest_terminal_summary` (`pytest_plugin.py:140`)
  surfaces each fixture's stashed report at end of session - one header line plus
  one line per test with findings - so the fixture has an observable effect. The
  `QueryDoctorWarning` (entry 1) is retained for the in-test-read path, which stays
  vacuous under any option. PR #21 shipped the code but omitted this file from its
  diff, so the work landed while the record stayed open; corrected here in S6's
  records commit (the reviewer error was in the S5 bookkeeping, not the PR). The
  evidence line refs above (`:81-104`, `:104`) predate the fix.

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
- **Resolved:** 2.2.0 (S6, commit d7693a5). Strengthened to assert
  `"No issues detected"`, not the vacuous `"No issues" or "0"` (the header always
  carries a `0`). Not deleted: it is the only direct `_render_rich` coverage of the
  empty branch (`console.py:123-124`) - the nearby `test_render_empty_report_content`
  goes through `render()` and passes on `_render_plain` too, which emits the same
  marker (`console.py:190`), so it does not pin the Rich path. Verified falsifiable:
  with `console.py:123-124` removed the strengthened assertion fails; the old one
  passed. `:352` was accurate.

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
- **Note (S7, 2026-07-27):** measured rather than argued. Three findings, none
  of which close this entry.

  1. **The candidate fix above is wrong as written.** `thread_sensitive=False`
     moves `_analyze_and_report` onto an arbitrary worker thread, and the
     hazards that exposes are not the one that would be guessed. A
     `deque.append` race is **not** among them: `deque.append` is thread-safe,
     measured at 16 threads x 5000 appends with 80000/80000 items intact. The
     real hazards are (a) the check-then-set lazy init at `admin_panel.py:40-53`
     — two threads can both read `_report_buffer is None`, both build a deque,
     and one buffer is discarded with every report in it; 199 of 200 trials lost
     reports — and (b) interleaved writes from two reporters onto the same
     stream, which `print(output, file=self._stream)` does not serialise. Any
     future off-loop fix has to address both; `thread_sensitive=False` alone
     addresses neither.
  2. **The blocking is real, but it is discovery, not analysis.** Profiling the
     call showed the cost is flat in query count — a 0-query request costs the
     same as a 100-query one — and scales with the number of *installed
     distributions*: ~8 ms at 87 distributions, ~10 ms at 152. That is
     `discover_analyzers()` rescanning entry points on every call, filed as
     entry 29. Analysis proper is sub-millisecond. So the thing this entry
     proposes to move off the loop is mostly filesystem I/O that should not be
     happening at all.
  3. **Disposition: (b) — leave it synchronous and document it as a cheap
     inline post-response step — conditional on entry 29 landing first.** That
     sentence is only true once the discovery cache exists; writing it while the
     step still costs ~8 ms would be the fifth false doc claim of this release.
     This entry therefore stays open and closes in **S7b**, the same step that
     lands entry 29's cache.

  **Stale line numbers corrected.** The blocking call is `middleware.py:170`,
  not `:134`; `__acall__` is `middleware.py:144`, not `:108`. The sync-path copy
  of the same call at `:202` is correct there and out of scope — it already runs
  in a worker thread.
- **Resolved:** 2.2.0 (S7b) — **disposition (b): left synchronous, and now
  documented as a cheap inline post-response step.** No change to
  `middleware.py`; the only edit is the disclosure at
  `docs/guides/async-support.md:79`, which already said `__acall__` runs
  analyzers and reporters without yielding and now carries the measured
  magnitude.

  (b) became writable only because entry 29 landed first. At ~8 ms it would have
  been the fifth false doc claim of this release. Post-cache, on one development
  machine, `pipeline.analyze` costs 0.144 ms for a request that issued no
  queries.

  **One premise of this entry's note did not survive the fix, and the doc says
  what was measured rather than what was predicted.** "Flat in query count" was
  true *because* ~8 ms of entry-point scanning dominated everything; with the
  scanning gone it is false. Re-measured post-cache, `pipeline.analyze` scales
  roughly linearly with captured query count:

  | queries | ms/call |
  |---:|---:|
  | 0 | 0.144 |
  | 1 | 0.189 |
  | 10 | 0.368 |
  | 50 | 1.176 |
  | 100 | 2.177 |
  | 500 | 10.275 |

  So the disclosure states linear scaling in captured queries, not flatness. The
  worst case — single-digit milliseconds at several hundred queries — is a
  request the tool exists to flag, which is the argument for (b) rather than a
  hole in it. Note what this means for the pre-cache reading: a 500-query request
  used to cost ~8 ms of discovery *plus* ~10 ms of analysis, and the flatness
  observed then was an artifact of measuring against small query counts where
  discovery swamped the linear term.

  The candidate fix and the hazards stand as recorded above:
  `sync_to_async(thread_sensitive=False)` is measured wrong; the hazards are the
  check-then-set lazy init at `admin_panel.py:40-53` and interleaved reporter
  stream writes, **not** a `deque.append` race, which is thread-safe
  (16 threads x 5000 appends, 80000/80000 intact). Corrected line numbers stand:
  the blocking call is `middleware.py:170` (not `:134`), `__acall__` is `:144`
  (not `:108`).

## 18. `docs/guides/middleware.md` claims `threading.local()` per-request state

- **Evidence:** `docs/guides/middleware.md:39` — "The middleware uses
  `threading.local()` to store per-request state, so it is fully thread-safe
  under WSGI." (Filed as `:35`; the line had drifted to `:39` by S8, corrected
  here.) `src/query_doctor/middleware.py` holds no per-request state at
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
- **Resolved:** 2.2.0 (S8) — corrected, and the claim was in **three** places,
  not the one this entry filed. `docs/guides/middleware.md:39` and
  `docs/contributing.md:162` both stated `threading.local()`; the second is a
  *contributor instruction*, so leaving it would have regenerated the first.
  A third copy sat in a test docstring, `tests/test_interceptor.py:114`
  ("Each thread should have its own query list via threading.local") — the
  test itself is correct and passes precisely *because* the storage is a
  `ContextVar`: a new thread starts a fresh context, so the lookup resolves to
  the default rather than to the main thread's list. All three now name
  `contextvars.ContextVar` and the two doc surfaces cross-link
  `docs/deep-dive/architecture.md#per-instance-contextvar-storage`.

  The true mechanism is cited at `src/query_doctor/interceptor.py:10,56-63`;
  `threading.local` appears nowhere in `src/query_doctor/` except
  `turbo/context.py:7`, where it is prose naming what is used *instead* and
  was deliberately left alone.

  **Scope boundary against entry 24:** this entry establishes only that
  per-request state *is stored in* contextvars. It is not evidence that
  contextvars is what *isolates concurrent requests* — see entry 24, which
  reaches the opposite conclusion on that separate question.

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
- **Resolved:** 2.2.0 (S4) - **R3, ratified and documented.** `__acall__`
  stays and is now documented as a supported route in
  `docs/guides/async-support.md`. R3 as written ("already reachable by a
  supported, documented route") did not fit unmodified: `__acall__` is the
  *only* implementation of the route being supported, so ratifying had to
  **document the route**, not merely record why — the refinement recorded in
  entry 3. Cost accepted and stated: ~20 lines of duplicated pipeline,
  permanently. Deleting it would also delete `__call__`'s `_is_async` branch,
  which makes `test_asgiref_wrapped_handler_detected_as_async` meaningless and
  removes the asgiref-vs-inspect predicate defence at `middleware.py:127-131` —
  regression coverage a shipped incident produced. Entry 17's blocking-call
  defect is tied here and stays open. Stale evidence: `__acall__` at
  `middleware.py:154` (not `:108`).

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
- **Resolved:** 2.2.0 (S7, commit `a95840c`). The coverage this entry asked for
  landed as `TestASGIAsyncORMCapture`
  (`tests/test_asgi_middleware_chain.py:277`), which drives all five surfaces —
  `aget`, `acreate`, `acount`, `aexists`, async iteration — through a real
  `ASGIHandler` on the `MIDDLEWARE`-chain route and asserts captured counts of
  1/2/2/2/2 plus a per-method SQL fragment, so the raw `SELECT 1` that satisfied
  the old ASGI tests cannot satisfy these. Measured on Django 6.0.7 and 4.2.30.
  The "either keep the claim or qualify it" half is **not** decided here: the
  claim measured **false on the hand-embedding route**
  (`docs/guides/async-support.md:64`), where all five capture nothing, so the
  doc sentence at `:85` is route-dependent and needs a qualifier rather than a
  keep-or-delete. That is split out as **entry 28** rather than edited in
  passing — the same precedent entry 22 set, where a claim measured false during
  this entry's disposition became its own entry instead of a silent fix. The
  measured non-capture is pinned by `TestDirectEmbedAsyncORMNotCaptured`
  (`:315`), a characterization test rather than an xfail: it keeps the suite
  green, states the current behaviour, and flips when entry 28's disposition
  lands. A sync view doing identical ORM work through the same driver captures
  2, which is what makes the five zeros falsifiable.

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
- **Resolved:** 2.2.0 (S8) — **rewritten, and this entry's own diagnosis was
  understated.** The disposition asked for one of two outcomes: build a test
  that isolates contextvars from thread separation, or rewrite. The answer is
  the rewrite, and the reason is stronger than "thread separation is
  sufficient".

  **The operative mechanism is neither contextvars nor thread separation: it
  is per-request instantiation.** `build_interceptor()` is called per request
  (`middleware.py:162,194`) and the result is a local variable. All eleven
  construction sites in `src/` do the same — `context_managers.py:33`,
  `celery_integration.py:102`, `pytest_plugin.py:88`,
  `project_diagnoser.py:218`, and three management commands. No interceptor is
  ever shared across requests, so there is no shared state for any mechanism
  to protect.

  **Constructibility verdict: not constructible for the claim as written**, and
  this was measured rather than argued. Two probes, run under
  `asyncio.gather` with `await asyncio.sleep(0)` forcing interleaving on a
  single thread:

  *Probe 1 — positive control, one **shared** store:*

  ```
  CtxVarStore      task A: n=3 ['A0','A1','A2']            isolated == True
  ThreadLocalStore task A: n=5 ['B0','A1','B1','A2','B2']  isolated == False
  ```

  *Probe 2 — a **fresh** store per request, which is what the code does:*

  ```
  CtxStore   per-request-fresh -> isolated == True
  PlainStore per-request-fresh -> isolated == True
  ```

  Probe 1 is what makes probe 2 mean anything: it shows the comparison *can*
  discriminate, so probe 2's `True/True` is a real negative result and not a
  probe that would have printed `True` for anything. Read together: contextvars
  is genuinely distinguishable from `threading.local()` — but only when a store
  is shared, which this codebase never does. Swapping the `ContextVar` for
  `self._queries = []` would leave every existing test green.

  **Disposition applied:** the claim is rewritten to state what is
  demonstrable. `architecture.md` now attributes cross-request isolation to
  per-request instantiation (plus Django's per-request `ThreadSensitiveContext`
  under ASGI), keeps the narrower and backed contextvars claim — correctness
  within one interceptor across `await` and across threads — and says
  explicitly that a causal contextvars claim would be asserted, not
  demonstrated. The `TestConcurrentRequestIsolation` citation is retained only
  for the *behaviour* it does establish, with an explicit note that it
  identifies no mechanism. It is nowhere cited as backing for contextvars.

  **A discriminating test was deliberately not added.** Probe 1 shows one is
  constructible for a *shared* interceptor, but no code path shares one, so
  such a test would pin a usage the package does not have — and would function
  as exactly the smuggled backing this entry warns against. Filed instead as a
  candidate if a shared-interceptor design is ever introduced.

  **Second mis-named backing found and fixed:**
  `tests/test_async_support.py:175` was `TestContextVarsIsolation::
  test_separate_interceptors_isolated`, which constructs two *separate*
  interceptors — the same defect as `TestConcurrentRequestIsolation`, named for
  contextvars while testing instance separation. Not cited in any doc, but it
  would have read as backing to the next person. Renamed to
  `TestInterceptorInstanceSeparation::
  test_separate_interceptors_have_separate_query_lists`; the tree was grepped
  first to confirm nothing referenced the old name.

  **Relationship to entry 18:** 18 established that per-request state *is
  stored in* contextvars — true, and unchanged. This entry establishes that
  contextvars is *not* what isolates concurrent requests. The two are separate
  questions and 18 is not evidence for this one.

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
- **Resolved:** 2.2.0 (S4) - **R1, wired.** A `build_interceptor()` factory in
  `interceptor.py` reads `CAPTURE_STACK_TRACES` and `STACK_TRACE_EXCLUDE` from
  `get_config()` (falling back to packaged defaults with a logged warning when
  config is unreadable) and constructs the interceptor. All nine construction
  sites call it — the seven bare ones plus the two middleware sites, which stop
  reading config inline. `QueryInterceptor.__init__` is unchanged, keeping the
  "the interceptor does not read configuration itself" docstring
  (`interceptor.py:47-49`) true and leaving explicit construction available to
  tests and library users. The candidate fix this entry proposed — have
  `__init__` read `get_config()` itself — was declined for that reason: a
  factory keeps the class config-free. `TestCaptureStackTraces` pins
  `CAPTURE_STACK_TRACES: False` at each of the seven previously-ignoring sites,
  each with a `True` positive control.

## 28. The async-ORM capture claim is true on one route and false on the other

- **Evidence:** measured 2026-07-27 during S7, on Django 6.0.7 and 4.2.30.
  `docs/guides/async-support.md:85` states that the interceptor's
  `execute_wrapper` captures `aget`, `acreate`, `acount`, `aexists` and async
  iteration "identically", without naming a route. The same page documents two
  routes: the `MIDDLEWARE` chain, and the hand-embedding route at `:64`
  (`QueryDoctorMiddleware(async_get_response)`). The claim is **true on the
  chain route** — all five surfaces capture, counts 1/2/2/2/2
  (`tests/test_asgi_middleware_chain.py::TestASGIAsyncORMCapture`) — and
  **false on the hand-embedding route**, where all five capture nothing
  (`::TestDirectEmbedAsyncORMNotCaptured`, `:315`), against a sync-view positive
  control through the same driver that captures 2.
- **Cause:** `__acall__` installs the `execute_wrapper` on the event loop
  thread's connection (`middleware.py:166`), while every `a*` method is
  internally `sync_to_async(thread_sensitive=True)`, so the ORM runs on an
  executor thread holding a different `connections["default"]`. This is the same
  cause as the `diagnose_queries()` failure already documented on the same page
  at `:95`, and the same cause as entry 22 — thread-local connection registry,
  not contextvars.
- **Impact:** a user following the hand-embedding route documented at `:64`
  gets an empty report from async ORM calls and no signal that anything is
  wrong. The page's own caveat at `:78` ("you own the thread placement") covers
  the mechanism but does not connect it to the async-ORM claim 7 lines later, so
  the two read as independent.
- **This is the fourth ASGI claim of this release measured false**, after the
  two corrected in 2.1.2 and entry 22's `diagnose_queries()` recommendation.
  Recorded as a rate, not as an incident: every ASGI claim in this package that
  has been measured rather than reasoned from the mechanism has needed
  qualification, so the remaining unmeasured ASGI claims should be treated as
  unbacked rather than as probably fine.
- **Proposed disposition:** a route qualifier on `:85` pointing at the `:78`
  caveat. **Not deletion** — the claim is true on the `MIDDLEWARE`-chain route,
  which is the route the page recommends and the one essentially every user is
  on. **Destination: S8** (docs corrections). Deliberately not fixed in S7: S7
  is scoped to measurement, and this is the fourth false claim of the release,
  which is a finding to record rather than to fix in passing.
- **Resolved:** 2.2.0 (S7b) — **qualified, not deleted**, as proposed. `:85` now
  opens with the route ("Through the `MIDDLEWARE` chain, ...") and cites
  `TestASGIAsyncORMCapture` as the measurement, and a warning admonition beneath
  it states the hand-embedding counter-case, gives the thread-placement cause,
  links back to the route section, and cites
  `TestDirectEmbedAsyncORMNotCaptured`. Pulled forward from S8 into S7b because
  S7b was already opening this file for entry 17, and leaving a claim known false
  in a shipped document for the length of another step is not a scheduling
  decision worth making.

  The page already carried a thread-placement caveat for that route at `:78`,
  but seven lines above the async-ORM heading and phrased generally, so the two
  read as independent — which is why an unqualified claim survived a doc sweep
  that had the counter-argument on the same page. The admonition connects them
  explicitly. The anchor it links to was verified present in the built HTML
  (`id="embedding-the-middleware-around-an-async-handler"` in
  `site/guides/async-support/index.html`) rather than assumed from the heading
  text.

  Scope held: one claim. The claim-by-claim audit of this page — four of its
  claims measured false in one release — remains S8's question and was not
  started here.

## 29. `discover_analyzers()` rescans entry points on every call

- **Evidence:** measured 2026-07-27 during S7, while profiling entry 17's
  blocking call. `pipeline.analyze` (`pipeline.py:27`) calls
  `discover_analyzers()` (`plugin_api.py:80`) on **every** invocation;
  `_load_entry_point_analyzers` (`plugin_api.py:103`) walks every installed
  distribution and reads its `entry_points.txt` from disk. Nothing on that path
  caches. Counted directly: 435 `read_text` calls over 5 runs = 87 per run =
  exactly the installed-distribution count. Cost is **flat in query count** — a
  0-query call costs the same as a 100-query call — and scales with installed
  distributions: ~8 ms at 87, ~10 ms at 152. Discovery is 87% of cumulative
  time; analysis proper is sub-millisecond.
- **Impact:** synchronous filesystem I/O on every analyzed request, on **every
  surface** — the sync middleware, `diagnose_queries()`, the pytest plugin, the
  Celery integration and all three management commands — not only the async one
  entry 17 is about. Entry 17 is where it was found, not where it lives.
- **Measured fix:** `functools.lru_cache` on `discover_analyzers`, which takes
  the residual to 0.15-0.80 ms.
- **Four implementation constraints, each measured, each easy to get wrong:**
  1. **Decorate the `def` itself, not a re-export.** `pipeline.py:21` holds a
     separate module-level binding
     (`from query_doctor.plugin_api import discover_analyzers`, used at `:48`),
     so caching by rebinding `plugin_api.discover_analyzers` leaves the pipeline
     path — the only path that matters — uncached.
  2. **Cache a tuple, or return a copy.** The cache hands back the same list
     object and the same analyzer instances on every call (verified: `same list
     object: True`, all seven instances identical). `pipeline.analyze` only
     iterates, so this is safe today, but any caller that mutates the returned
     list corrupts every later call. Sharing the *instances* is separately safe:
     `fat_select.py:64` (`self._threshold_override`, set in `__init__` at `:57`)
     is the only instance attribute assigned anywhere in
     `src/query_doctor/analyzers/`, and it is never mutated during `analyze`.
  3. **`cache_clear()` is part of the contract, not an afterthought.** Mirror
     `conf.py:60-61` (`@functools.lru_cache(maxsize=1)` on `get_config`) and the
     way `tests/test_pipeline.py` calls `get_config.cache_clear()` to keep tests
     isolated.
  4. **The blast radius is three tests, not one.** Only
     `tests/test_plugin_api.py:71` (`test_includes_valid_plugin`) goes red, at
     the `:79` assertion. `:81` (`test_invalid_plugin_skipped`) and `:91`
     (`test_plugin_error_logged`) go **vacuous** — measured,
     `mock_load.called == False` in both, `assert len(result) >= 3` still True,
     warnings logged 0 — so both keep passing while exercising nothing. That is
     the worse failure mode, because nothing goes red to announce it, and a
     future reader who sees only "one test failed" will under-scope the fix.
     Immune, and not to be "fixed" alongside them:
     `tests/test_coverage_gaps.py:283,328`, which patch
     `query_doctor.pipeline.discover_analyzers` outright.
- **Disposition:** land the cache with its `cache_clear()` contract and the
  three-test fix. **Destination: S7b**, a new step. Entry 17 closes in the same
  step and cannot close before it — 17's disposition (b) describes the analysis
  as "a cheap inline post-response step", which is not true at ~8 ms.
- **Resolved:** 2.2.0 (S7b.1). `functools.lru_cache(maxsize=1)` on a private
  `_discover_analyzers_cached()` (`plugin_api.py:81`); the public
  `discover_analyzers()` (`:113`) returns `list(...)` of it. Measured on this
  tree, before and after, at 87 installed distributions:

  | | before | after |
  |---|---:|---:|
  | `_load_entry_point_analyzers` calls, over 5 `discover_analyzers()` | 5 | 1 |
  | `entry_points.txt` reads, over 5 calls | 435 | 87 |
  | `pipeline.analyze([])`, 50 reps | 7.860 ms/call | 0.302 ms/call |

  `435 / 5 = 87` = the installed-distribution count exactly. The timing is on an
  **empty** query list, so every millisecond of it is discovery — which is what
  makes "the cost is discovery, not analysis" a measurement rather than an
  inference.

  **Blast radius wider than this entry recorded.** Seven surfaces route through
  `pipeline.analyze` — `middleware.py:246`, `context_managers.py:48`,
  `celery_integration.py:158`, `pytest_plugin.py:185`,
  `project_diagnoser.py:242`, `check_queries.py:213`, `fix_queries.py:196` — and
  `project_diagnoser.py:242` sits inside `_diagnose_url`, called once per
  discovered URL from the loop at `:170`. A project scan therefore paid a **full
  entry-point rescan per URL**. That is the strongest single piece of evidence
  for the fix and it was not in this entry as written.

  Against the four constraints:
  1. **Satisfied structurally rather than literally.** The `lru_cache` sits on
     the private function; the public `discover_analyzers` — the name
     `pipeline.py:21` binds at import — routes through it, so there is no
     uncached second path to miss.
  2. **Copy, not tuple, and the copy is free.** `list(...)` of seven analyzers
     costs **0.0971 µs**, four orders of magnitude below the 0.302 ms residual it
     protects. Returning a tuple would have been a breaking change to a
     `list[BaseAnalyzer]`-annotated function on the public plugin surface, bought
     with nothing.
  3. `discover_analyzers.cache_clear()` is attached and documented as contract.
     **`cache_info` is deliberately not attached**: it reports hit/miss counts,
     which is diagnostic rather than contractual, and exposing it invites callers
     to depend on cache statistics this package does not want to promise.
     `cache_clear` is attached because the cache is only safe to introduce if
     callers can drop it.
  4. **Three tests, and vacuity is now structurally impossible.** All the tests
     in `tests/test_plugin_api.py` run under a module-level autouse fixture that
     clears the cache before **and after** each test, and each patched test
     asserts `mock_load.called`. Clearing *after* is not symmetry: a result
     cached under a patch would otherwise leak into
     `test_analyzer_discovery_wiring.py:67`'s exact-count assertion.

  Caching *instances* was verified safe on the config axis, not assumed:
  `analyzers/fat_select.py:57` is the only `__init__` in all of
  `src/query_doctor/analyzers/` and it reads no config, while `is_enabled()` and
  `_get_threshold()` read `get_config()` at analyze time — so `override_settings`
  still takes effect through a cached instance. No caller mutates the returned
  list: `pipeline.py:48` iterates, `test_analyzer_discovery_wiring.py:53,67` read
  names and length, and `examples/scripts/08_custom_analyzer.py:44` is inside a
  printed string.

  **Do not read a scaling law into the wall-clock number.** The *read count*
  scales with installed distributions (87 per call at 87 distributions, 142 at
  152). Wall time does not track it: 87 distributions gave 7.860 ms/call here and
  152 gave 7.684 ms/call on the reviewer's machine. Two data points contradict a
  scaling law, so both the shipped `CHANGELOG` entry and this record scope the
  timing to the environment that produced it.

  One consequence recorded for whoever reads entry 30 next: `cache_clear()` in
  tests is untypechecked today, because the gate runs `mypy` on `src/` and
  `scripts/` only. Harmless now; it becomes an error the day tests enter mypy's
  scope, and the attribute needs a typed shim then.

## 30. `test_plugin_error_logged` does not assert on logging

- **Evidence:** `tests/test_plugin_api.py:91-102` (def at `:92`). The docstring
  reads "Plugin that raises should log a warning". The body sets
  `mock_load.side_effect`, opens
  `caplog.at_level(logging.WARNING, logger="query_doctor")` (`:98`), and then
  asserts only `assert len(result) >= 3` (`:102`). `caplog` is never read.
- **Impact:** the graceful-degradation half is genuinely covered — a raising
  plugin loader does not take down discovery. The logging half, which the
  test's name and docstring both promise, is asserted nowhere, so the warning
  in `discover_analyzers`'s except branch (`plugin_api.py:95`) could be deleted
  and this test would stay green. Same shape as entry 15 (an assertion that cannot fail), one layer
  over: here the assertion is real but is not the one advertised.
- **Disposition:** add the missing assertion on `caplog.records` (renaming the
  test to what it actually covers is the worse option — the warning deserves a
  pin). Pre-existing and independent of entry 29: true today, before any
  caching change, and it would remain true if entry 29 were never done. Filed
  separately for that reason rather than folded into 29's three-test fix.
  **Destination: S9b** (tooling tests, with entries 7, 8, 9 and 10).
- **Resolved:** 2.2.0 (S7b.2). The test now asserts exactly one `query_doctor`
  WARNING record, its message, and that `exc_info` is present — the traceback is
  the actionable half, since without it a user learns that *some* plugin failed
  and nothing about which one or why. The `len(result) >= 3` assertion stays and
  is labelled as the graceful-degradation half rather than standing in for both.
  Pulled forward from S9b for the same reason as entry 28: S7b.1 already had this
  file open and had just made two of its siblings temporarily vacuous, so fixing
  the third assertion gap in the same module was cheaper than scheduling it.

  Verified falsifiable by breaking the thing it tests: replacing the
  `logger.warning` with `pass` fails the test at `assert len(warnings) == 1` ->
  `assert 0 == 1`.

  **The ordering against entry 29 was demonstrated, not merely obeyed.** Running
  the identical assertion with the discovery cache warm and never cleared:

  ```
  mock_load.called: False
  query_doctor WARNING records: 0
  len(result): 7
  assert len(warnings) == 1
  E  assert 0 == 1
  ```

  A cache hit returns without entering the `try`, so the patched loader is never
  called, never raises, and no warning is emitted — the assertion would have
  failed for a reason with nothing to do with the logging it tests. Had this
  entry been fixed before entry 29, the test would have been rewritten to
  accommodate a cache that did not exist yet. The two entries are the same loop
  seen from both ends: the warning entry 30 fails to assert on is the warning
  entry 29's cache silences.

  Line reference moved during the fix: the warning was at `plugin_api.py:95` when
  this entry was filed; S7b.1 moved the `try` into `_discover_analyzers_cached`
  and it is now at `:105`.

## 31. `docs/guides/async-support.md` claim inventory — backing status of all 25 claims

Filed by S8 as **inventory only**. No claim in this file was edited by S8; the
point is to size the fix effort before spending it. Four claims in this one
file measured false during 2.1.2, which is why it gets a claim-by-claim pass
rather than a spot check.

**Destination:** the asserted-unbacked table below is the work item. Closable
within 2.2.0 if the two flagged claims measure true; otherwise each false one
becomes its own entry with a named disposition, as entry 28 did.

### Test-backed (no action)

| Line | Claim | Backing |
|---|---|---|
| 20 | `sync_capable = True`, `async_capable = False` | `test_async_support.py:76,80`; source `middleware.py:111-112` |
| 26 | `ASGIHandler` opens a per-request `ThreadSensitiveContext`; requests do not serialise | `test_asgi_middleware_chain.py:221`, `:355` |
| 28 | `AsyncClient` gets no such context; capture still works | `TestAsyncClientCapture` `:402-425` |
| 41 | Captures `async def` and sync views alike | `TestASGICapture:201`, parametrized `:209` |
| 46-49 | 2.0.0-2.1.1 either crashed the chain or captured nothing | `TestASGIChainServesRequests:135`, `RESPONSE_TOUCHING_STACKS:165`, `PASS_THROUGH_STACKS:178` |
| 64, 74 | Hand-embed route reaches `__acall__`; detected at construction | `TestDirectInstantiationPredicate:427,437,465` |
| 85 | Five async ORM methods captured via the `MIDDLEWARE` chain on Django 6.0 and 4.2, counts plus per-method SQL fragment | `TestASGIAsyncORMCapture:277-313` |
| 89-91 | Those same five capture nothing on the hand-embed route | `TestDirectEmbedAsyncORMNotCaptured:315-341`, with positive control at `:343` |
| 101-103 | `diagnose_queries()` captures nothing inside `async def` | entry 22; cause matches `middleware.py:100-108` |

### Source-traceable but ungated

- **`:79` — the three timing figures.** "0.14 ms for a request that issued
  none, 2.2 ms at 100 queries and 10.3 ms at 500."

  **These are not unsourced.** S8's plan first reported them as having no
  origin in the tree; that was an artifact of grepping the rounded strings.
  They trace exactly to the measured table in entry 17 — `0.144`, `2.177`,
  `10.275` — which the doc rounds correctly, and both surfaces carry the same
  "on one development machine" provenance. The adjacent "roughly linearly"
  matches entry 17's re-measurement too. So the claim is accurate and its
  origin is recorded.

  **The gap is that nothing re-measures it.** There is no benchmark script, no
  test, and no row in `claims.json`. `scripts/claims_check.py` did not catch
  this and could not have: it checks only claims registered in the manifest, so
  an unregistered number is invisible to it rather than failing. The figures
  would go stale silently the moment `pipeline.analyze` changed cost — which is
  precisely what happened to the *previous* generation of this claim, whose
  "flat in query count" survived until entry 29's cache falsified it.

  **Consequence for the fix:** this one must be re-measured and registered, not
  reworded. Rewording preserves exactly the property that makes it rot.

### Asserted-unbacked (the fix surface)

| Line | Claim | Note |
|---|---|---|
| ~~**42**~~ | Captures queries issued inside `sync_to_async`-wrapped helpers | **S9: this row was wrong.** It was already backed — see the correction below. Measured, partially false as *worded*; now qualified and split to entry 32. |
| ~~**129**~~ | `@diagnose` on an `async def` returns the coroutine object and the capture context exits before the body runs | **S9: measured TRUE**, both halves, by `tests/test_decorators.py::TestDiagnoseOnCoroutineFunctions`. Now test-backed. |
| 105 | "The interceptor's per-instance `ContextVar` storage is correct and does propagate across `await`" | Same class as entry 24. Not currently discriminable, for the reason recorded there. S8's probe 1 shows a discriminating test *is* constructible for a shared store — but no code path shares one. |
| ~~22~~ | Django keeps DB connections in thread-local storage | **S9: cited** — Django databases/connection-management docs plus `django.db.utils.ConnectionHandler`. |
| ~~24~~ | "This is how Django adapts *every* sync-only middleware under ASGI" | **S9: cited and narrowed** — the universal "every sync-only middleware" is now scoped to middleware declaring `async_capable = False`, citing Django's async-middleware docs and `BaseHandler.load_middleware`. |
| 32-34 | Middleware listed before query-doctor runs in sync mode too; "does not affect request concurrency" | Asserted |
| 36 | "not a change relative to 2.1.1" | Asserted |
| 78 | Hand-embed route: "you own the thread placement" | Consistent with `:89-91` but not separately tested |
| 79 | "The `MIDDLEWARE`-chain path does not have this property at all" | Asserted; distinct from the figures above |
| 109 | `diagnose_queries()` works inside a `def` view served under ASGI | Example only, no test |
| 123 | `async with diagnose_queries()` raises `TypeError` | No test located |
| 162-164 | `@query_budget` on coroutines unsupported; connection-pooler compatibility; raw `asyncpg` uncaptured | Asserted |

### Size of the effort

One figure set to register (`:79`), one entry-24-class assertion (`:105`), and
twelve asserted-unbacked claims of which **`:42` and `:129` are the two most
likely to be false** and should be measured before any wording is touched. The
remainder are upstream-Django facts or scope statements where a citation, not a
test, is the appropriate backing.

### S9 progress — measured, with one correction to this entry

`:42`, `:129`, `:22` and `:24` are closed; `:79` and `:105` remain, which is why
this entry stays open.

**`:42`'s row in the table above was wrong, and it was the row this entry
flagged as most likely false.** It was already fully backed when the inventory
was written. `tests/testapp/views.py::async_probe` issues its query through
`await sync_to_async(_run_one_query)()`, and
`TestASGICapture::test_both_view_flavours_captured` drives it through a real
`ASGIHandler` asserting the query is captured;
`test_middleware_and_view_share_thread_and_connection` additionally pins the
mechanism the claim names. The inventory missed it because it searched for
tests by *name and keyword* rather than by *behaviour*, so a test that exercises
a claim without naming it was invisible. That is the same method failure that
produced the `:79` error in this entry — two wrong rows from one cause, which is
the more useful finding than either row.

What was genuinely wrong with `:42` was its *wording*, not its backing: it
claimed capture for `sync_to_async` unconditionally. Measured both ways, the
qualification is real — filed as entry 32 rather than reworded in passing.

`:129` measured **true**, both halves.

## 32. `async-support.md:42` claims `sync_to_async` capture unconditionally

Split out of entry 31 in S9 rather than silently reworded, per the rule that a
claim measuring false gets its own record.

- **Evidence:** `docs/guides/async-support.md:42` listed "Captures queries
  issued inside `sync_to_async`-wrapped helpers" with no qualification, and the
  Mixed Sync/Async section stated the same. `sync_to_async` accepts
  `thread_sensitive`, defaulting to `True`.
- **Impact:** true for the default, false for `thread_sensitive=False`. That
  variant runs the helper on a general executor thread, which resolves a
  different thread-local `connections["default"]` than the one the
  `execute_wrapper` is installed on, so its queries are never captured. Same
  cause as entry 22 and as the hand-embedding limitation. A user who passes
  `thread_sensitive=False` for throughput would get a silently empty report.
- **Resolved:** 2.2.0 (S9) — measured, then qualified. Both halves pinned by
  `tests/test_asgi_middleware_chain.py::TestSyncToAsyncThreadSensitivity`: one
  query captured for the default, zero for `thread_sensitive=False`. The
  negative test also asserts the thread *and* connection identities differ, so
  it cannot pass on a harness that captures nothing; the default-case test is
  its positive control. The docs now carry the exception explicitly with both
  call forms shown.
