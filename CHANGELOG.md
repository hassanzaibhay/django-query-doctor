# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

> **Two sections below describe releases that were never published: `[1.0.3]`
> and `[2.0.1]`.** There are ten version sections here and eight git tags, and
> the two without a tag are the same two with no artifact on PyPI. If you are
> choosing a version to install, those two are not installable; use `1.0.2` or
> `2.0.0` respectively. The sections are left in place rather than deleted,
> because released sections are never edited retroactively -- this note is the
> additive remedy.
>
> Section dates are the PyPI upload date. That holds exactly for 2.1.0 through
> 2.2.0. Three earlier headings are within a day of their upload, which is a
> timezone artifact (PyPI reports UTC, uploads were from UTC+5) and not an
> error; `2.0.0` is dated two days before its upload and is simply wrong.

## [Unreleased]

### Fixed
- **The 2.3.0 upgrade notes were wrong about `--fail-on-regression`.** They
  stated it was "unaffected: fewer findings cannot create a regression", four
  paragraphs after stating that the N+1 prescription text had changed. A
  baseline snapshot keys each issue on `analyzer : file_path : message`
  (`baseline.py`), so the changed message rehashes every N+1 entry: the same
  unfixed finding is reported as *resolved* under its old key and as a *new
  regression* under its new one, and a CI job running
  `--baseline=... --fail-on-regression` exits 1 with no code change. The
  identical mechanism was documented correctly for the 2.1.x upgrade in the
  same file. `UPGRADING.md` now says so, and names the regeneration step.
- **`check_serializers` no longer prescribes a queryset call that raises.** Of
  the seven places `serializer_method` builds a finding, only one established
  that the attribute it was about to name was a relation. The other four that
  prescribe `prefetch_related` took the attribute straight from the source, so
  `get_theme(self, obj): return obj.payload.get("theme")` produced
  `prefetch_related('payload')`, which raises `AttributeError`; a `CharField`
  produced `prefetch_related('title')`, which raises `ValueError`. All four now
  resolve the attribute against `Meta.model`, or against Django's `_set`
  reverse-accessor suffix when the serializer has no model, and suppress the
  finding when neither establishes a relation.
- **The deep-chain check no longer prescribes `select_related` for relations it
  cannot take.** `select_related` follows a single forward join, so
  `obj.categories.name` on a many-to-many produced
  `select_related('categories')` and `FieldError` when followed. It now
  requires a forward `ForeignKey` or a `OneToOneField`, and a serializer with
  no model gets no prescription here at all, because a reverse accessor is a
  prefetch signal rather than a `select_related` one.

## [2.3.0] - 2026-08-01

### Added
- `reset_turbo_override()` is exported from `query_doctor.turbo`, alongside
  `set_turbo_override()` and `get_turbo_override()`. 2.2.0's release notes
  pointed users at `set_turbo_override()` as the replacement for the removed
  `turbo.patch.set_thread_override`, but the token it returns could not be
  reset from outside the module: resetting a `ContextVar` needs the variable
  itself, and `_turbo_override` is private. The manual override is now
  actually usable, is documented in the QueryTurbo guide, and is covered by
  tests. `turbo_enabled()` and `turbo_disabled()` now route through
  `set_turbo_override()` rather than setting the ContextVar directly, so the
  helper the changelog recommends has a caller in the package.
- The console reporter prints a one-line note when a report contains both an
  N+1 finding and a fat SELECT finding, saying that fixing the N+1 widens the
  base query and that the fat SELECT findings should be re-read afterwards.
  Prescriptions are now returned in the order they should be applied rather
  than in analyzer-discovery order: N+1 first, fat SELECT last.
- `check_serializers`' loop check and the N+1 analyzer's relation resolution
  are covered by tests that *run* the prescribed queryset call against real
  Django, so a prescription naming a field that does not resolve fails with
  the error Django raises rather than passing a string comparison.

### Changed
- **`docs/deep-dive/architecture.md` no longer shows a fabricated console
  block.** The section illustrated the console reporter with hand-written
  output the tool has never produced: three of its four distinctive strings
  (`QUERY DOCTOR REPORT`, `N+1 Query Detected`, `match fingerprint`) appear
  zero times in `src/`, and the fourth (`Total queries:`) appears on 3 lines
  but only as part of a differently shaped summary line. It is replaced with
  an excerpt of the real committed capture, and the surrounding prose now
  describes the Rich and plain paths as the different renderings they are
  rather than claiming they print the same block.
- **The QueryTurbo speedup table is re-measured and correctly labelled.** The
  published figures (123x / 153x / 294x / 374x / 214x / 1,050x) did not
  reproduce with the documented command: every value came back 30-50% lower,
  and the complex scenario measured 523.4x -- below the 727x floor that the
  "hardware variance" note disclosed, so the caveat failed too. The table is
  replaced with a single run on a named machine, is explicitly labelled as the
  `compilation_only` section of `benchmarks/results.json`, and the docs now
  state up front that the last line the command prints is the *end-to-end*
  result and comes out below 1x on SQLite in-memory, explaining why that is
  expected rather than a defect. That end-to-end figure is given as a run with
  its observed run-to-run spread rather than as a single value, since publishing
  one point estimate as a constant is the fault this entry was about. The table
  was duplicated on two pages; it now lives on one, with the other linking to
  it.
- `docs/guides/auto-fix.md` lists all nine `IssueType` members instead of
  seven, and marks which are selectable via `--issue-type`. The guide said
  "five of the seven issue types", omitted `serializer_method_field` (shipped
  in v2.0) and `write_n_plus_one` (shipped in 2.2.0), and described
  `--issue-type complexity` as accepted-but-fruitless when argparse rejects it
  outright -- contradicting the guide's own statement two paragraphs below that
  an unknown value "is rejected with an error before anything runs".
- `docs/api/reference.md` autodocs all eight analyzers. `WriteNPlusOneAnalyzer`
  and `SerializerMethodAnalyzer` were absent, so the API reference disagreed
  with the two other pages that count the analyzer set correctly.
- **`models_meta` is documented as reserved and always `None`.** The parameter
  is part of the `BaseAnalyzer` contract and appears in all eight analyzers,
  but nothing in the package passes it: the only call site,
  `pipeline.analyze()`, calls `analyzer.analyze(queries)`. `base.py` described
  it as "for enhanced analysis" and the plugin guide said it "may be `None`" --
  both of which invite a plugin author to write code against a value that never
  arrives. All six documentation sites and the base-class docstring now say it
  is always `None`. Removing the parameter would break third-party analyzer
  signatures, so it happens in a major version; see **Deprecated** below, where
  that removal is announced for 3.0.0.
- Three documents quoted the `missing_index` TODO comment with an em dash the
  fixer does not emit (it writes an ASCII hyphen). Corrected, and pinned by a
  test that asserts the emitted separator *and* sweeps every tracked markdown
  file for a recurrence -- a test on the emitted string alone would have stayed
  green throughout, because the defect was never in `src/`.
- `docs/guides/async-support.md` backs or withdraws the claims its own
  inventory flagged as asserted-unbacked. `async with diagnose_queries()`
  raising, and `@query_budget` on a coroutine not enforcing, are now measured,
  each with a control. Backing the first corrected it: the guide said it raises
  `TypeError`, which holds only on Python 3.11 and later -- on 3.10 the same
  code raises `AttributeError: __aenter__`, so a reader on the oldest supported
  interpreter writing `except TypeError` would not have caught it. Both types
  are now named, in both places the guide states the limitation. The
  concurrency and "not a change relative to 2.1.1" claims cite the tests that
  establish them. The connection-pooler and
  `asyncpg` limitations now say plainly that neither is exercised here. The
  claim that the interceptor's `ContextVar` storage "does propagate across
  `await`" is withdrawn rather than reworded: no code path shares an
  interceptor between contexts, so no test could distinguish it from thread
  separation, and the thread-locality of Django's connection registry is what
  decides the outcome anyway.
- `CHANGELOG.md` gains a note at the top recording that `[1.0.3]` and
  `[2.0.1]` describe releases that were never published -- ten version sections
  against eight git tags, and the two without a tag are the two with no PyPI
  artifact. The sections are left in place; released sections are not edited
  retroactively, so the note is the additive remedy.
- **`benchmarks/` is inside the gates.** The v2.0 QueryTurbo suite sat outside
  the commands, which named `src/ tests/ scripts/`, and failed them: 12 ruff
  errors and 14 mypy errors. Both are fixed and all three gate declarations --
  CI, the pre-push hook, and the contributor docs -- are widened in the same
  change, so the errors cannot be reintroduced. Two waivers are recorded with
  reasons rather than left implicit: `E501` for `benchmarks/report.py`, whose
  long lines are CSS and Chart.js inside an HTML template rather than Python,
  and `attr-defined` for `benchmarks.*`, because the django-stubs plugin
  resolves models against `tests.settings` where the benchmark app is
  deliberately not installed. Nothing shipped is affected: the wheel packages
  `src/query_doctor` only.
- **A new gate keeps `src/` and config free of em and en dashes.** It ships
  green -- the baseline is zero -- which is the cheapest moment to install one;
  the exposure it closes is that the clean state was previously unenforced.
  `scripts/dash_gate.py` classifies by token kind, as CLAUDE.md prescribes,
  flagging only COMMENT tokens and docstring STRING tokens. That makes the
  program-output exemption fall out automatically rather than needing a
  maintained list: `print()` heredocs and `title=` arguments are not
  docstrings. It runs in CI and on pre-push, and is stdlib-only so it needs no
  install. Its own tests feed it dash-carrying input in every flagged position
  *and* in every exempt one, because a gate verified only against a clean tree
  is verified against nothing.
- **The CI matrix exercises the two claimed cells it was skipping.** Python
  3.10 x Django 5.1 and 3.10 x Django 5.2 were excluded despite Django
  declaring `requires_python >= 3.10` for both, so the README badge and the
  trove classifiers claimed combinations nothing tested. Only the two
  genuinely impossible cells remain excluded (Django 6.0 needs 3.12), taking
  the matrix from 16 to 18 jobs.
- Two marketing-register sentences are replaced with checkable statements:
  `comparison.md`'s "provides the most comprehensive CI analysis" now says what
  it does that `nplusone` does not, and `custom-plugins.md`'s "integrate
  seamlessly" now says what integration actually means.

### Deprecated
- **`models_meta` is deprecated. 3.0.0 removes it from the
  `BaseAnalyzer.analyze()` signature.** Nothing has ever populated it. The sole
  call site, `pipeline.py:92`, calls `analyzer.analyze(queries)` for every
  analyzer on every run, so the argument is `None` unconditionally, and all
  eight built-in analyzers ignore it. It is part of the plugin contract rather
  than an internal detail, which is the only reason its removal waits for a
  major version instead of happening in this release.

  **What a third-party analyzer author has to do.** Nothing for 2.3.0: an
  `analyze(self, queries, models_meta=None)` signature keeps working
  unchanged. But since the argument is never passed, you can drop the
  parameter today and be correct on both 2.3.0 and 3.0.0:

  ```python
  # accepted by 2.3.0, required by 3.0.0
  def analyze(self, queries: list[CapturedQuery]) -> list[Prescription]:
      ...
  ```

  If you keep the parameter, remove it when you adopt 3.0.0. If you read the
  value and branch on it, that branch is unreachable today and should go now.
  Do not add a `None` check waiting for a value to arrive, because none will.

  The documentation that described the parameter was corrected in this release
  rather than left to the deprecation: six doc sites and the `base.py`
  docstring said "optional model metadata" or "may be `None`", which invited
  exactly that `None` check. They now state that it is reserved and always
  `None`, and `docs/guides/custom-plugins.md` and `docs/contributing.md` carry
  this removal notice.

### Fixed
- **`check_queries --url` no longer exits 0 for a URL that does not resolve.**
  Both a `Resolver404` and any exception raised inside the view were swallowed
  identically, and the command went on to report zero captured queries and
  exit 0. For a tool whose CI story is "fail the build on new issues",
  analysing nothing was indistinguishable from finding nothing, so a typo in a
  `--url` argument turned the gate green permanently. Each case now raises a
  `CommandError` with its own wording, naming the URL. **This can turn a
  previously-green CI gate red.** If your pipeline runs `check_queries --url`
  against a path that does not resolve, or against a view that raises, the
  build will now fail where it previously passed -- which is the point of the
  fix. Check the URL before upgrading.
- **The N+1 analyzer no longer prescribes a field that raises `FieldError`.**
  On a repeated primary-key lookup the field name was derived by string-slicing
  the table name (`testapp_author` -> `author`) whenever no foreign key was
  found, and the foreign-key path was no safer: it searched every model in the
  project for a field pointing at the target table, with no knowledge of which
  model the caller was iterating. `Author.objects.get(pk=pk)` in a loop
  prescribed `.select_related('author')`, which raises. A relation is now named
  only after it resolves through `Model._meta.get_field()`, and only when an
  earlier query in the same capture read the table that declares it -- so a
  genuine forward-FK N+1 still gets `select_related`, and a bare `get(pk=...)`
  loop gets the advice that actually applies: fetch the rows in one query with
  `in_bulk()` or `filter(pk__in=...)`. The prescription text changes for both
  cases, and it now names the model the call belongs to.
- The reverse-foreign-key branch of the same analyzer had the same defect,
  found while fixing the above: for `WHERE "book"."author_id" = ?` it read the
  field name off the column (`author`) and prescribed
  `prefetch_related('author')` on what is necessarily an `Author` queryset. It
  now resolves the reverse accessor on the far side of the relation
  (`books`) and validates it against that model.
- The `serializer_method` analyzer no longer prescribes `prefetch_related()`
  for a loop over a scalar attribute. `for ch in obj.title` over a `CharField`
  produced `prefetch_related('title')`, which raises `ValueError`. The
  bare-attribute loop branch now confirms the attribute is a relation --
  through `Meta.model` when the serializer has one, otherwise through Django's
  own `_set` reverse-accessor suffix -- and emits nothing when it cannot.
- The `duplicate` analyzer no longer reports a re-read that follows a write to
  the same table. Read, write, read back is ordinary Django, and following the
  prescription ("assign the result to a variable and reuse it") returns the
  pre-write row. This was the one finding in the set whose fix was a
  correctness regression rather than a missed optimisation, so the group is
  suppressed rather than reworded.
- `fat_select` no longer counts a joined table's columns against the base
  table. The column count came from the whole select list while the table name
  came from the `FROM` clause, so `Book.objects.select_related("author")`
  reported 13 columns "from testapp_book" when Book has 8, and the prescribed
  `.defer()` addressed only a fraction of them.
- `fat_select` no longer fires on a single-row lookup. `Book.objects.get(pk=1)`
  returns one row and hit the default threshold of 8 with the model's own
  columns, so every read of an ordinary Django model produced a finding. A
  primary-key equality test or an explicit `LIMIT 1` is now exempt.
- `extract_tables()` reports the target table of `UPDATE`, `INSERT INTO` and
  `DELETE FROM` statements. It matched only `FROM` and `JOIN`, so every write
  reported no tables at all and was invisible to any analyzer reasoning about
  which tables a statement touches.
- `write_nplusone`'s IN-list and VALUES counters are aware of quoted string
  literals. `WHERE "name" IN ('a,b')` counted two items, so the statement was
  classified as a bulk write and the finding was suppressed. Reaching this
  needs a literal inlined into the SQL through `.extra()`, `RawSQL` or a
  hand-written `cursor.execute()`, because Django's ORM parameterises.
- Embedding the middleware by hand around an async handler now emits a
  `QueryDoctorWarning` instead of silently reporting zero. On that route the
  `execute_wrapper` is installed on the event loop thread's connection while
  Django runs async ORM work on a separate executor thread, so `aget`,
  `acreate`, `acount`, `aexists` and async iteration were never captured and
  nothing said so. The condition is probed by asking the executor whether it
  can see the interceptor, not predicted, so an async handler doing sync ORM
  inline stays quiet. The warning describes the wiring rather than one
  request, so it is emitted at most once per middleware instance. Suites that
  escalate warnings to errors will fail on a hand-embedded async middleware.
- Removed the dead `_severity_color()` helper from the project report
  generator, and two parameters that were declared and never read:
  `_suggest_simplification`'s `score` (whose docstring documented it) and
  `_render_executive_summary`'s `total_warnings`. 2.2.0 removed five dead
  symbols, so a reader could reasonably assume the sweep was complete.
- `tests/test_management_commands.py` drove `check_queries` at `/test/`, which
  is absent from the test URLconf, so nine tests analysed zero queries and
  asserted against an empty report. `test_baseline_no_regression_exits_zero`
  compared an empty baseline against an empty run and would have passed with
  `--fail-on-regression` deleted; it is rebuilt around a non-empty baseline and
  paired with a negative control that fails when a regression is introduced.
  `diagnose_project`'s baseline path -- documented in the baseline guide and
  previously the largest uncovered block in the package -- now has tests for
  save, no-regression, regression and resolved-issue reporting.
- **The example artifacts no longer ship the author's local absolute paths.**
  `examples/outputs/report.{html,json}` and
  `examples/screenshots/*.capture.txt` carried `C:\Users\<user>\...` and a
  pytest fixture directory including a Windows account display name, across 20
  lines in 4 files. These are generated artifacts committed exactly as
  produced, and they ship inside the sdist, so the paths were published.
  `scripts/regen_examples.py` now normalizes them -- the repository root
  becomes a repo-relative path with forward slashes, the fixture directory
  becomes `<tmpdir>` -- and asserts before writing that nothing leaked. All
  four artifacts are regenerated. The published 2.2.0 sdist is immutable and
  keeps its copies permanently; this fix applies from the next release
  onwards. The artifacts were **not** hand-edited: hand-editing a generated
  capture is what produced the fabricated files `51c72cd` had to delete.
- `tests/test_svg_capture_sync.py` covers the two artifacts it never touched
  (`report.html` and `report.json`), asserts that no generated artifact
  carries an absolute local path in any of its spellings, and adds the
  staleness check that was missing: both captures are regenerated into a
  temporary directory and diffed against the committed copies, with durations
  masked because they legitimately differ between runs. The staleness check
  was only possible once the paths were normalized, since the fixture
  directory's counter changed on every run. It immediately earned its place:
  the console capture had drifted from the N+1 prescription wording changed
  above, and the transcription in `examples/generate_svgs.py` was corrected
  rather than the test relaxed.

## [2.2.0] - 2026-07-30

### Added
- An eighth built-in analyzer, `write_nplusone`, detects repeated single-row
  writes — the `.save()`, `.create()` or `.delete()` in a loop that issues one
  round trip per object. The other seven analyzers all examine `SELECT`
  statements, so this is the first one that fires on code doing no reads at
  all: an import job, a bulk status update, a fan-out of rows. It prescribes
  the bulk equivalent (`bulk_create()`, `bulk_update()`, a queryset `update()`
  or `delete()`), naming the model where the table resolves to one. Enabled by
  default at a threshold of 3 identical writes; configure under
  `ANALYZERS.write_nplusone`, and suppress individual findings with an
  `ignore: write_n_plus_one:<path>` rule in `.queryignore`. Transaction control
  statements are excluded, so a request opening several transactions is not
  reported. `fix_queries` does not rewrite these findings — the fix is a
  multi-line restructure, not a single-line edit, the same reason `complexity`
  has no fixer. See the [Write N+1 analyzer guide](https://hassanzaibhay.github.io/django-query-doctor/analyzers/write-nplusone/).
- The `query_doctor` pytest fixture now produces observable output. A
  `pytest_terminal_summary` hook prints a `query_doctor` section at end of
  session: one header line with the number of fixture-using tests observed and
  how many were clean, then one line per test that had findings. Tests with zero
  issues produce no line, so the section stays proportionate to the problems
  found. Previously the fixture's report was populated in a teardown finalizer
  and then discarded unread, giving the fixture no observable effect. The
  teardown timing is unchanged, so `diagnose_queries()` remains the tool for
  assertions inside a test body; the fixture's own runtime warning about that is
  unchanged.
- `docs/guides/async-support.md` now documents the hand-embed route — building
  `QueryDoctorMiddleware` directly around an async `get_response`, so `__call__`
  awaits `__acall__` — and gives its measured cost. The route itself is
  unchanged and is not new; what is new is that the guide describes it, states
  the two caveats that apply to it, and quantifies the one that bites: analysis
  runs inline on your event loop and blocks it for the duration. The guide
  publishes a table — 0.14 ms at 0 captured queries, 6.5 ms at 100, 32.0 ms at
  500 — alongside the machine, the Django version, the analyzer count, the
  `.queryignore` rule count and the full workload composition, because every one
  of those changes the answer: the grouping analyzers are O(distinct
  fingerprints) rather than O(queries), and per-query cost is dominated by how
  much SQL each analyzer parses. A narrow-`SELECT` workload costs 3.2x to 3.5x
  less than a wide one at the same count. `python -m scripts.bench_analyze`
  regenerates every published number, including the per-analyzer split behind
  the claim that one analyzer dominates and a `--select-width` flag behind the
  wide-versus-narrow ratio. Scope is stated rather than implied: the figures
  cover the analysis stage only — `__acall__` blocks for analysis **and**
  reporting, and reporters run only when the request produced findings — and the
  0-query row is the pipeline's floor rather than this route's, because the
  middleware returns before analysis when nothing was captured while the six
  other dispatch surfaces do not.

### Changed
- Settings that were accepted and then ignored now take effect.
  `STACK_TRACE_EXCLUDE` reaches the callsite finder, `QUERYIGNORE_PATH`
  selects the `.queryignore` file to load, and `ADMIN_DASHBOARD.max_reports`
  sizes the dashboard buffer. All three were present in the defaults,
  documented as having no effect, and read by nothing.
- An unrecognized `REPORTERS` entry now warns instead of silently producing no
  reporter. A typo and an unsupported name were previously indistinguishable
  from a working configuration. Suites running `-W error` will fail on such an
  entry — see `UPGRADING.md`.
- `.queryignore` is now honoured on every surface that reports findings, not
  only the middleware and `fix_queries`. `check_queries`, `diagnose_project`,
  the pytest plugin, the `diagnose_queries()` context manager and the Celery
  integration consolidate onto a single `pipeline.analyze()`, so a rule behaves
  identically everywhere. Suppression stays at the prescription level: captured
  query counts and timings are never altered, only which findings are reported.
  `sql:` rules additionally match the raw SQL behind a finding, not only its
  description — strictly more suppression. See `UPGRADING.md`.
- `CAPTURE_STACK_TRACES` and `STACK_TRACE_EXCLUDE` are now read at every
  interceptor construction site through a shared `build_interceptor()` factory.
  `CAPTURE_STACK_TRACES: False` previously took effect only in the middleware;
  the seven other surfaces captured stack traces regardless. Default is `True`,
  so only users who set it `False` are affected.
- A `QUERYIGNORE_PATH` that cannot be resolved warns and falls back to
  discovery beside `manage.py`, rather than being dropped silently.
- `diagnose_queries()` now emits a `QueryDoctorWarning` when entered from a
  coroutine. Inside an `async def` function the block has always reported zero
  queries however many it issued — it installs its `execute_wrapper` on the
  entering thread's connection, and Django routes async ORM work to a separate
  executor thread holding a different one — and it did so silently, so the
  empty report looked like a clean result. The capture behaviour is unchanged;
  only the silence is. The predicate is whether an event loop is running on the
  entering thread, so the two shapes that do capture correctly — a `def` view
  served under ASGI, and a `sync_to_async`-wrapped helper — do not warn. Use the
  middleware to diagnose async views. Suites running `-W error` will fail on
  such a block — see `UPGRADING.md`.

- The distribution metadata and the runtime `__version__` can no longer
  disagree. The version was previously declared independently in
  `pyproject.toml` and `src/query_doctor/__init__.py`, with a third copy pinned
  in a test, and nothing derived any one from the others; the module is now the
  single source and the suite fails if the installed distribution reports
  anything else. Note for contributors: bumping the version requires
  `pip install -e "."` before the suite passes, because distribution metadata is
  snapshotted at install time.

### Removed
- `IGNORE_PATTERNS` from the default configuration. No code path ever read it;
  `.queryignore` is the supported way to suppress findings. Leaving the key in
  your settings is harmless — unknown keys are merged and ignored.
- The dead admin-dashboard project-scan integration: `record_project_report`,
  the `_latest_project_report` global, and the unused `project_report` template
  context key. The feature never functioned in any release — nothing wrote the
  global and the dashboard template never rendered it. See the `[1.0.0]`
  historical note.
- `ignore.should_ignore_query`, which had no caller. Its goal — `sql:` rules
  matching raw SQL — is now delivered by `filter_prescriptions` at the
  prescription level.
- Three exception classes that were never raised anywhere in the package:
  `ConfigError`, `AnalyzerError` and `InterceptorError`. They were not exported
  from `query_doctor` and no code path constructed them, but they *were*
  published API: `docs/api/reference.md` autodocs the whole
  `query_doctor.exceptions` module, so all three rendered on the API reference
  page. If you catch them by name, import them from your own module or catch
  `QueryDoctorError` instead — the base class, which every remaining package
  exception still inherits from.
- `turbo.patch.set_thread_override`, a deprecated shim that delegated to
  `turbo.context.set_turbo_override`. It had no caller in the package, no test,
  and no mention in the docs. Use `set_turbo_override` directly.

### Fixed
- Prescriptions no longer point at a line inside Django on Debian and Ubuntu
  system Python. Callsite detection named only three Django ORM modules in its
  exclude list, so `django/db/models/manager.py` (reached by every
  `.objects.create()`) and `django/db/models/base.py` (every `.save()`) were
  skipped only because they happen to live under a path containing
  `site-packages`. Distributions that install to `dist-packages` instead got a
  `file:line` inside Django for those queries, making the prescription
  unactionable — and `fix_queries` would have targeted a Django source file. The
  whole `django/db` package is now excluded by name, and `dist-packages` is
  recognised alongside `site-packages`. If you set `STACK_TRACE_EXCLUDE` to work
  around this, that entry is now redundant but still harmless.
- The Rich console reporter now selects box-drawing characters from the encoding
  of the stream it writes to, not from stdout. Previously, output aimed at a
  terminal whose encoding differed from stdout's could contain characters the
  destination could not encode, garbling the report (or raising on a strict
  stream). It now renders a plain-ASCII box whenever the destination cannot encode
  the Unicode one.
- `docs/deep-dive/comparison.md` no longer asserts that Django's fetch modes are
  "unreleased as of 2026-07-14". That parenthetical would have become false when
  Django 6.1 reaches final release, with no code change and nobody touching the
  file; the linked release notes now carry the status instead. The dated
  disclaimers at `comparison.md:5` and `faq.md:131` are deliberately unchanged —
  those record when a comparison was made and stay true permanently.
- `discover_analyzers()` no longer rescans installed entry points on every call.
  It walked every installed distribution and read its `entry_points.txt` from
  disk each time analysis ran — measured at 87 reads per call against 87
  installed distributions, roughly 8 ms of synchronous filesystem I/O. The cost
  was flat in query count, so a request issuing no queries paid the same as one
  issuing a hundred, and it was paid by every surface: the middleware,
  `diagnose_queries()`, the pytest plugin, the Celery integration and all three
  management commands. `diagnose_project` paid it once per URL pattern. The scan
  is now cached for the process, taking a zero-query `pipeline.analyze()` from
  7.86 ms to 0.30 ms in the same environment. `discover_analyzers()` still
  returns a fresh `list`, so callers may mutate the result as before; a new
  `discover_analyzers.cache_clear()` forces a rescan, which any test patching
  discovery must call.
- `docs/guides/async-support.md` no longer claims that Django's async ORM
  methods are captured without saying on which route. `aget`, `acreate`,
  `acount`, `aexists` and async iteration are captured through the `MIDDLEWARE`
  chain — now measured for all five rather than argued from the mechanism — and
  capture **nothing** when the middleware is embedded by hand around an async
  handler, because `__acall__` installs its wrapper on the event loop thread's
  connection while those methods run on an executor thread holding a different
  one. The section now states the route and carries the counter-case; the claim
  is qualified, not withdrawn.

## [2.1.2] - 2026-07-22

### Changed
- **`QueryDoctorMiddleware.async_capable` is now `False`** (was `True`). This is
  the fix for the two ASGI defects below, not a withdrawal of ASGI support —
  ASGI capture works for the first time in this release. Django adapts
  sync-only middleware with `sync_to_async(thread_sensitive=True)`, which runs
  it in the same thread-sensitive executor Django runs ORM work in; because
  database connections are thread-local, that co-location is what lets the
  interceptor see the queries. Request concurrency is unaffected: Django opens
  a thread-sensitive context per request, so requests do not serialise.
  One consequence worth knowing: Django assigns middleware modes from the
  inside out (`django/core/handlers/base.py`, `load_middleware`), so every
  middleware listed *before* `QueryDoctorMiddleware` in `MIDDLEWARE` now runs
  in sync mode as well. With the recommended last position, that is the whole
  chain. This is standard Django behaviour for any sync-only middleware — a
  great deal of third-party middleware is sync-only — and it does not affect
  request concurrency, but async-capable middleware in your stack will run
  synchronously while query-doctor is installed. Note this is not a change
  relative to 2.1.1: the missing coroutine marker described below already
  forced those middleware into sync mode, while also breaking them.
  `async_capable` is a public class attribute — if you subclass
  `QueryDoctorMiddleware` and re-declare it as `True`, remove that override.
  The `async_capable = False` subclass workaround circulating in issue #11
  becomes redundant but stays harmless.

### Fixed
- **ASGI requests failed with `TypeError: object HttpResponse can't be used in
  'await' expression`** (`HttpResponseServerError` when `DEBUG = False`), raised
  at `django/core/handlers/base.py` in `get_response_async`. The middleware
  declared `async_capable = True` without marking its instance as a coroutine
  function, so Django recorded the handler as async while
  `convert_exception_to_response` wrapped it synchronously. Every middleware
  listed before it then degraded to sync mode and was handed an un-awaited
  coroutine. Three of Django's seven `startproject` defaults —
  `SecurityMiddleware`, `CommonMiddleware`, `XFrameOptionsMiddleware` — touch
  the response object unconditionally and raised on it, so any stack built from
  those defaults with query-doctor anywhere but first position failed on every
  request. Reported in #11 under Daphne + Channels. (`SessionMiddleware`,
  `CsrfViewMiddleware`, and `AuthenticationMiddleware` pass the object through
  untouched on an ordinary GET, so some stacks returned 200 — and hit the next
  defect instead.)
- **No queries were captured under ASGI at all**, in any middleware
  configuration that did not crash, in every release that shipped the
  middleware. The middleware ran on the event loop thread while Django ran all
  ORM work — from `async def` views and sync views alike — in a thread-sensitive
  executor thread. Database connections are thread-local, so the
  `execute_wrapper` was installed on a connection object the queries never
  touched, and every ASGI report was silently empty. A 200 response was not
  evidence the tool had run.
- **Docs:** `docs/guides/async-support.md` recommended `with diagnose_queries():`
  inside `async def` views as an alternative to the middleware. Measured under a
  real ASGI handler, that block reports zero queries — same thread-locality
  cause as the middleware defect, applied to the context manager. The
  recommendation has been removed and the limitation documented. No code change;
  the fix is tracked for a future release.
- The async predicate now comes from `asgiref.sync` rather than `inspect`, which
  is the predicate Django itself uses. `inspect.iscoroutinefunction` does not
  recognise asgiref-wrapped callables before Python 3.12
  (`inspect.markcoroutinefunction` arrived in 3.12), so on Python 3.10 and 3.11
  a `QueryDoctorMiddleware` constructed directly around a `sync_to_async`
  handler took the sync path and ran its analysis stage *before* the view body,
  producing an always-empty report. Not reachable through Django's middleware
  chain — `load_middleware` never hands a `sync_capable` middleware an
  asgiref-wrapped handler — so this affected direct instantiation only.

## [2.1.1] - 2026-07-17

### Added
- `QueryDoctorWarning` (subclass of `UserWarning`), exported from
  `query_doctor` — the package's warning category for runtime advisories,
  filterable by category (`ignore::query_doctor.QueryDoctorWarning`)
  without touching other `UserWarning`s.

### Changed
- The `query_doctor` pytest fixture now emits a `QueryDoctorWarning` when
  requested: its `DiagnosisReport` is populated only during test teardown,
  so assertions on it inside the test body pass vacuously. Use the
  `diagnose_queries()` context manager for in-test assertions. Suites
  running `-W error` (or `filterwarnings = error`) will start failing on
  fixture use — that is the intended signal; suppress just this category
  with `ignore::query_doctor.QueryDoctorWarning`.

### Fixed
- The CI integration guide prescribed in-test assertions on the
  `query_doctor` fixture object and claimed they gate CI — those
  assertions pass vacuously (see the fixture warning above; users who
  copied that sample are exactly who the warning fires on). The sample was
  removed in favour of the pytest guide's `diagnose_queries()` patterns,
  which do fail the test when violated.

## [2.1.0] - 2026-07-16

> **PyPI note:** 2.1.0 is the first release published to PyPI since 2.0.0.
> The `[2.0.1]` and `[1.0.3]` entries below describe versions that were
> merged and tagged in this repository but never uploaded to PyPI (PyPI has
> only 1.0.0, 1.0.1, 1.0.2, and 2.0.0). If you are upgrading from 2.0.0,
> this release is therefore your first with the 2.0.1 `fix_queries --apply`
> corruption fix. If you ever ran `--apply` on 2.0.0, follow the damage
> detection steps in `UPGRADING.md` ("If you ran fix_queries --apply on
> 2.0.0") before trusting that source.

### Upgrading to 2.1.0

`nplusone`, `duplicate`, and `missing_index` now respect their
`ANALYZERS.<name>.enabled` config setting, and every dispatch path
(middleware, pytest plugin, Celery integration, context manager,
`check_queries`/`diagnose_project`) now runs the full set of discovered
analyzers instead of a hardcoded subset. If you use `check_queries
--baseline`, **regenerate your baseline** after upgrading — the widened
analyzer coverage means an old baseline will report newly-covered findings as
regressions until it's refreshed. Comparing against a baseline saved with a
different query-doctor version now prints a non-blocking warning rather than
failing the check. See `UPGRADING.md` for the full 2.1.0 upgrade checklist.

### Added
- `IssueType.SERIALIZER_METHOD_FIELD` — findings from `SerializerMethodAnalyzer`
  (the `check_serializers` static analyzer) now carry their own issue type
  instead of sharing `IssueType.DRF_SERIALIZER` with the deleted runtime
  analyzer. `DRF_SERIALIZER` remains in the enum for plugin/fixer compatibility.

### Fixed
- `nplusone`, `duplicate`, and `missing_index` analyzers now respect their
  `ANALYZERS.<name>.enabled` config setting. Previously, disabling these
  three analyzers had no effect outside `fix_queries` — they still ran and
  reported issues through the middleware, pytest plugin, Celery integration,
  context manager, and `check_queries`/`diagnose_project` commands.
- Middleware, context manager, `check_queries`, Celery integration, and the
  pytest plugin now dispatch through `discover_analyzers()` instead of five
  separate hardcoded, inconsistent analyzer lists (3-5 of the built-ins each).
  Every analyzer's own `is_enabled()` gate (above) is what keeps config
  toggles honored now that dispatch is no longer hand-filtered per site.
- `serializer_method` now has a `DEFAULT_CONFIG` entry, so
  `ANALYZERS.serializer_method.enabled = False` actually disables it.
  Previously there was no config key to set, so the analyzer always ran.
- `fat_select`'s column-count threshold config key was **renamed** from
  `ANALYZERS.fat_select.field_count_threshold` (the key 2.0.x read) to
  `ANALYZERS.fat_select.threshold`, matching the other analyzers. The old
  key is now **silently ignored** — if you set `field_count_threshold` in
  your settings, rename it to `threshold` when upgrading.
- `fix_queries --issue-type` now validates against the five fixer-backed
  issue types instead of silently accepting any string and producing zero
  fixes on a typo.
- `check_queries --baseline` now tracks the query-doctor version the baseline
  was saved with (previously hardcoded to a stale `"2.0.0"` literal) and
  prints a non-blocking warning — not a failure — when comparing against a
  baseline saved with a different version.

### Removed
- Removed `DRFSerializerAnalyzer`, a builtin analyzer that always returned no
  results through any code path reachable from `fix_queries`, the middleware,
  or any management command. Nothing detectable was lost — not because another
  analyzer took the work over, but because this one emitted nothing in any
  reachable path (see the [1.0.0] historical note, and the `fix_queries` entry
  below: `drf_serializer` is never emitted by the runtime pipeline). The
  built-in analyzer count is now 7.

  The static `SerializerMethodAnalyzer` (`check_serializers` command) is
  **not** a replacement for it — the two target different DRF N+1 patterns.
  `SerializerMethodAnalyzer` reads `SerializerMethodField` declarations and
  parses the bodies of the matching `get_<field>` methods; it inspects nothing
  else. `DRFSerializerAnalyzer` aimed at nested serializer fields whose view
  queryset lacked `select_related`/`prefetch_related` — a nested
  `AuthorSerializer()` is not a `SerializerMethodField`, so `check_serializers`
  never looks at it. That pattern is currently uncovered. It was uncovered
  before this removal too, since the analyzer never fired.

## [2.0.1] - 2026-07-13

> **Never published to PyPI.** This version was merged and tagged in the
> repository but not uploaded; PyPI's latest remained 2.0.0. Its changes —
> including the `fix_queries --apply` corruption fix below — first reach
> PyPI in 2.1.0. To check whether a 2.0.0 `--apply` run already damaged
> your source, see `UPGRADING.md`.

### Changed
- `docs/getting-started/configuration.md`: full rewrite. The previous
  example used dotted class paths for `ANALYZERS` and dotted-path
  `REPORTERS`, neither of which the code accepts; documented fictional keys
  (`MIN_SEVERITY`, `QUERY_DOCTOR_ENABLED`, `EXCLUDE_PATHS`,
  `JSON_OUTPUT_DIR`/`HTML_OUTPUT_DIR`); and implied `HTMLReporter` works via
  `REPORTERS`, which it doesn't. Rewritten against the real
  `DEFAULT_CONFIG` and each key's call site, including three keys
  (`STACK_TRACE_EXCLUDE`, `IGNORE_PATTERNS`, `QUERYIGNORE_PATH`) that exist
  in defaults but aren't read by any code path yet.
- `docs/guides/auto-fix.md`: updated to describe the new safe/unsafe split
  and the `ast.parse()` validation floor.

### Fixed
- **`fix_queries --apply` could write broken code into your source files.**
  The fixer edits the query's *callsite* line, but for `n_plus_one` and
  `fat_select` prescriptions that's frequently the in-loop attribute-access
  line, not the queryset definition — appending `.select_related(...)` or
  `.only(...)` there produced invalid or silently-wrong Python. This shipped
  in 2.0.0. **If you ran `fix_queries --apply` on 2.0.0, check your diffs
  (`git diff` or the `.bak` files it created) for corrupted lines before
  trusting them.**

  As of 2.0.1, `--apply` only writes fixes for issue types verified safe
  (`queryset_eval`, `duplicate_query`, `missing_index`) via a fixed
  allowlist (`fixer.AUTO_APPLIABLE_ISSUE_TYPES`). `n_plus_one`, `fat_select`,
  and `drf_serializer` are shown in the diff tagged `[MANUAL FIX ONLY]` and
  refused at write time — apply those by hand. Before writing anything, the
  candidate file content is also validated with `ast.parse()`; a fix that
  would produce syntactically invalid Python is rejected instead of written
  (this catches syntax errors only, not semantic correctness). `fix_queries
  --apply` now exits nonzero if any fixes were skipped as unsafe or failed
  validation, even when other fixes in the same run succeeded.

  Post-patch, `--apply` performs exactly one real code transform
  (`queryset_eval`) plus two `# TODO`-comment insertions (`duplicate_query`,
  `missing_index`). `n_plus_one` and `fat_select` are dry-run only.
  `drf_serializer` is never emitted by the runtime pipeline `fix_queries`
  uses, so it never reaches the fixer at all.

## [2.0.0] - 2026-03-21

### Added
- **QueryTurbo**: SQL compilation cache with three-phase trust lifecycle
  (UNTRUSTED → TRUSTED → POISONED). On cache miss, compiles and caches.
  On untrusted hit, validates cached SQL against fresh `as_sql()` output
  and promotes to TRUSTED after `VALIDATION_THRESHOLD` (default 3)
  successful validations. On trusted hit, skips `as_sql()` entirely and
  extracts params directly from the Query tree via `turbo/params.py`.
  On mismatch, poisons the entry for the lifetime of the process (persists across cache clears triggered by migrations).
- **True SQL Compilation Skipping**: `turbo/params.py` extracts params
  from the Django Query tree without calling `as_sql()`. Uses
  `lookup.as_sql(compiler, connection)` per WHERE node for exact param
  transformations (handles `__contains` wrapping, `__isnull` discarding,
  etc.) at a fraction of the cost of full SQL compilation.
- **Prepared Statement Bridge**: Multi-database prepared statement support.
  Automatic protocol-level preparation on PostgreSQL + psycopg3 after a
  configurable hit-count threshold. Oracle implicit cursor caching. Graceful
  fallback (TypeError → permanent disable) on unsupported backends.
- **AST SerializerMethodField Analyzer**: Static analysis of DRF `get_<field>`
  methods using `ast.parse()` to detect hidden N+1 queries at serialization
  time. Detects four patterns: related manager access, Model.objects calls,
  deep attribute chains, and for-loop queryset iteration.
- **Per-File Analysis**: `--file` and `--module` flags on `check_queries`
  and `diagnose_project` commands for focused diagnosis via substring matching.
- **Benchmark Dashboard**: `query_doctor_report` management command generates
  standalone HTML report with Chart.js graphs showing cache hit rates, top
  optimized queries, and prepared statement statistics.
- **GitHub Actions CI Integration**: `ci.github` module with
  `format_github_annotations()` for inline PR diff annotations,
  `generate_pr_comment()` for Markdown PR summaries, and
  `write_json_report()` for CI consumption. Example workflow in
  `examples/github-actions/query-doctor.yml`.
- **Baseline Snapshots**: `baseline.py` with `BaselineSnapshot` class for
  saving/loading issue snapshots. SHA-256 hashing ignores line numbers for
  stable identity across code movement. `--save-baseline`, `--baseline`,
  and `--fail-on-regression` flags on `check_queries` and `diagnose_project`.
- **Smart Prescription Grouping**: `grouping.py` with `group_prescriptions()`
  supporting `file_analyzer`, `root_cause`, and `view` strategies. `--group`
  flag on `check_queries` and `diagnose_project`. Console reporter supports
  grouped output mode.
- **Async-Safe Context Managers**: `turbo_enabled()` / `turbo_disabled()`
  now use `contextvars.ContextVar` instead of `threading.local()`, making
  them safe for ASGI deployments with concurrent coroutines.
- **`check_serializers` command**: Dedicated management command for AST-based
  DRF serializer analysis with `--app`, `--file`, `--format`, and `--fail-on`
  flags.
- **Post-migrate cache invalidation**: Automatic cache clear on Django
  `post_migrate` signal to prevent stale SQL after schema changes.
- **Fingerprint collision detection**: Cache hit path validates SQL matches
  and poisons mismatched entries permanently.
- **`__in` lookup length in fingerprint**: Different `__in` list sizes
  produce different fingerprints, preventing SQL/param count mismatch.
- **`select_for_update` in fingerprint**: Queries with `FOR UPDATE`,
  `NOWAIT`, and `SKIP LOCKED` produce distinct fingerprints.
- **Annotation source field fingerprinting**: Annotations with the same
  name but different field targets produce different fingerprints.

### Changed
- Minimum Python version remains 3.10
- All existing v1.x APIs remain backward compatible
- Version bumped to 2.0.0
- Context managers switched from `threading.local()` to `contextvars.ContextVar`
- Cache entries now track `validated_count`, `trusted`, `poisoned` state
- New config key: `VALIDATION_THRESHOLD` (default 3) controls trust promotion

## [1.0.3] - 2026-03-18

> **Never published to PyPI.** This version exists only in the repository
> history; its changes first shipped to PyPI as part of 2.0.0.

### Fixed
- Missing Index analyzer now recommends `Meta.indexes` with `models.Index()` instead of `db_index=True`, following Django's official recommendation since 4.2 (fixes #1)
- Auto-fix for missing indexes now generates `Meta.indexes` suggestion instead of `db_index=True`
- `_field_is_indexed` now checks `Meta.constraints` for `UniqueConstraint` (modern Django 4.2+ pattern) in addition to `unique_together`

### Changed
- Full audit of all prescription texts across all 7 analyzers to align with Django 4.2–6.0 best practices
- Fat SELECT prescriptions now mention `.values()`/`.values_list()` as alternatives when model instances aren't needed
- N+1 prescriptions for `prefetch_related` now mention `Prefetch()` objects for advanced filtering scenarios
- QuerySet evaluation prescriptions now mention `.iterator()` for large querysets to reduce memory usage
- Updated docs, README, and all affected tests to reflect new recommendation text

## [1.0.2] - 2026-03-16

### Fixed
- Fixed SVG terminal renders not displaying on GitHub (switched to absolute URLs)
- Removed Google Fonts @import from SVGs blocked by GitHub CSP

## [1.0.1] - 2026-03-15

### Changed
- Added SVG terminal renders to README for visual feature showcase
- Added Django 6.0 mention in README requirements

## [1.0.0] - 2026-03-13

> **Historical note (added during the 2.1.0 remediation):** two features
> listed below never functioned in any release. The runtime "DRF Serializer
> N+1" analyzer returned no results through any reachable code path and was
> removed in 2.1.0 (see the [2.1.0] "Removed" entry; static DRF analysis via
> `check_serializers` replaces it). "Admin dashboard integration showing
> latest project scan results" never activated: `record_project_report` has
> no caller in any released version and the dashboard template does not
> render project-report data; that dead code — the function, its global, and
> the unused context key — was removed in 2.2.0. The original entries are
> preserved unchanged below.

### Added

#### Core Pipeline
- Query interception via `connection.execute_wrapper()` — works without `DEBUG=True`
- SQL fingerprinting with normalization and SHA-256 hashing
- Source code mapping with file:line references via stack trace analysis
- Django middleware with zero-config setup (one line in `MIDDLEWARE`)
- `diagnose_queries()` context manager for targeted analysis
- `@diagnose` and `@query_budget` decorators
- Full configuration system via `QUERY_DOCTOR` Django settings

#### Analyzers
- **N+1 Detection** — fingerprint-based grouping with FK pattern matching
- **Duplicate Query Detection** — exact-duplicate identification (same SQL and parameters, hashed and grouped)
- **Missing Index Detection** — WHERE/ORDER BY columns without indexes
- **Fat SELECT Detection** — flags `SELECT *` when fewer columns suffice
- **QuerySet Evaluation** — suggests `.count()`, `.exists()`, `.first()` alternatives
- **DRF Serializer N+1** — detects missing prefetch in DRF views

#### Reporters
- **Console** — Rich terminal output with fallback to plain text
- **JSON** — structured output for CI/CD pipelines
- **Log** — Python logging integration
- **HTML** — standalone dashboard report
- **OpenTelemetry** — span and event export for observability stacks

#### Ecosystem
- Celery task support via `@diagnose_task` decorator
- Async Django/ASGI middleware support
- Custom analyzer plugin API via Python entry points
- Pytest plugin with `query_doctor` fixture
- `check_queries` management command for CI analysis
- `query_budget` management command for budget enforcement

#### Project-Wide Diagnosis
- **diagnose_project** management command — crawls all project URLs and generates app-wise health report
- Standalone HTML report with health scores, sortable app scoreboard, and per-URL prescription detail
- JSON report output for CI integration
- Admin dashboard integration showing latest project scan results

#### Auto-Fix & CI
- **Auto-Fix Mode** — `fix_queries` management command applies diagnosed fixes with dry-run default and .bak backups
- **Diff-Aware CI** — `--diff` flag for `check_queries` to analyze only files changed vs a git ref
- **.queryignore** — project-level file to suppress known false positives by SQL pattern, file, callsite, or issue type

#### Monitoring
- **Admin Dashboard** — staff-only in-memory dashboard showing recent query diagnosis reports
- **Query Complexity Scorer** — regex-based SQL complexity analysis flagging excessive JOINs, subqueries, and OR chains

#### Developer Experience
- Every prescription includes severity, description, file:line, and exact code fix
- Zero required dependencies beyond Django
- Optional extras: Rich, Celery, OpenTelemetry
- Full type annotations with `py.typed` (PEP 561)
- CI matrix: Python 3.10-3.13 x Django 4.2-6.0
