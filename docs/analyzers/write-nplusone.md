# Write N+1 Analyzer

## What It Detects

The write N+1 analyzer identifies repeated **single-row write statements** --
the `.save()`, `.create()` or `.delete()` inside a loop that issues one database
round trip per object where a single bulk statement would do the same work.

Every other built-in analyzer examines `SELECT` statements. This one examines
everything else, which makes it the only analyzer that fires on code doing no
reads at all: an import job, a bulk status update, a fan-out of notification
rows.

It groups non-`SELECT` captures by fingerprint -- normalization collapses the
literal values, so the same statement shape repeated in a loop shares a single
fingerprint -- and reports any group that reaches the threshold. Transaction
control statements (`BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`) are captured the
same way a write is, and are excluded, so a request that opens several
transactions is not reported as a write N+1.

## Problem Code

```python
# views.py

def import_books(request):
    payload = json.loads(request.body)

    for row in payload["books"]:            # 500 rows
        Book.objects.create(                # one INSERT per row -- 500 round trips
            title=row["title"],
            isbn=row["isbn"],
            author_id=row["author_id"],
        )

    return JsonResponse({"imported": len(payload["books"])})
```

The same shape appears with `.save()` in a loop, which issues one `UPDATE` per
object:

```python
def mark_all_reviewed(request):
    for book in Book.objects.filter(status="pending"):
        book.status = "reviewed"
        book.save()                         # one UPDATE per book
```

## Fix Code

Build the objects first, then issue one statement:

```python
# views.py

def import_books(request):
    payload = json.loads(request.body)

    Book.objects.bulk_create(               # one INSERT
        [
            Book(
                title=row["title"],
                isbn=row["isbn"],
                author_id=row["author_id"],
            )
            for row in payload["books"]
        ],
        batch_size=500,
    )

    return JsonResponse({"imported": len(payload["books"])})
```

For the update case, `bulk_update()` when the new values differ per row:

```python
books = list(Book.objects.filter(status="pending"))
for book in books:
    book.status = "reviewed"
Book.objects.bulk_update(books, ["status"])
```

...or a queryset update when every row gets the same value, which is cheaper
still because it never loads the rows:

```python
Book.objects.filter(status="pending").update(status="reviewed")
```

And for deletes, go through the queryset rather than per object:

```python
Book.objects.filter(status="expired").delete()   # one DELETE
```

`bulk_create()` emits a single multi-row `INSERT`, which is one capture and
never reaches the threshold -- so applying the prescription clears the finding.

## Prescription Output

Console output for four `Book.objects.create()` calls in a loop:

```
WARNING: Write N+1 detected: 4 single-row INSERT statements for Book. One bulk statement replaces all 4.
   Location: /app/myapp/views.py:21 in import_books
   Fix: Build the objects in a list and issue one write: Book.objects.bulk_create([Book(...), ...]). Pass batch_size= if the list is large enough to strain the driver.
   Queries: 4 | Est. savings: ~0.1ms
```

The prescription's `extra` dict carries the parsed statement kind and target:

```python
{"table": "testapp_book", "statement": "insert", "model": "Book"}
```

`model` is `None` when no installed model maps to the table -- a raw
`cursor.execute()` against a table Django does not own, for example. The finding
is still reported; the fix suggestion falls back to the generic
`Model.objects.bulk_create(...)` wording.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ANALYZERS.write_nplusone.threshold` | `3` | Minimum number of identical single-row writes before the group is reported. Raise it if your application legitimately issues a handful of individual writes per request. |
| `ANALYZERS.write_nplusone.enabled` | `True` | Whether this analyzer runs at all. |

```python
# settings.py
QUERY_DOCTOR = {
    "ANALYZERS": {
        "write_nplusone": {"threshold": 10},
    },
}
```

Severity follows the same rule as the [N+1 analyzer](nplusone.md): `WARNING`
below ten statements in a group, `CRITICAL` at ten or more.

## Common Scenarios

### Creating Related Rows Alongside a Parent

A parent object followed by a loop over its children is the most common shape,
and the loop is easy to miss because the parent write looks like the expensive
part:

```python
order = Order.objects.create(customer=customer)
for item in cart:
    OrderItem.objects.create(order=order, product=item.product, qty=item.qty)
```

**Fix:** `OrderItem.objects.bulk_create([...])` after the parent exists.

### Signal Handlers Writing Per Instance

A `post_save` receiver that writes an audit row turns any bulk operation back
into per-row writes, and the loop is not visible at the call site:

```python
@receiver(post_save, sender=Book)
def log_change(sender, instance, **kwargs):
    AuditEntry.objects.create(model="Book", object_id=instance.pk)
```

**Fix:** collect the entries and write them once at the end of the request, or
skip the receiver for bulk paths. Note that `bulk_create()` does **not** send
`post_save`, so converting the caller to `bulk_create()` silences both the
original write N+1 and this one -- verify the audit rows are still written some
other way before doing that.

### `get_or_create()` in a Loop

`get_or_create()` issues a `SELECT` and, on a miss, an `INSERT`. In a loop over
mostly-new values this produces both an N+1 and a write N+1 for the same code:

```python
for name in tag_names:
    Tag.objects.get_or_create(name=name)
```

**Fix:** fetch the existing rows once, then `bulk_create()` the difference:

```python
existing = set(Tag.objects.filter(name__in=tag_names).values_list("name", flat=True))
Tag.objects.bulk_create([Tag(name=n) for n in tag_names if n not in existing])
```

!!! note "Not every repeated write is a defect"
    Writes that must be individually committed, or that depend on the primary
    key of the previous row, cannot be batched. `bulk_create()` also skips
    `save()` overrides and `pre_save`/`post_save` signals, so it is not a
    drop-in replacement in every codebase. When a group is legitimate, suppress
    it with a [`.queryignore`](../guides/query-ignore.md) rule rather than
    raising the threshold globally.
