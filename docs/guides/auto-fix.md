# Auto-Fix

django-query-doctor can automatically apply the fixes it prescribes by modifying your Python source files. This page explains how the auto-fix system actually works, what it can and cannot do, and how to use it safely.

---

## How It Works

When you run `fix_queries`, django-query-doctor:

1. **Analyzes** the target URL by executing a request and capturing queries.
2. **Generates prescriptions** with exact file paths, line numbers, and a suggested fix as text.
3. **Reads the single source line** at the prescription's `callsite.line_number` and applies a **regex substitution** on that one line — it does not parse or understand the surrounding code.
4. On `--apply`, **only issue types known to be safe are written to disk** (see [Supported Fix Types](#supported-fix-types)); the rest are refused and reported instead.

Each issue type has its own regex-based line handler; some just append a method call to the end of the line, others prepend a `# TODO` comment. There is no code restructuring or understanding of surrounding context — the handler only ever sees one line.

> **Known limitation — the edited line may not be the line you expect.** The line a fix targets is the *callsite* of the captured query: the closest application-code stack frame to where the query actually executed (see `stack_tracer.capture_callsite`). For the classic N+1 pattern —
>
> ```python
> books = Book.objects.all()
> for book in books:
>     name = book.author.name  # triggers one query per book
> ```
>
> — the callsite is the `book.author.name` line inside the loop, **not** the `Book.objects.all()` line. Appending `.select_related('author')` there would produce `name = book.author.name.select_related('author')`, which is not valid code. **This is exactly why `n_plus_one` (and `fat_select`, for the same reason) are not auto-applied** — `--apply` refuses to write them and reports them for manual review instead. Only `--dry-run` shows what the fix *would* look like.
>
> Before writing anything, the fixer also parses the candidate file content with `ast.parse()` and refuses to write if that fails — a syntax-error floor. This catches malformed output, not semantic correctness: a fix that lands inside a comment, or after a valid-but-wrong expression, still parses cleanly and would still be written. Treat `--apply`'s output as a starting diff to review, not a guaranteed-correct edit.

---

## Dry Run (Default)

By default, `fix_queries` runs in **dry-run mode**. It shows you a diff of what would change without modifying any files:

```bash
python manage.py fix_queries --url /api/books/
```

The diff format (from `QueryFixer.generate_diff`) shows the file, the line number, the issue description, the original line, and the replacement line(s):

```diff
--- myapp/views.py
+++ myapp/views.py
@@ -8,1 +8,1 @@
  [N+1 detected: 47 queries for table "myapp_author" (field: author)]
- books = Book.objects.all()
+ books = Book.objects.all().select_related('author')
```

Review this output carefully before proceeding.

---

## Applying Fixes

To modify your source files, pass the `--apply` flag:

```bash
python manage.py fix_queries --url /api/books/ --apply
```

Only fixes for `queryset_eval`, `duplicate_query`, and `missing_index` are actually written — see [Supported Fix Types](#supported-fix-types) for why the other issue types are refused. If any fixes were skipped as unsafe, or rejected because they'd produce invalid Python, `fix_queries` prints a warning/error for each and **exits nonzero** (`CommandError`) even though the safe fixes in the same run were still applied.

> **Warning:** Always ensure your code is committed to version control before running `--apply`. This is a line-level regex tool, not a code-aware refactorer — the `ast.parse()` floor only rejects syntactically invalid output, not semantically wrong output. Use `git diff` to review changes after applying, and use `--no-backup` only if you don't want the automatic `.bak` files it creates alongside each modified file.

---

## Supported Fix Types

The fixer dispatches on `Prescription.issue_type` (`fixer.py:_parse_fix`). Five of the seven issue types have a fix handler, but **`--apply` only writes three of those five to disk** — the rest are shown in the diff (`--dry-run` or the pre-write diff under `--apply`), tagged `[MANUAL FIX ONLY]`, and refused at write time:

| Issue Type (`IssueType.value`) | What the handler does | Handler | Auto-applied by `--apply`? |
|---|---|---|---|
| `n_plus_one` | Extracts a `.select_related(...)` or `.prefetch_related(...)` call from the fix suggestion text and appends it to the end of the callsite line | `_fix_nplusone` | **No** — callsite is often mid-loop, not the queryset definition (see the limitation above) |
| `drf_serializer` | Same handler as `n_plus_one` — but see the note below, this issue type is never produced by the runtime pipeline that `fix_queries` uses | `_fix_nplusone` | **No** (also never emitted here in the first place) |
| `fat_select` | Extracts a `.only(...)` or `.defer(...)` call and appends it to the end of the callsite line | `_fix_fat_select` | **No** — same callsite-line risk as `n_plus_one` |
| `queryset_eval` | Rewrites `len(x)` → `x.count()` and/or `if x:` → `if x.exists():` on the callsite line via regex | `_fix_queryset_eval` | **Yes** — the analyzer only fires when the anti-pattern is on the callsite line itself, so this handler is safe by construction |
| `duplicate_query` | Prepends a `# TODO: Cache this query result to avoid duplicate execution` comment above the callsite line — it does **not** extract a shared variable | `_fix_duplicate` | **Yes** — comment-only, can't corrupt code |
| `missing_index` | Prepends a `# TODO: Consider adding an index via Meta.indexes — <suggestion>` comment above the callsite line — it does **not** add a `models.Index()` entry | `_fix_missing_index` | **Yes** — comment-only, can't corrupt code |
| `complexity` | No handler. `--issue-type complexity` will never produce a fix. | — | — |

The auto-applied set is a fixed allowlist (`fixer.AUTO_APPLIABLE_ISSUE_TYPES`) — a future issue type only joins it after its handler is independently verified safe, not by default.

`meta_index` and `cache_queryset` are not real fix types in the code — they were names used in an earlier draft of this page. The actual behavior for missing-index and duplicate-query issues is a `# TODO` comment, shown below.

---

## Targeting Specific Fix Types

Use `--issue-type` (not `--fix-type`, which does not exist) to limit which issues are fixed. It accepts one or more `IssueType` values as strings, with no validation against the real set — a typo silently produces zero fixes:

```bash
# Only apply N+1 fixes
python manage.py fix_queries --url /api/books/ --issue-type n_plus_one --apply

# Only apply duplicate-query TODO comments
python manage.py fix_queries --url /api/books/ --issue-type duplicate_query --apply

# Apply multiple types
python manage.py fix_queries --url /api/books/ \
    --issue-type n_plus_one fat_select \
    --apply
```

Values that actually produce fixes through `fix_queries`: `n_plus_one`, `duplicate_query`, `fat_select`, `queryset_eval`, `missing_index`. `complexity` is detected but has no fix handler. `drf_serializer` findings are produced by the separate `check_serializers` static analyzer (see [DRF Serializer Analyzer](../analyzers/drf-serializer.md)), not by the runtime pipeline `fix_queries` uses, so this value currently has nothing to filter.

---

## Fix Details

### `n_plus_one` — dry-run only, never auto-applied

Targets N+1 patterns caused by accessing ForeignKey, OneToOne, ManyToMany, or reverse-FK relations repeatedly. The suggested fix appends `.select_related('field_name')` or `.prefetch_related('field_name')` to the end of the callsite line — see the [limitation above](#how-it-works) about which line that is.

`--dry-run` shows what this would look like; `--apply` refuses to write it and reports it as skipped instead, because the callsite is frequently mid-loop, not the queryset definition:

```python
# Suggested — shown in the diff, never written by --apply
books = Book.objects.all()
# becomes:
books = Book.objects.all().select_related('author')
```

Apply this one by hand, at the actual queryset definition line.

### `fat_select` — dry-run only, never auto-applied

Targets queries that fetch all columns when only a subset is used. The suggested fix appends `.only(...)` or `.defer(...)` to the end of the callsite line — same callsite-line risk as `n_plus_one`, so `--apply` refuses to write it.

```python
# Suggested — shown in the diff, never written by --apply
books = Book.objects.filter(published=True)
# becomes:
books = Book.objects.filter(published=True).only('id', 'title')
```

### `queryset_eval`

Targets `len(qs)` and `if qs:` patterns. The fix rewrites the callsite line directly via regex.

```python
# Before
total = len(qs)

# After
total = qs.count()
```

### `duplicate_query`

Targets queries executed more than once with identical SQL and parameters. The fix does **not** extract a shared variable — it prepends a comment for you to act on manually:

```python
# Before
count = Book.objects.filter(active=True).count()

# After
# TODO: Cache this query result to avoid duplicate execution
count = Book.objects.filter(active=True).count()
```

### `missing_index`

Targets model fields used in `WHERE`/`ORDER BY` clauses without a database index. The fix does **not** add a `models.Index()` entry — it prepends a comment:

```python
# Before
published_date = models.DateField()

# After
# TODO: Consider adding an index via Meta.indexes — Add an index on published_date
published_date = models.DateField()
```

Adding a real index still requires manually editing `Meta.indexes` and running `makemigrations`/`migrate`.

---

## Best Practices

1. **Always review diffs first.** Run without `--apply`, read every change, then apply.
2. **Commit before applying.** Use version control so you can revert if needed.
3. **Apply one issue type at a time** with `--issue-type`. This makes it easier to review and test each change.
4. **Run tests after applying.** Ensure your test suite passes after each batch of fixes.
5. **Apply `n_plus_one` and `fat_select` fixes by hand.** `--apply` won't write them for you (see [Supported Fix Types](#supported-fix-types)) — use the diff as a starting point and place the fix at the actual queryset definition, not the callsite line.
6. **Handle `missing_index` TODOs separately.** These require a manual `Meta.indexes` edit plus a migration; evaluate each one individually.
7. **Check the exit code in CI.** `fix_queries --apply` exits nonzero if any fixes were skipped as unsafe or failed the syntax-validity check, even if other fixes in the same run succeeded.

---

## Further Reading

- [Management Commands](management-commands.md) — Full command reference.
- [How It Works](how-it-works.md) — Understanding prescriptions and the analysis pipeline.
- [CI Integration](ci-integration.md) — Using auto-fix in CI workflows.
