# SerializerMethodField Analysis

## What It Detects

django-query-doctor statically analyzes DRF `SerializerMethodField`
`get_<field>` methods using Python's `ast` module, without executing the
code. This catches the #1 hidden N+1 source in DRF apps: a `get_<field>`
method that triggers a database query per serialized object.

This is a **static** analyzer only — it reads source code, not runtime
queries. Run it explicitly via the `check_serializers` management command;
it does not run automatically in the middleware/request pipeline.

## Running It

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

## Detected Patterns

The analyzer walks the AST of each `get_<field>` method and detects four patterns:

| Pattern | Example | Detection |
|---------|---------|-----------|
| **Related manager access** | `obj.items.count()` | Calls to queryset methods (`.filter()`, `.count()`, `.all()`, etc.) on the serialized object's related managers |
| **Direct QuerySet call** | `Model.objects.filter(...)` | Any `Model.objects.<method>()` call inside a `get_<field>` method |
| **Deep attribute chain** | `obj.author.name` | Two or more levels of attribute access on the serialized object, suggesting a missing `select_related()` |
| **Loop/comprehension over queryset** | `for item in obj.items.all()` | `for` loops, list comprehensions, set comprehensions, generator expressions, and dict comprehensions iterating over related managers |

## What It Does Not Detect

- **Indirect queryset access** — If a `get_<field>` method calls a helper function that internally runs a query, the analyzer cannot follow that call chain.
- **Dynamic attribute access** — `getattr(obj, field_name)` is not analyzed.
- **Cached properties** — If `obj.author` is a `@cached_property`, the analyzer still flags it as a potential N+1 since it cannot determine caching at the AST level.
- **Methods with no source** — C extensions or dynamically generated methods where `inspect.getsource()` fails are silently skipped.
- **Queries in exception handlers** — Queries inside `try`/`except` blocks are detected, but the analyzer does not account for whether the code path is actually reached.

## Problem Code

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

## Prescription Output

```
WARNING: N+1 risk in BookSerializer.get_total(): 'obj.items.count()' triggers a query per object
   Location: myapp/serializers.py:45 in get_total
   Fix: Use queryset.annotate() or prefetch_related('items') instead of accessing 'items' in the serializer method

INFO: Possible N+1 in BookSerializer.get_author_name(): 'obj.author.name' may trigger a query per object if 'author' is not select_related
   Location: myapp/serializers.py:52 in get_author_name
   Fix: Add select_related('author') to the viewset queryset
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ANALYZERS.serializer_method.enabled` | `True` | Set to `False` to disable this analyzer. |

```python
# settings.py
QUERY_DOCTOR = {
    "ANALYZERS": {
        "serializer_method": {"enabled": False},
    },
}
```

## Requires DRF

This analyzer only activates when `rest_framework` is installed. If DRF is
not present, `check_serializers` reports that DRF is not installed and exits
without error.
