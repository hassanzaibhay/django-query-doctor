# DRF Serializer Analyzer

## What It Detects

The DRF serializer analyzer detects N+1 queries that originate specifically
from Django REST Framework serializer nesting. When a serializer declares a
nested serializer or a `SerializerMethodField` that accesses related objects,
each item in the response triggers additional queries unless the viewset's
`get_queryset()` includes the appropriate `select_related()` or
`prefetch_related()` calls.

This analyzer traces the captured SQL back through the DRF serialization stack
to identify the responsible viewset and provide a targeted fix pointing at
`get_queryset()`.

## Problem Code

```python
# serializers.py

class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "email"]


class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()  # nested serializer -- triggers N+1

    class Meta:
        model = Book
        fields = ["id", "title", "author"]
```

```python
# views.py

class BookViewSet(viewsets.ModelViewSet):
    queryset = Book.objects.all()  # no select_related
    serializer_class = BookSerializer
```

When the list endpoint returns 50 books, this fires 1 query for books plus
50 queries to fetch each author individually.

## Fix Code

Override `get_queryset()` to eagerly load the related objects:

```python
# views.py

class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookSerializer

    def get_queryset(self):
        return Book.objects.select_related("author")
```

For many-to-many or reverse relations, use `prefetch_related()`:

```python
class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookDetailSerializer

    def get_queryset(self):
        return Book.objects.select_related("author").prefetch_related(
            "categories", "tags"
        )
```

## Prescription Output

```
[HIGH] DRF Serializer N+1 Detected
  Location: serializers.py:10 (BookSerializer.author)
  Issue:    Nested `AuthorSerializer` on `BookSerializer` causes 50 extra
            queries. The viewset `BookViewSet` does not prefetch `author`.
  Fix:      Override `get_queryset()` in views.py to add `select_related`:

            class BookViewSet(viewsets.ModelViewSet):
                serializer_class = BookSerializer

                def get_queryset(self):
            -       return Book.objects.all()
            +       return Book.objects.select_related("author")
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DRF_ANALYZER_ENABLED` | `True` | Set to `False` to disable DRF-specific analysis. The general N+1 analyzer will still catch some of these patterns. |
| `DRF_ANALYZER_THRESHOLD` | `3` | Minimum number of serializer-triggered queries before reporting. |

```python
# settings.py
QUERY_DOCTOR = {
    "DRF_ANALYZER_THRESHOLD": 5,
}
```

## Common Scenarios

### SerializerMethodField with QuerySet Access

A `SerializerMethodField` that traverses a relation or runs a query for each
instance is a frequent N+1 source:

```python
class BookSerializer(serializers.ModelSerializer):
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = ["id", "title", "review_count"]

    def get_review_count(self, obj):
        return obj.reviews.count()  # N+1: one COUNT per book
```

**Fix:** Annotate the count on the queryset:

```python
from django.db.models import Count

class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookSerializer

    def get_queryset(self):
        return Book.objects.annotate(review_count=Count("reviews"))
```

Then reference the annotation in the serializer:

```python
def get_review_count(self, obj):
    return obj.review_count  # no extra query -- uses annotation
```

### Deeply Nested Serializers

When serializers nest multiple levels deep, each level compounds the N+1:

```python
class PublisherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publisher
        fields = ["id", "name"]

class AuthorSerializer(serializers.ModelSerializer):
    publisher = PublisherSerializer()  # level 2 nesting

class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()  # level 1 nesting
```

**Fix:** Chain `select_related` with double-underscore lookups:

```python
def get_queryset(self):
    return Book.objects.select_related("author__publisher")
```

### Conditional Serializer Fields

Serializers that include different nested serializers depending on the action
need matching queryset optimization:

```python
class BookViewSet(viewsets.ModelViewSet):
    def get_serializer_class(self):
        if self.action == "list":
            return BookListSerializer   # no nested author
        return BookDetailSerializer      # includes nested author

    def get_queryset(self):
        qs = Book.objects.all()
        if self.action != "list":
            qs = qs.select_related("author")
        return qs
```

### Prefetching with Custom QuerySets

For complex prefetch scenarios, use `Prefetch` objects to control the queryset
used for prefetching:

```python
from django.db.models import Prefetch

def get_queryset(self):
    return Book.objects.prefetch_related(
        Prefetch(
            "reviews",
            queryset=Review.objects.select_related("user").order_by("-created_at")[:5],
        )
    )
```

!!! info "How It Traces Back to ViewSets"
    The analyzer inspects the Python stack trace captured alongside each SQL
    query. When it finds DRF serialization frames (e.g., `to_representation`,
    `SerializerMethodField.to_representation`), it walks up the stack to locate
    the originating viewset class and its `get_queryset()` method. This allows
    the prescription to point directly at the viewset that needs to be updated.

!!! note "Requires DRF"
    This analyzer only activates when `rest_framework` is installed. If DRF is
    not present, the analyzer silently skips itself. The general N+1 analyzer
    will still catch relation-access patterns regardless of whether DRF is used.

---

## Static Analysis: SerializerMethodField *(v2.0)*

In addition to runtime detection, django-query-doctor includes a **static analyzer** that inspects `SerializerMethodField` `get_<field>` methods using Python's `ast` module without executing the code. This catches N+1 patterns that are invisible to runtime analysis when test coverage is incomplete.

### Running Static Analysis

```bash
# Scan all installed apps
python manage.py check_serializers

# Scan specific apps
python manage.py check_serializers --app=myapp --app=otherapp

# Scan specific modules
python manage.py check_serializers --module=myapp.serializers

# Scan specific files
python manage.py check_serializers --file=myapp/serializers.py

# JSON output for CI
python manage.py check_serializers --format=json

# Fail CI on warnings or above
python manage.py check_serializers --fail-on=warning
```

### What It Detects

The static analyzer walks the AST of each `get_<field>` method and detects four patterns:

| Pattern | Example | Detection |
|---------|---------|-----------|
| **Related manager access** | `obj.items.count()` | Calls to queryset methods (`.filter()`, `.count()`, `.all()`, etc.) on the serialized object's related managers |
| **Direct QuerySet call** | `Model.objects.filter(...)` | Any `Model.objects.<method>()` call inside a `get_<field>` method |
| **Deep attribute chain** | `obj.author.name` | Two or more levels of attribute access on the serialized object, suggesting a missing `select_related()` |
| **Loop/comprehension over queryset** | `for item in obj.items.all()` | `for` loops, list comprehensions, set comprehensions, generator expressions, and dict comprehensions iterating over related managers |

### What It Does Not Detect

- **Indirect queryset access** — If a `get_<field>` method calls a helper function that internally runs a query, the static analyzer cannot follow that call chain.
- **Dynamic attribute access** — `getattr(obj, field_name)` is not analyzed.
- **Cached properties** — If `obj.author` is a `@cached_property`, the static analyzer still flags it as a potential N+1 since it cannot determine caching at the AST level.
- **Methods with no source** — C extensions or dynamically generated methods where `inspect.getsource()` fails are silently skipped.
- **Queries in exception handlers** — Queries inside `try`/`except` blocks are detected, but the analyzer does not account for whether the code path is actually reached.

### Prescription Output

```
WARNING  N+1 risk in BookSerializer.get_total(): 'obj.items.count()' triggers a query per object
  Location: myapp/serializers.py:45 (get_total)
  Fix:      Use queryset.annotate() or prefetch_related('items') instead of
            accessing 'items' in the serializer method

INFO     Possible N+1 in BookSerializer.get_author_name(): 'obj.author.name' may
         trigger a query per object if 'author' is not select_related
  Location: myapp/serializers.py:52 (get_author_name)
  Fix:      Add select_related('author') to the viewset queryset
```

!!! info "Static vs Runtime"
    The static analyzer (`check_serializers` command) and the runtime DRF analyzer (middleware) are complementary. The static analyzer finds patterns in source code regardless of test coverage. The runtime analyzer detects actual N+1 queries during request processing. Use both for comprehensive coverage.
