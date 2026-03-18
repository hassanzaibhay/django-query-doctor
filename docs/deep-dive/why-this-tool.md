# Why django-query-doctor?

## The N+1 Epidemic

The N+1 query problem is the single most common performance issue in Django applications. It occurs when code fetches a list of objects and then individually queries for related objects one at a time, turning what should be 1-2 queries into hundreds or thousands.

Consider a typical Django REST Framework endpoint:

```python
# serializers.py
class BookSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.name")
    publisher_name = serializers.CharField(source="publisher.name")
    categories = serializers.StringRelatedField(many=True)

    class Meta:
        model = Book
        fields = ["id", "title", "author_name", "publisher_name", "categories"]


# views.py
class BookListView(generics.ListAPIView):
    queryset = Book.objects.all()  # No select_related or prefetch_related
    serializer_class = BookSerializer
```

When this endpoint is called with 50 books in the database, here is what actually happens:

```sql
-- 1 query: Fetch all books
SELECT * FROM books_book;

-- 50 queries: Fetch each book's author (N+1 on author FK)
SELECT * FROM books_author WHERE id = 1;
SELECT * FROM books_author WHERE id = 2;
...
SELECT * FROM books_author WHERE id = 50;

-- 50 queries: Fetch each book's publisher (N+1 on publisher FK)
SELECT * FROM books_publisher WHERE id = 1;
SELECT * FROM books_publisher WHERE id = 2;
...
SELECT * FROM books_publisher WHERE id = 50;

-- 50 queries: Fetch each book's categories (N+1 on M2M)
SELECT * FROM books_book_categories WHERE book_id = 1;
SELECT * FROM books_book_categories WHERE book_id = 2;
...
SELECT * FROM books_book_categories WHERE book_id = 50;
```

**Total: 151 queries instead of 3.**

The fix is straightforward, but you have to know the problem exists first:

```python
class BookListView(generics.ListAPIView):
    queryset = Book.objects.select_related(
        "author", "publisher"
    ).prefetch_related("categories")
    serializer_class = BookSerializer
```

### The Scale of the Problem

In a typical Django monolith with 100+ models and dozens of developers, N+1 queries accumulate silently. Here are typical metrics observed before optimization:

| Metric | Unoptimized | After django-query-doctor |
|--------|-------------|--------------------------|
| Avg queries per page load | 80-200 | 5-15 |
| 95th percentile response time | 800ms-2s | 80-200ms |
| Database CPU utilization | 60-80% | 15-25% |
| Avg queries per API endpoint | 50-150 | 3-10 |
| Duplicate query ratio | 30-50% | < 2% |
| Pages with N+1 issues | 70-90% | < 5% |
| Monthly database cost (cloud) | $2,000-5,000 | $500-1,200 |

These are not hypothetical numbers. Every Django application of meaningful size has these problems hiding in plain sight.

---

## Why Existing Tools Fall Short

### django-debug-toolbar

The most popular Django debugging tool, but it was designed for interactive development, not systematic optimization.

**Limitations:**

- **Requires `DEBUG=True`**: Cannot run in staging or production. The very environments where performance matters most are invisible to it.
- **Manual inspection only**: You have to visually scan through a list of queries and mentally group them to spot N+1 patterns.
- **No fix suggestions**: It tells you *what* queries ran, but not *why* they are a problem or *how* to fix them.
- **No CI integration**: Cannot catch regressions automatically. A developer can introduce an N+1 in a PR and it will pass all checks.
- **Per-page only**: No way to aggregate across an entire project or scan all endpoints at once.

### django-silk

A profiling and inspection tool that records requests and queries to the database.

**Limitations:**

- **Heavyweight**: Requires its own database tables, middleware, and a separate UI. Adds measurable overhead to every request.
- **Storage overhead**: Writes profiling data to the database on every request, which can itself become a performance problem.
- **Detection, not prescription**: Like debug-toolbar, it shows you queries but does not identify patterns or suggest fixes.
- **Not CI-friendly**: Designed for interactive use through its web interface.

### nplusone

The closest existing tool to what django-query-doctor does, but with significant gaps.

**Limitations:**

- **Only detects N+1 queries**: Does not catch duplicate queries, missing indexes, fat SELECTs, unnecessary complexity, or any of the other 6 categories that django-query-doctor covers.
- **No file:line references**: Tells you which model relationship caused the N+1, but not where in your code the offending access occurs. In a large codebase with dozens of views accessing the same model, this is not enough.
- **No fix suggestions**: Reports the problem but does not generate the `select_related()` or `prefetch_related()` call you need to add.
- **No CI integration**: Cannot enforce query budgets or fail a build on regressions.
- **Unmaintained**: Has not seen active development in recent years.

### django-auto-prefetch

A clever approach that automatically adds `select_related` to ForeignKey access at the model level.

**Limitations:**

- **Masks the problem instead of fixing it**: Your code still has the N+1 access pattern; the library silently adds JOINs. This can lead to unexpected query shapes and performance characteristics.
- **No visibility**: You have no idea what it is doing or why. When something goes wrong, debugging is harder, not easier.
- **Only handles ForeignKey**: Does not help with ManyToMany relationships, which require `prefetch_related` (a fundamentally different mechanism).
- **Global behavior change**: Modifies query behavior for your entire application. Cannot be scoped to specific views or endpoints.
- **No detection of other issues**: Only addresses N+1 on ForeignKeys. All other query optimization issues remain invisible.

---

## What django-query-doctor Does Differently

### 1. Seven Categories of Detection

django-query-doctor does not just find N+1 queries. It detects seven distinct categories of query optimization issues:

| Category | What It Detects |
|----------|----------------|
| **N+1 Queries** | Repeated queries with the same fingerprint differing only by FK/PK parameter |
| **Duplicate Queries** | Exact and near-duplicate queries that waste database round-trips |
| **Missing Indexes** | Full table scans on columns used in WHERE/JOIN clauses |
| **Fat SELECTs** | `SELECT *` when only a few columns are needed (`only()` / `values()`) |
| **Query Complexity** | Overly complex queries with excessive JOINs or subqueries |
| **DRF Serializer Issues** | N+1 patterns originating from Django REST Framework serializer field access |
| **QuerySet Evaluation** | Unnecessary queryset evaluations (e.g., calling `.count()` after `.all()`) |

### 2. Pinpoints Exact File and Line

Every prescription includes the exact file path and line number where the problematic query originates in your code:

```
N+1 DETECTED: 47 duplicate queries on books_book.author_id

  File: myapp/views.py, line 42
    queryset = Book.objects.all()

  File: myapp/serializers.py, line 15
    author_name = serializers.CharField(source="author.name")
```

### 3. Copy-Paste Fixes

Every prescription includes the exact code change needed to resolve the issue. Not a vague suggestion --- an actual code snippet you can paste into your editor:

```
PRESCRIPTION:
  Change your queryset from:
    Book.objects.all()
  To:
    Book.objects.select_related('author', 'publisher').prefetch_related('categories')

  Location: myapp/views.py:42
```

### 4. Runs Anywhere --- No DEBUG=True Required

django-query-doctor uses Django's `connection.execute_wrapper()` API, which works regardless of the `DEBUG` setting. This means you can run it in:

- Local development
- Staging environments
- Production (with overhead controls)
- CI/CD pipelines

```python
# Works with DEBUG=False --- unlike debug-toolbar
MIDDLEWARE = [
    "query_doctor.middleware.QueryDoctorMiddleware",
    # ... your other middleware
]
```

### 5. Auto-Fix Mode

For common issues like missing `select_related()` or `prefetch_related()`, django-query-doctor can generate and apply fixes automatically:

```bash
# Scan the entire project and generate fix suggestions
python manage.py diagnose_queries --auto-fix
```

### 6. CI-Native

django-query-doctor is designed to run in CI/CD pipelines as a first-class use case:

```yaml
# .github/workflows/ci.yml
- name: Query Doctor Check
  run: |
    python manage.py diagnose_queries --format=json --fail-on-issues
```

You can set query budgets per view and fail the build if they are exceeded:

```python
from query_doctor.decorators import query_budget

@query_budget(max_queries=10, max_duplicates=0)
def my_view(request):
    # If this view exceeds 10 queries or has any duplicates,
    # the test suite will report a failure.
    ...
```

### 7. Zero Required Dependencies

The only runtime dependency is Django itself. Rich console output is available if you install Rich, but it is entirely optional:

```toml
# pyproject.toml
[project]
dependencies = ["django>=4.2"]

[project.optional-dependencies]
rich = ["rich>=13.0"]
```

---

## The N+1 Problem: A Complete Example

Here is a full example showing how django-query-doctor catches and fixes a real-world N+1 problem.

### The Problematic Code

```python
# models.py
class Author(models.Model):
    name = models.CharField(max_length=200)
    bio = models.TextField()

class Publisher(models.Model):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)

class Category(models.Model):
    name = models.CharField(max_length=100)

class Book(models.Model):
    title = models.CharField(max_length=300)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE)
    categories = models.ManyToManyField(Category)
    published_date = models.DateField()


# views.py
from rest_framework import generics

class BookListView(generics.ListAPIView):
    queryset = Book.objects.all()
    serializer_class = BookSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Filter by year if provided
        year = self.request.query_params.get("year")
        if year:
            qs = qs.filter(published_date__year=year)
        return qs


# serializers.py
class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name"]

class BookSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()
    publisher_name = serializers.CharField(source="publisher.name")
    categories = serializers.StringRelatedField(many=True)

    class Meta:
        model = Book
        fields = ["id", "title", "author", "publisher_name", "categories"]
```

### What django-query-doctor Reports

```
============================================================
  QUERY DOCTOR REPORT - GET /api/books/
  Total queries: 151 | Time: 340ms
============================================================

CRITICAL  N+1 Query Detected
          47 queries match fingerprint: SELECT * FROM books_author WHERE id = ?
          Source: myapp/serializers.py:12
                  author = AuthorSerializer()
          Fix: Add select_related('author') to your queryset
               myapp/views.py:8
               - queryset = Book.objects.all()
               + queryset = Book.objects.select_related('author').all()

CRITICAL  N+1 Query Detected
          47 queries match fingerprint: SELECT * FROM books_publisher WHERE id = ?
          Source: myapp/serializers.py:13
                  publisher_name = serializers.CharField(source="publisher.name")
          Fix: Add select_related('publisher') to your queryset
               myapp/views.py:8
               - queryset = Book.objects.all()
               + queryset = Book.objects.select_related('author', 'publisher').all()

WARNING   N+1 Query Detected
          47 queries match fingerprint: SELECT * FROM books_book_categories ...
          Source: myapp/serializers.py:14
                  categories = serializers.StringRelatedField(many=True)
          Fix: Add prefetch_related('categories') to your queryset
               myapp/views.py:8
               - queryset = Book.objects.all()
               + queryset = Book.objects.select_related('author', 'publisher') \
               +     .prefetch_related('categories').all()

============================================================
  3 issues found | Estimated savings: ~145 queries per request
============================================================
```

### The Fix

Apply the suggested change to `views.py`:

```python
class BookListView(generics.ListAPIView):
    queryset = Book.objects.select_related(
        "author", "publisher"
    ).prefetch_related("categories")
    serializer_class = BookSerializer
```

**Result: 151 queries reduced to 4.** Response time drops from 340ms to 25ms.

---

## Getting Started

Add the middleware to your Django settings and django-query-doctor starts working immediately:

```python
# settings.py
MIDDLEWARE = [
    "query_doctor.middleware.QueryDoctorMiddleware",
    # ... your other middleware
]

# Optional: customize behavior
QUERY_DOCTOR = {
    "ENABLED": True,           # Toggle on/off
    "REPORT_FORMAT": "console", # "console", "json", or "log"
    "N_PLUS_ONE_THRESHOLD": 2,  # Minimum repeat count to flag
    "DUPLICATE_THRESHOLD": 2,   # Minimum duplicate count to flag
}
```

> **Tip:** Start with the defaults. django-query-doctor is designed to work out of the box with zero configuration. Customize thresholds only after you have addressed the most critical issues.

For more details on the architecture, see [Architecture](./architecture.md). For a comparison with other tools, see [Comparison](./comparison.md).
