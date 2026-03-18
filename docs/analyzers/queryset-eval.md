# QuerySet Evaluation Analyzer

## What It Detects

The queryset evaluation analyzer catches Python patterns that cause unintended
or inefficient queryset evaluation. Django querysets are lazy -- they only hit
the database when evaluated. Certain Python idioms inadvertently trigger full
evaluation when a more efficient ORM method exists.

The analyzer flags four main patterns:

| Pattern | Inefficient | Efficient |
|---------|-------------|-----------|
| Counting rows | `len(queryset)` | `queryset.count()` |
| Checking existence | `if queryset:` / `bool(queryset)` | `queryset.exists()` |
| Iterating multiple times | looping over the same queryset twice | evaluate once into a list, or restructure |
| Slicing after evaluation | `list(qs)[5:10]` | `qs[5:10]` (database LIMIT/OFFSET) |

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

### Iterating a QuerySet Multiple Times

```python
# views.py

def report(request):
    books = Book.objects.all()
    titles = [b.title for b in books]   # query 1 -- full evaluation
    authors = [b.author for b in books] # query 2 -- evaluates again
```

### Slicing After Evaluation

```python
# views.py

def paginated(request):
    all_books = list(Book.objects.all())  # loads ALL rows
    page = all_books[20:30]               # slices in Python
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

### Evaluate Once

```python
def report(request):
    books = list(Book.objects.select_related("author"))  # one query
    titles = [b.title for b in books]
    authors = [b.author for b in books]  # no extra query -- already loaded
```

### Slice at the Database Level

```python
def paginated(request):
    page = Book.objects.all()[20:30]  # SELECT ... LIMIT 10 OFFSET 20
```

## Prescription Output

```
[MEDIUM] Inefficient QuerySet Evaluation
  Location: views.py:5
  Issue:    `len()` called on a queryset. This loads all rows into memory
            to count them. Use `.count()` for a database-level COUNT.
  Fix:
            - total = len(books)
            + total = books.count()
```

```
[MEDIUM] Inefficient QuerySet Evaluation
  Location: views.py:4
  Issue:    QuerySet used in a boolean context (`if queryset:`). This evaluates
            the full queryset. Use `.exists()` to check with a LIMIT 1 query.
  Fix:
            - if pending:
            + if pending.exists():
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `QUERYSET_EVAL_ENABLED` | `True` | Set to `False` to disable this analyzer. |
| `QUERYSET_EVAL_IGNORE_SMALL` | `False` | When `True`, skip reporting for querysets that return fewer than 10 rows. Useful for reducing noise on small lookup tables. |

```python
# settings.py
QUERY_DOCTOR = {
    "QUERYSET_EVAL_IGNORE_SMALL": True,
}
```

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
    does not hit the database again. The analyzer detects cases where a
    **new queryset** is constructed with identical SQL, or where `.count()` /
    `.exists()` would avoid the initial full evaluation entirely.

!!! info "When `len()` Is Acceptable"
    If you need both the count and the rows, evaluating the queryset into a
    list and calling `len()` on the list is efficient -- the analyzer will not
    flag `len(my_list)`. The issue arises only when `len()` is called directly
    on an unevaluated queryset.
