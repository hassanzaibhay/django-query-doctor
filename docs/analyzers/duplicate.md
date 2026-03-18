# Duplicate Query Analyzer

## What It Detects

The duplicate query analyzer identifies identical SQL statements -- same query
text **and** same bound parameters -- that are executed more than once within a
single request. Unlike N+1 patterns, duplicates typically arise when the same
queryset is evaluated independently in multiple places (a view helper, a
template tag, a context processor) rather than from iterating over a relation.

## Problem Code

```python
# views.py

def dashboard(request):
    featured_count = Book.objects.filter(featured=True).count()  # query 1
    context = {
        "featured_count": featured_count,
        "books": Book.objects.all(),
    }
    return render(request, "dashboard.html", context)
```

```html
{# dashboard.html #}

<p>{{ featured_count }} featured books</p>

{# A template tag that runs the same query again #}
{% load book_tags %}
<p>{% featured_book_count %}</p>  {# query 2 -- identical to query 1 #}
```

```python
# templatetags/book_tags.py

@register.simple_tag
def featured_book_count():
    return Book.objects.filter(featured=True).count()
```

The `featured=True` count query runs twice with exactly the same SQL and
parameters.

## Fix Code

Remove the redundant evaluation by passing the result through the template
context or caching it:

```python
# views.py

def dashboard(request):
    featured_count = Book.objects.filter(featured=True).count()
    context = {
        "featured_count": featured_count,
        "books": Book.objects.all(),
    }
    return render(request, "dashboard.html", context)
```

```html
{# dashboard.html -- use the context variable directly #}

<p>{{ featured_count }} featured books</p>
<p>{{ featured_count }}</p>  {# no extra query #}
```

Alternatively, for values needed across many templates, use Django's caching
framework:

```python
from django.core.cache import cache

def get_featured_count():
    count = cache.get("featured_count")
    if count is None:
        count = Book.objects.filter(featured=True).count()
        cache.set("featured_count", count, timeout=60)
    return count
```

## Prescription Output

```
[MEDIUM] Duplicate Query Detected
  Location: views.py:4, templatetags/book_tags.py:5
  Issue:    Query `SELECT COUNT(*) FROM "app_book" WHERE "app_book"."featured" = ?`
            executed 2 times with identical parameters.
  Fix:      Compute the value once and pass it through the template context,
            or cache the result.

            # views.py -- the value is already computed on line 4.
            # Remove the duplicate call in templatetags/book_tags.py:5
            # and use {{ featured_count }} in the template instead.
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DUPLICATE_THRESHOLD` | `2` | Minimum number of identical executions before a duplicate is reported. Raise this if your application legitimately issues a small number of repeated queries per request. |

```python
# settings.py
QUERY_DOCTOR = {
    "DUPLICATE_THRESHOLD": 3,
}
```

## Common Scenarios

### Multiple View Helpers Querying the Same Data

When utility functions each build their own queryset for the same data, the
same SQL can fire multiple times:

```python
def get_active_users():
    return User.objects.filter(is_active=True)

def view(request):
    users = get_active_users()          # query 1
    admin_users = get_active_users().filter(is_staff=True)  # query 2 (superset, not duplicate)
    active_count = get_active_users().count()                # query 3 (duplicate of query 1's table scan)
```

**Fix:** Assign the base queryset to a variable and reuse it.

### Context Processors and Views

A context processor that runs a query already performed by the view produces a
duplicate:

```python
# context_processors.py
def notifications(request):
    return {"unread": Notification.objects.filter(user=request.user, read=False).count()}

# views.py
def inbox(request):
    unread = Notification.objects.filter(user=request.user, read=False).count()
    ...
```

**Fix:** Let the context processor be the single source of truth, or guard it
with a per-request cache using `request` attributes.

### Pagination Computing Total Count Twice

Some pagination setups call `.count()` both in the paginator and in the
template:

```python
paginator = Paginator(Book.objects.all(), 25)  # .count() internally
page = paginator.get_page(request.GET.get("page"))

# template
<p>Total: {{ books.count }}</p>  {# another .count() #}
```

**Fix:** Use `paginator.count` (already cached after first access) instead of
calling `.count()` again on the queryset.

!!! tip "Near-Duplicates"
    The duplicate analyzer also detects **near-duplicates** -- queries with the
    same fingerprint (normalized SQL) but different bound parameters. These are
    reported at a lower severity because they may indicate an N+1 pattern
    rather than a true duplicate.
