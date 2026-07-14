# N+1 Query Analyzer

## What It Detects

The N+1 analyzer identifies queries that are executed repeatedly because
related objects are accessed inside a loop without eager loading. A single
query fetches N parent objects, then N additional queries fire -- one per
parent -- to resolve a foreign key or reverse relation. This is the single
most common cause of slow Django views.

## Problem Code

```python
# views.py

def book_list(request):
    books = Book.objects.all()          # 1 query
    for book in books:
        print(book.author.name)         # N queries (one per book)
    return render(request, "books.html", {"books": books})
```

With 100 books this produces **101 queries** instead of the 2 that are
actually necessary.

## Fix Code

```python
# views.py

def book_list(request):
    books = Book.objects.select_related("author")  # 1 query with JOIN
    for book in books:
        print(book.author.name)                     # no extra queries
    return render(request, "books.html", {"books": books})
```

For reverse relations or many-to-many fields, use `prefetch_related()` instead:

```python
books = Book.objects.prefetch_related("categories")  # 2 queries total
```

## Prescription Output

Console output for a detected N+1:

```
CRITICAL: N+1 detected: 100 queries for table "app_author" (field: author)
   Location: /app/myapp/views.py:8 in book_list
   Fix: Add .select_related('author') to your queryset
   Queries: 100 | Est. savings: ~99.0ms
```

Severity is CRITICAL when the repeated query count is 10 or more, WARNING below that.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ANALYZERS.nplusone.threshold` | `3` | Minimum number of same-fingerprint queries before reporting an N+1. Set higher to reduce noise in views that legitimately issue a small number of similar queries. |
| `ANALYZERS.nplusone.enabled` | `True` | Set to `False` to disable this analyzer. |

```python
# settings.py
QUERY_DOCTOR = {
    "ANALYZERS": {
        "nplusone": {"threshold": 5},
    },
}
```

## Common Scenarios

### DRF Serializers with Nested Relations

When a DRF serializer includes a nested serializer, each parent instance
triggers a query for the related object unless the viewset pre-fetches:

```python
# serializers.py
class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()  # triggers N+1 without prefetching

    class Meta:
        model = Book
        fields = ["id", "title", "author"]
```

**Fix:** Override `get_queryset()` in the viewset:

```python
class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookSerializer

    def get_queryset(self):
        return Book.objects.select_related("author")
```

### Model `@property` Methods

Properties that traverse relations are a hidden source of N+1 queries:

```python
class Book(models.Model):
    author = models.ForeignKey(Author, on_delete=models.CASCADE)

    @property
    def author_bio(self):
        return self.author.bio  # triggers a query if author is not prefetched
```

**Fix:** Ensure callers of `book.author_bio` use a queryset with
`select_related("author")`.

### Template Access Patterns

Django templates silently resolve attribute lookups, which means an N+1 can
hide inside `{{ book.author.name }}` in a `{% for %}` loop:

```html
{% for book in books %}
  <p>{{ book.title }} by {{ book.author.name }}</p>
{% endfor %}
```

**Fix:** Pass a pre-fetched queryset from the view:

```python
context["books"] = Book.objects.select_related("author")
```

!!! info "Fingerprint-Based Detection"
    The N+1 analyzer does **not** rely on heuristics around model field
    definitions. Instead it normalizes each SQL query into a fingerprint by
    replacing literal values with placeholders, then groups by fingerprint.
    If the same fingerprint appears at least `ANALYZERS.nplusone.threshold`
    times and the SQL pattern matches a foreign-key lookup, it is flagged
    as an N+1.
    This approach catches N+1 patterns regardless of how the ORM call is
    constructed.
