# Auto-Fix

django-query-doctor can automatically apply the fixes it prescribes by modifying your Python source files. This page explains how the auto-fix system actually works, what it can and cannot do, and how to use it safely.

---

## How It Works

When you run `fix_queries`, django-query-doctor:

1. **Analyzes** the target URL by executing a request and capturing queries.
2. **Generates prescriptions** with exact file paths, line numbers, and a suggested fix as text.
3. **Reads the single source line** at the prescription's `callsite.line_number` and applies a **regex substitution** on that one line — it does not parse or understand the surrounding code.
4. **Writes the modified line back to disk**, replacing only that line, at its original position.

There is no AST parsing and no code restructuring. The fixer (`fixer.py`) imports only `logging`, `re`, `shutil`, `dataclasses`, and `pathlib` — no `ast` module. Each issue type has its own regex-based line handler (see [Supported Fix Types](#supported-fix-types)); some just append a method call to the end of the line, others prepend a `# TODO` comment.

> **Known limitation — the edited line may not be the line you expect.** The line that gets modified is the *callsite* of the captured query: the closest application-code stack frame to where the query actually executed (see `stack_tracer.capture_callsite`). For the classic N+1 pattern —
>
> ```python
> books = Book.objects.all()
> for book in books:
>     name = book.author.name  # triggers one query per book
> ```
>
> — the callsite is the `book.author.name` line inside the loop, **not** the `Book.objects.all()` line. Applying the N+1 fix here appends `.select_related('author')` to the end of the access line (`name = book.author.name.select_related('author')`), which is not valid code. The fixer works cleanly when the queryset is evaluated and iterated on the same line, or when you manually point `--file`/review the diff and edit the correct line yourself. **Always review the diff before applying.**

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

> **Warning:** Always ensure your code is committed to version control before running `--apply`. This is a line-level regex tool, not a code-aware refactorer — it can produce incorrect edits, especially for N+1 fixes where the callsite line isn't the queryset definition (see the limitation above). Use `git diff` to review changes after applying, and use `--no-backup` only if you don't want the automatic `.bak` files it creates alongside each modified file.

---

## Supported Fix Types

The fixer dispatches on `Prescription.issue_type` (`fixer.py:_parse_fix`). Only five of the seven issue types have a fix handler:

| Issue Type (`IssueType.value`) | What the handler does | Handler |
|---|---|---|
| `n_plus_one` | Extracts a `.select_related(...)` or `.prefetch_related(...)` call from the fix suggestion text and appends it to the end of the callsite line | `_fix_nplusone` |
| `drf_serializer` | Same handler as `n_plus_one` (extracts and appends `.select_related`/`.prefetch_related`) — but see the note below, this issue type is never produced by the runtime pipeline that `fix_queries` uses | `_fix_nplusone` |
| `fat_select` | Extracts a `.only(...)` or `.defer(...)` call and appends it to the end of the callsite line | `_fix_fat_select` |
| `queryset_eval` | Rewrites `len(x)` → `x.count()` and/or `if x:` → `if x.exists():` on the callsite line via regex | `_fix_queryset_eval` |
| `duplicate_query` | Prepends a `# TODO: Cache this query result to avoid duplicate execution` comment above the callsite line — it does **not** extract a shared variable | `_fix_duplicate` |
| `missing_index` | Prepends a `# TODO: Consider adding an index via Meta.indexes — <suggestion>` comment above the callsite line — it does **not** add a `models.Index()` entry | `_fix_missing_index` |
| `complexity` | No handler. `--issue-type complexity` will never produce a fix. | — |

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

### `n_plus_one`

Targets N+1 patterns caused by accessing ForeignKey, OneToOne, ManyToMany, or reverse-FK relations repeatedly. The fix appends `.select_related('field_name')` or `.prefetch_related('field_name')` to the end of the callsite line — see the [limitation above](#how-it-works) about which line that is.

When the queryset is evaluated and accessed on one line, this works as expected:

```python
# Before
books = Book.objects.all()

# After
books = Book.objects.all().select_related('author')
```

### `fat_select`

Targets queries that fetch all columns when only a subset is used. The fix appends `.only(...)` or `.defer(...)` to the end of the callsite line.

```python
# Before
books = Book.objects.filter(published=True)

# After
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
5. **Double-check N+1 fixes especially.** If the callsite line is inside a loop rather than the queryset definition, the appended call will land on the wrong line — fix it by hand instead.
6. **Handle `missing_index` TODOs separately.** These require a manual `Meta.indexes` edit plus a migration; evaluate each one individually.

---

## Further Reading

- [Management Commands](management-commands.md) — Full command reference.
- [How It Works](how-it-works.md) — Understanding prescriptions and the analysis pipeline.
- [CI Integration](ci-integration.md) — Using auto-fix in CI workflows.
