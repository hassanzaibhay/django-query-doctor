# QuerySet Evaluation Analyzer

## What It Detects

The queryset evaluation analyzer catches Python patterns that cause unintended
or inefficient queryset evaluation. Django querysets are lazy -- they only hit
the database when evaluated. Certain Python idioms inadvertently trigger full
evaluation when a more efficient ORM method exists.

The analyzer inspects the captured call-site code context and flags three
patterns:

| Pattern | Inefficient | Efficient |
|---------|-------------|-----------|
| Counting rows | `len(queryset)` | `queryset.count()` |
| Checking existence | `if queryset:` / `bool(queryset)` | `queryset.exists()` |
| First element via list | `list(qs)[0]` | `qs.first()` |

## Problem Code

### `len()` Instead of `.count()`

```python
# views.py

def stats(request):
    books = Book.objects.filter(published=True)
    total = len(books)  # loads ALL rows into memory just to count them
    return JsonResponse({"total": total})
```

### `bool()` / `if qs` Instead of `.exists()`

```python
# views.py

def dashboard(request):
    pending = Order.objects.filter(status="pending")
    if pending:  # evaluates the entire queryset
        send_alert()
```

### `list(qs)[0]` Instead of `.first()`

```python
# views.py

def latest(request):
    newest = list(Book.objects.order_by("-created_at"))[0]  # loads ALL rows
```

## Fix Code

### Use `.count()`

```python
def stats(request):
    total = Book.objects.filter(published=True).count()  # SELECT COUNT(*)
    return JsonResponse({"total": total})
```

### Use `.exists()`

```python
def dashboard(request):
    if Order.objects.filter(status="pending").exists():  # SELECT 1 LIMIT 1
        send_alert()
```

### Use `.first()`

```python
def latest(request):
    newest = Book.objects.order_by("-created_at").first()  # SELECT ... LIMIT 1
```

## Prescription Output

Console output (severity is always INFO):

```
INFO: Inefficient queryset evaluation: len(qs)
   Location: /app/myapp/views.py:5 in stats
   Code: total = len(books)
   Fix: Use .count() instead of len() to let the database count rows. If iterating afterward, consider .iterator() for large querysets
```

```
INFO: Inefficient queryset evaluation: bool(qs)
   Location: /app/myapp/views.py:4 in dashboard
   Code: if pending:
   Fix: Use .exists() instead of bool()/if to check for rows without loading them
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ANALYZERS.queryset_eval.enabled` | `True` | Set to `False` to disable this analyzer. |

```python
# settings.py
QUERY_DOCTOR = {
    "ANALYZERS": {
        "queryset_eval": {"enabled": False},
    },
}
```

> **Note:** Detection relies on the captured stack trace's code context, so
> `CAPTURE_STACK_TRACES` must remain enabled (it is by default).

## Common Scenarios

### Conditional Logic in Views

Views that branch based on whether a queryset has results frequently use
`if qs:` out of habit:

```python
# Before
users = User.objects.filter(role="admin")
if users:
    ...

# After
if User.objects.filter(role="admin").exists():
    ...
```

### Template Filters and Tags

Custom template filters that call `len()` on a queryset passed from the view
trigger a full evaluation:

```python
# templatetags/utils.py

@register.filter
def item_count(queryset):
    return len(queryset)  # should be queryset.count()
```

### Management Commands Processing All Rows

Commands that iterate a queryset, then check its length, evaluate it twice:

```python
# management/commands/process.py

items = Item.objects.filter(processed=False)
print(f"Processing {len(items)} items")  # query 1
for item in items:                        # query 2
    process(item)
```

**Fix:** Convert to a list once, or count separately:

```python
count = items.count()
print(f"Processing {count} items")
for item in items:
    process(item)
```

!!! warning "Evaluated QuerySets Are Cached"
    After a queryset is fully evaluated (e.g., by iterating it), Django caches
    the results internally. A second iteration of the **same Python object**
    does not hit the database again. Repeated identical SQL from **new**
    queryset objects is the [Duplicate Query analyzer](duplicate.md)'s
    territory; this analyzer flags call sites where `.count()`, `.exists()`,
    or `.first()` would avoid the full evaluation entirely.

!!! info "When `len()` Is Acceptable"
    If you need both the count and the rows, evaluating the queryset into a
    list and calling `len()` on the list is efficient -- the analyzer will not
    flag `len(my_list)`. The issue arises only when `len()` is called directly
    on an unevaluated queryset.
