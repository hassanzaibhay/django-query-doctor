# Query Complexity Analyzer

## What It Detects

The query complexity analyzer scores each SQL query based on the number and
type of expensive operations it contains. Queries that exceed a configurable
complexity threshold are flagged with suggestions for simplification. The goal
is to catch queries that have grown unwieldy through chained ORM calls and may
benefit from being broken apart or restructured.

## Scoring Table

Each SQL feature contributes points to the total complexity score:

| SQL Feature | Points per Occurrence | Example ORM Usage |
|-------------|----------------------|-------------------|
| `JOIN` (each) | 5 | `select_related()`, `annotate()` with relations |
| Subquery (each) | 10 | `Subquery()`, `qs.filter(id__in=other_qs)` |
| Aggregation (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`) | 3 | `.annotate(total=Sum(...))` |
| `CASE / WHEN` (each) | 4 | `Case(When(...))` |
| `DISTINCT` | 3 | `.distinct()` |
| `UNION` / `INTERSECT` / `EXCEPT` | 8 | `qs1.union(qs2)` |
| `GROUP BY` | 3 | `.values().annotate()` |
| `HAVING` | 4 | `.annotate().filter()` after group |
| `ORDER BY` on expression | 2 | `.order_by(F("field").desc())` |
| Window function | 8 | `Window(expression=..., partition_by=...)` |

The total score is the sum of all points. The default threshold is **50**.

## Problem Code

```python
# views.py

from django.db.models import (
    Case, Count, F, Q, Subquery, OuterRef, Sum, When, Window
)
from django.db.models.functions import Rank

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
        .select_related("author", "publisher")                  # 2 JOINs = 10
        .prefetch_related("categories")
        .annotate(
            review_count=Count("reviews"),                      # aggregation = 3
            avg_rating=Subquery(subquery),                      # subquery = 10
            revenue=Sum("sales__amount"),                       # aggregation = 3, JOIN = 5
            tier=Case(                                          # CASE = 4
                When(revenue__gte=10000, then=Value("gold")),
                When(revenue__gte=1000, then=Value("silver")),
                default=Value("bronze"),
            ),
            rank=Window(                                        # window = 8
                expression=Rank(),
                partition_by=F("publisher"),
                order_by=F("revenue").desc(),
            ),
        )
        .filter(review_count__gte=5)                            # HAVING = 4
        .distinct()                                              # DISTINCT = 3
        .order_by("-rank")
    )
    # Total score: 10 + 3 + 10 + 3 + 5 + 4 + 8 + 4 + 3 = 50 (at threshold)
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

```
[LOW] High Query Complexity (score: 54)
  Location: views.py:12
  Issue:    Query has a complexity score of 54 (threshold: 50).
            Breakdown: 2 JOINs (10), 1 subquery (10), 2 aggregations (6),
            1 CASE/WHEN (4), 1 window function (8), 1 DISTINCT (3),
            1 HAVING (4), expression ORDER BY (2), GROUP BY (3).
  Fix:      Consider breaking this into multiple simpler queries.
            - Extract the subquery into a separate query and join in Python.
            - Move the window function to a dedicated annotation query.
            - Use .annotate() with JOIN-based aggregation instead of Subquery
              where possible.
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `COMPLEXITY_THRESHOLD` | `50` | Total score above which a query is flagged. Lower values catch more queries but may produce noise. |
| `COMPLEXITY_IGNORE_TABLES` | `[]` | Tables to exclude from analysis. Reporting queries against analytics tables are often intentionally complex. |

```python
# settings.py
QUERY_DOCTOR = {
    "COMPLEXITY_THRESHOLD": 40,
    "COMPLEXITY_IGNORE_TABLES": ["analytics_report"],
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
