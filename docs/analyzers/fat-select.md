# Fat SELECT Analyzer

## What It Detects

The fat SELECT analyzer identifies queries that retrieve more columns than the
application actually uses. This typically manifests as `SELECT *` (Django's
default when accessing full model instances) when only a few fields are needed.
Transferring unnecessary columns wastes database I/O, network bandwidth, and
Python memory -- especially when the model contains large `TextField`,
`JSONField`, or `BinaryField` columns.

## Problem Code

```python
# views.py

def book_list(request):
    # Fetches ALL columns including the large 'description' TextField
    books = Book.objects.all()
    return render(request, "book_list.html", {
        "books": [{"id": b.id, "title": b.title} for b in books]
    })
```

The view only uses `id` and `title`, but the query loads every column on the
`Book` model, including a potentially large `description` field.

## Fix Code

Use `.only()` to select just the columns you need:

```python
# views.py

def book_list(request):
    books = Book.objects.only("id", "title")
    return render(request, "book_list.html", {
        "books": [{"id": b.id, "title": b.title} for b in books]
    })
```

Alternatively, use `.defer()` to exclude specific heavy columns while keeping
everything else:

```python
books = Book.objects.defer("description", "metadata")
```

For cases where you do not need model instances at all, `.values()` or
`.values_list()` avoids model instantiation entirely:

```python
books = Book.objects.values_list("id", "title")
```

## Prescription Output

```
[LOW] Fat SELECT Detected
  Location: views.py:5
  Issue:    Query selects 12 columns from `app_book` but only `id` and `title`
            are accessed in subsequent code.
  Fix:      Use .only() to limit the selected columns:

            - books = Book.objects.all()
            + books = Book.objects.only("id", "title")
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `FAT_SELECT_THRESHOLD` | `6` | Minimum number of selected columns before the analyzer considers a query "fat". Queries selecting fewer columns than this are ignored. |
| `FAT_SELECT_IGNORE_TABLES` | `[]` | List of table names to exclude from analysis. Useful for small reference tables where selecting all columns is acceptable. |

```python
# settings.py
QUERY_DOCTOR = {
    "FAT_SELECT_THRESHOLD": 8,
    "FAT_SELECT_IGNORE_TABLES": ["app_config"],
}
```

## Common Scenarios

### List Views and Tables

List pages typically display a subset of fields in a table. Loading full model
instances for 50+ rows per page wastes significant memory:

```python
# Before -- loads all fields for every row
books = Book.objects.filter(published=True)[:50]

# After -- loads only what the template uses
books = Book.objects.filter(published=True).only(
    "id", "title", "author_id", "published_date"
)[:50]
```

### API Endpoints Returning Subsets

DRF serializers with a subset of fields still trigger `SELECT *` unless the
queryset is constrained:

```python
class BookListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ["id", "title", "published_date"]

class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookListSerializer

    def get_queryset(self):
        # Constrain columns to match the serializer fields
        return Book.objects.only("id", "title", "published_date")
```

### Models with TextField or JSONField

Models that store large blobs of text or JSON are prime candidates for
`.defer()`:

```python
class Article(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField()
    body = models.TextField()              # can be 50+ KB
    metadata = models.JSONField(default=dict)  # can be large

# Defer the heavy fields when listing
articles = Article.objects.defer("body", "metadata")
```

### Aggregation Queries

If you only need aggregated results, avoid loading rows at all:

```python
# Before
total = len(Book.objects.all())  # loads all rows, all columns

# After
total = Book.objects.count()  # single COUNT(*) query
```

!!! tip "only() vs defer() vs values()"
    Use `.only()` when you know exactly which fields you need. Use `.defer()`
    when you want most fields but need to exclude a few heavy ones. Use
    `.values()` or `.values_list()` when you do not need model instances at
    all and want the best possible performance. Note that `.only()` and
    `.defer()` return model instances that will lazily load deferred fields on
    access, which can cause additional queries if you access them by mistake.
