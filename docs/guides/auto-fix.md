# Auto-Fix

django-query-doctor can automatically apply the fixes it prescribes by modifying your Python source files. This page explains how the auto-fix system works, what fix types are supported, and how to use it safely.

---

## How It Works

When you run `fix_queries`, django-query-doctor:

1. **Analyzes** the target URL(s) by executing requests and capturing queries.
2. **Generates prescriptions** with exact file paths, line numbers, and fix code.
3. **Parses** the target source files using Python's AST module.
4. **Applies** the fixes by modifying the AST and writing the updated source back to disk.

The AST-based approach ensures that fixes are syntactically correct and properly placed. django-query-doctor does not use simple string replacement -- it understands the structure of your code.

---

## Dry Run (Default)

By default, `fix_queries` runs in **dry-run mode**. It shows you a diff of what would change without modifying any files:

```bash
python manage.py fix_queries --url /api/books/
```

Output:

```diff
--- myapp/views.py (original)
+++ myapp/views.py (fixed)
@@ -83,7 +83,7 @@
     def get_queryset(self):
-        return Book.objects.all()
+        return Book.objects.select_related('author').all()

--- myapp/serializers.py (original)
+++ myapp/serializers.py (fixed)
@@ -22,7 +22,11 @@
     class Meta:
         model = Book
-        fields = "__all__"
+        fields = ["id", "title", "isbn", "published_date"]
```

Review this output carefully before proceeding.

---

## Applying Fixes

To modify your source files, pass the `--apply` flag:

```bash
python manage.py fix_queries --url /api/books/ --apply
```

> **Warning:** Always ensure your code is committed to version control before running `--apply`. While django-query-doctor generates correct fixes in the vast majority of cases, complex querysets (dynamic construction, conditional chaining, multi-line expressions) may require manual adjustment. Use `git diff` to review changes after applying.

---

## Supported Fix Types

| Fix Type | What It Does | Example |
|---|---|---|
| `select_related` | Adds `.select_related()` calls for FK/OneToOne N+1 patterns | `.select_related('author', 'publisher')` |
| `prefetch_related` | Adds `.prefetch_related()` calls for M2M/reverse FK N+1 patterns | `.prefetch_related('categories', 'tags')` |
| `only_defer` | Replaces `SELECT *` with `.only()` or adds `.defer()` for unused columns | `.only('id', 'title', 'price')` |
| `db_index` | Adds `db_index=True` to model field definitions for missing indexes | `published_date = DateField(db_index=True)` |
| `cache_queryset` | Extracts repeated queryset evaluations into a variable | `books = list(Book.objects.filter(...))` |

---

## Targeting Specific Fix Types

You can limit which categories of fixes are applied using `--fix-type`:

```bash
# Only apply select_related fixes
python manage.py fix_queries --url /api/books/ --fix-type select_related --apply

# Only apply index-related fixes
python manage.py fix_queries --url /api/books/ --fix-type db_index --apply

# Apply multiple specific fix types
python manage.py fix_queries --url /api/books/ \
    --fix-type select_related \
    --fix-type prefetch_related \
    --apply
```

This is useful when you want to apply safe, well-understood fixes (like `select_related`) while leaving more complex changes (like `db_index`, which requires a migration) for manual review.

---

## Fix Details

### `select_related`

Targets N+1 patterns caused by accessing ForeignKey or OneToOneField relations in loops. The fix adds `.select_related('field_name')` to the queryset that feeds the loop.

Before:
```python
def get_queryset(self):
    return Book.objects.all()
    # Accessing book.author in template triggers N+1
```

After:
```python
def get_queryset(self):
    return Book.objects.select_related('author').all()
```

### `prefetch_related`

Targets N+1 patterns from ManyToManyField or reverse ForeignKey traversal. The fix adds `.prefetch_related('field_name')` to the queryset.

Before:
```python
books = Book.objects.all()
for book in books:
    categories = book.categories.all()  # N+1
```

After:
```python
books = Book.objects.prefetch_related('categories').all()
for book in books:
    categories = book.categories.all()  # Uses prefetched cache
```

### `only_defer`

Targets queries that fetch all columns when only a subset is used. The fix adds `.only()` with the columns that are actually accessed.

Before:
```python
books = Book.objects.filter(published=True)
titles = [book.title for book in books]  # Only uses 'title'
```

After:
```python
books = Book.objects.filter(published=True).only('id', 'title')
titles = [book.title for book in books]
```

### `db_index`

Targets model fields used in `WHERE` or `ORDER BY` clauses that lack a database index. The fix adds `db_index=True` to the field definition.

Before:
```python
class Book(models.Model):
    published_date = models.DateField()
```

After:
```python
class Book(models.Model):
    published_date = models.DateField(db_index=True)
```

> **Note:** After applying `db_index` fixes, you must generate and run a migration:
>
> ```bash
> python manage.py makemigrations
> python manage.py migrate
> ```

### `cache_queryset`

Targets duplicate queries caused by evaluating the same queryset multiple times. The fix extracts the queryset evaluation into a variable.

Before:
```python
def get_context_data(self, **kwargs):
    ctx = super().get_context_data(**kwargs)
    ctx["count"] = Book.objects.filter(active=True).count()
    ctx["books"] = Book.objects.filter(active=True)[:10]  # Same filter, separate query
    return ctx
```

After:
```python
def get_context_data(self, **kwargs):
    ctx = super().get_context_data(**kwargs)
    _qs_books_active = Book.objects.filter(active=True)
    ctx["count"] = _qs_books_active.count()
    ctx["books"] = _qs_books_active[:10]
    return ctx
```

---

## Best Practices

1. **Always review diffs first.** Run without `--apply`, read every change, then apply.
2. **Commit before applying.** Use version control so you can revert if needed.
3. **Apply one fix type at a time.** This makes it easier to review and test each change.
4. **Run tests after applying.** Ensure your test suite passes after each batch of fixes.
5. **Handle `db_index` separately.** Index changes require migrations and may affect write performance. Evaluate each one individually.

---

## Further Reading

- [Management Commands](management-commands.md) -- Full command reference.
- [How It Works](how-it-works.md) -- Understanding prescriptions and the analysis pipeline.
- [CI Integration](ci-integration.md) -- Using auto-fix in CI workflows.
