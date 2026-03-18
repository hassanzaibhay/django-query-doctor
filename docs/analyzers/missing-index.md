# Missing Index Analyzer

## What It Detects

The missing index analyzer inspects captured SQL for `WHERE`, `ORDER BY`, and
`GROUP BY` clauses that reference columns without a corresponding database
index. Filtering or sorting on unindexed columns forces the database to
perform a full table scan, which degrades rapidly as row counts grow.

## Problem Code

```python
# models.py

class Book(models.Model):
    title = models.CharField(max_length=200)
    published_date = models.DateField()          # no index
    status = models.CharField(max_length=20)     # no index
```

```python
# views.py

def recent_books(request):
    # Full table scan -- published_date has no index
    books = Book.objects.filter(
        published_date__gte="2025-01-01"
    ).order_by("-published_date")
    return render(request, "books.html", {"books": books})
```

## Fix Code

Add a `models.Index()` entry to the model's `Meta.indexes`:

```python
# models.py -- Meta.indexes (supports single and composite indexes)

class Book(models.Model):
    title = models.CharField(max_length=200)
    published_date = models.DateField()
    status = models.CharField(max_length=20)

    class Meta:
        indexes = [
            models.Index(fields=["-published_date"]),
            models.Index(fields=["status", "-published_date"]),  # composite
        ]
```

After changing the model, generate and apply a migration:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Prescription Output

```
[MEDIUM] Missing Index Detected
  Location: views.py:6
  Issue:    Column `published_date` on table `app_book` is used in a
            WHERE clause but has no database index.
  Fix:      Add models.Index(fields=["published_date"]) to Book's Meta.indexes

            Then run: python manage.py makemigrations && python manage.py migrate
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MISSING_INDEX_ENABLED` | `True` | Set to `False` to skip index analysis entirely. |
| `MISSING_INDEX_IGNORE_TABLES` | `[]` | List of table names to exclude from analysis (e.g., small lookup tables). |
| `MISSING_INDEX_IGNORE_COLUMNS` | `["id", "pk"]` | Columns to skip. Primary keys are always indexed. |

```python
# settings.py
QUERY_DOCTOR = {
    "MISSING_INDEX_IGNORE_TABLES": ["app_config", "app_featureflag"],
    "MISSING_INDEX_IGNORE_COLUMNS": ["id", "pk", "uuid"],
}
```

## Common Scenarios

### Filtering by Status or Type Fields

String fields used as filters are frequently overlooked for indexing:

```python
Order.objects.filter(status="pending")
```

If `status` has low cardinality (few distinct values), a standard B-tree index
may not help much. Consider a partial index or conditional index if your
database supports it:

```python
class Meta:
    indexes = [
        models.Index(
            fields=["status"],
            condition=models.Q(status="pending"),
            name="idx_order_pending",
        ),
    ]
```

### Ordering in List Views

`ORDER BY` on an unindexed column forces a full sort:

```python
Article.objects.order_by("-created_at")  # slow without index on created_at
```

### Composite Filters

When a query filters on multiple columns simultaneously, a composite index is
more effective than individual single-column indexes:

```python
# This benefits from Index(fields=["author", "-published_date"])
Book.objects.filter(author=author).order_by("-published_date")
```

!!! note "About Composite Indexes"
    Column order in a composite index matters. The index
    `Index(fields=["author", "published_date"])` supports queries that filter
    on `author` alone or on both `author` and `published_date`, but it does
    **not** efficiently support filtering on `published_date` alone. Place the
    most selective or most frequently filtered column first.

!!! warning "Not Every Column Needs an Index"
    Indexes speed up reads but slow down writes. For write-heavy tables
    (logging, event tracking, audit trails), adding indexes on rarely-queried
    columns can hurt overall performance. The analyzer flags potential
    opportunities -- use your judgment about whether the read pattern justifies
    the write overhead.
