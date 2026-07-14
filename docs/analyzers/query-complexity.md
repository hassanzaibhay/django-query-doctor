# Query Complexity Analyzer

## What It Detects

The query complexity analyzer scores each SQL query based on the number and
type of expensive operations it contains. Queries that exceed a configurable
complexity threshold are flagged with suggestions for simplification. The goal
is to catch queries that have grown unwieldy through chained ORM calls and may
benefit from being broken apart or restructured.

## Scoring Table

Each SQL feature contributes points to the total complexity score:

| SQL Feature | Points | Example ORM Usage |
|-------------|--------|-------------------|
| `JOIN` (each) | 2 | `select_related()`, `annotate()` with relations |
| Subquery (each additional `SELECT`) | 3 | `Subquery()`, `qs.filter(id__in=other_qs)` |
| `OR` (each) | 1 | `Q(...) \| Q(...)` |
| `GROUP BY` | 2 | `.values().annotate()` |
| `HAVING` | 2 | `.annotate().filter()` after group |
| `DISTINCT` | 1 | `.distinct()` |
| `ORDER BY` | 1 | `.order_by(...)` |
| `CASE / WHEN` (each `WHEN`) | 1 | `Case(When(...))` |
| `UNION` / `INTERSECT` / `EXCEPT` | 3 | `qs1.union(qs2)` |
| `LIKE` with leading `%` | 2 | `.filter(name__contains=...)` |
| `COUNT(*)` combined with `JOIN` | 2 | `.annotate(n=Count(...))` over relations |

The total score is the sum of all points. The default threshold is **8**; a
query scoring 8 or more is flagged (WARNING severity, CRITICAL at 12 or more).

## Problem Code

```python
# views.py

from django.db.models import (
    Avg, Case, Count, OuterRef, Subquery, Sum, Value, When
)

def complex_report(request):
    subquery = (
        Review.objects
        .filter(book=OuterRef("pk"))
        .values("book")
        .annotate(avg_rating=Avg("rating"))
        .values("avg_rating")
    )

    books = (
        Book.objects
        .select_related("author", "publisher")                  # 2 JOINs = 4
        .prefetch_related("categories")
        .annotate(
            review_count=Count("reviews"),                      # JOIN = 2, COUNT+JOIN = 2
            avg_rating=Subquery(subquery),                      # subquery = 3
            revenue=Sum("sales__amount"),                       # JOIN = 2
            tier=Case(                                          # 2 WHENs = 2
                When(revenue__gte=10000, then=Value("gold")),
                When(revenue__gte=1000, then=Value("silver")),
                default=Value("bronze"),
            ),
        )
        .filter(review_count__gte=5)                            # HAVING = 2
        .distinct()                                              # DISTINCT = 1
        .order_by("-revenue")                                    # ORDER BY = 1
    )
    # GROUP BY from the annotations = 2
    # Total score: 4 + 2 + 2 + 3 + 2 + 2 + 2 + 1 + 1 + 2 = 21 (over threshold 8)
```

## Fix Code

Break the query into smaller, focused queries:

```python
# views.py

def complex_report(request):
    # Query 1: Basic book data with author
    books = (
        Book.objects
        .select_related("author", "publisher")
        .annotate(review_count=Count("reviews"))
        .filter(review_count__gte=5)
    )

    # Query 2: Revenue data (separate annotation)
    revenue_data = dict(
        Sales.objects
        .values("book_id")
        .annotate(revenue=Sum("amount"))
        .values_list("book_id", "revenue")
    )

    # Query 3: Average ratings (separate query)
    rating_data = dict(
        Review.objects
        .values("book_id")
        .annotate(avg_rating=Avg("rating"))
        .values_list("book_id", "avg_rating")
    )

    # Combine in Python
    for book in books:
        book.revenue = revenue_data.get(book.id, 0)
        book.avg_rating = rating_data.get(book.id, None)
```

Alternatively, use `.annotate()` instead of subqueries when the ORM can
express the operation as a `JOIN`:

```python
# Instead of a Subquery for average rating:
books = Book.objects.annotate(avg_rating=Avg("reviews__rating"))
```

## Prescription Output

Console output for a flagged query:

```
CRITICAL: Query complexity score 21 exceeds threshold 8
   Location: /app/myapp/views.py:12 in complex_report
   Fix: Replace subqueries with JOINs or annotate() where possible.
```

The fix suggestion is contextual: with more than 3 JOINs it recommends
splitting the query and using `select_related`/`prefetch_related`; with
subqueries it suggests JOIN-based rewrites; with multiple `OR` conditions
it points at index-friendly alternatives.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ANALYZERS.complexity.threshold` | `8` | Total score at or above which a query is flagged. Lower values catch more queries but may produce noise. |
| `ANALYZERS.complexity.enabled` | `True` | Set to `False` to disable this analyzer. |

```python
# settings.py
QUERY_DOCTOR = {
    "ANALYZERS": {
        "complexity": {"threshold": 12},
    },
}
```

## Common Scenarios

### Dashboard Views with Multiple Aggregations

Admin dashboards frequently build a single "mega-query" with many annotations.
Splitting into per-widget queries is often clearer and no slower:

```python
# Before: one query with 6 annotations
stats = (
    Order.objects
    .annotate(month=TruncMonth("created_at"))
    .values("month")
    .annotate(
        total_orders=Count("id"),
        total_revenue=Sum("amount"),
        avg_order=Avg("amount"),
        max_order=Max("amount"),
        refund_count=Count("id", filter=Q(status="refunded")),
        unique_customers=Count("customer", distinct=True),
    )
)

# After: two focused queries
monthly_revenue = (
    Order.objects
    .annotate(month=TruncMonth("created_at"))
    .values("month")
    .annotate(total=Sum("amount"), avg=Avg("amount"), max=Max("amount"))
)

monthly_counts = (
    Order.objects
    .annotate(month=TruncMonth("created_at"))
    .values("month")
    .annotate(
        orders=Count("id"),
        refunds=Count("id", filter=Q(status="refunded")),
        customers=Count("customer", distinct=True),
    )
)
```

### Subqueries That Can Be JOINs

Many subqueries can be rewritten as JOIN-based annotations:

```python
# Before (subquery, 10 points)
latest_review = Review.objects.filter(
    book=OuterRef("pk")
).order_by("-created_at").values("rating")[:1]

books = Book.objects.annotate(latest_rating=Subquery(latest_review))

# After (JOIN-based, fewer points)
from django.db.models import Max
books = Book.objects.annotate(latest_rating=Max("reviews__rating"))
```

!!! warning "Premature Optimization"
    A high complexity score does not necessarily mean the query is slow. The
    database query planner may handle complex queries efficiently, especially
    with proper indexes. Always measure actual query time with `EXPLAIN
    ANALYZE` before investing effort in restructuring. The analyzer provides
    awareness, not a mandate.

!!! tip "Using EXPLAIN"
    Django 4.0+ supports `queryset.explain()` which runs `EXPLAIN` on the
    query. Use `queryset.explain(analyze=True)` in development to see actual
    execution times and whether the planner chooses efficient access paths
    despite query complexity.
