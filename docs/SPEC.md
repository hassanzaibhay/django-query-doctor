# django-query-doctor — Phase 1 Technical Specification

This document is the source of truth for implementation. Claude Code should reference this
when implementing any module.

## 1. Project Scaffold

### pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "django-query-doctor"
version = "0.1.0"
description = "Automated diagnosis and prescriptions for slow Django ORM queries"
readme = "README.md"
license = "MIT"
requires-python = ">=3.10"
authors = [{ name = "Hassan", email = "hassanzaib.hay@gmail.com" }]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: Django",
    "Framework :: Django :: 4.2",
    "Framework :: Django :: 5.0",
    "Framework :: Django :: 5.1",
    "Framework :: Django :: 5.2",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Database",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Topic :: Software Development :: Quality Assurance",
]
keywords = ["django", "orm", "query", "optimization", "n+1", "performance"]
dependencies = ["django>=4.2"]

[project.optional-dependencies]
rich = ["rich>=13.0"]
dev = [
    "pytest>=8.0",
    "pytest-django>=4.7",
    "pytest-cov>=4.0",
    "factory-boy>=3.3",
    "ruff>=0.4",
    "mypy>=1.8",
    "django-stubs>=4.2",
    "djangorestframework>=3.14",
]

[project.urls]
Homepage = "https://github.com/hassanzaibhay/django-query-doctor"
Repository = "https://github.com/hassanzaibhay/django-query-doctor"
Issues = "https://github.com/hassanzaibhay/django-query-doctor/issues"
Documentation = "https://github.com/hassanzaibhay/django-query-doctor#readme"

[tool.hatch.build.targets.wheel]
packages = ["src/query_doctor"]

[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "tests.settings"
pythonpath = ["src"]
addopts = "-v --tb=short"

[tool.ruff]
src = ["src", "tests"]
line-length = 99
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "SIM", "RUF"]

[tool.mypy]
python_version = "3.10"
plugins = ["mypy_django_plugin.main"]
strict = true
warn_return_any = true

[tool.django-stubs]
django_settings_module = "tests.settings"
```

### Test Django Project (tests/)

```python
# tests/settings.py
SECRET_KEY = "test-secret-key-not-for-production"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "query_doctor",
    "tests.testapp",
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
QUERY_DOCTOR = {}  # use all defaults
```

```python
# tests/testapp/models.py
from django.db import models

class Publisher(models.Model):
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100, db_index=True)

    class Meta:
        app_label = "testapp"

class Author(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)  # Large field, good for .defer() testing
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="authors")

    class Meta:
        app_label = "testapp"

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        app_label = "testapp"

class Book(models.Model):
    title = models.CharField(max_length=300)
    isbn = models.CharField(max_length=13, unique=True)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="books")
    categories = models.ManyToManyField(Category, related_name="books", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    description = models.TextField(blank=True)  # Large field
    published_date = models.DateField(null=True)
    # NO index on published_date — good for missing index testing

    class Meta:
        app_label = "testapp"

class Review(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    reviewer_name = models.CharField(max_length=200)
    rating = models.IntegerField()
    content = models.TextField()

    class Meta:
        app_label = "testapp"
```

```python
# tests/factories.py
import factory
from tests.testapp.models import Publisher, Author, Book, Category, Review

class PublisherFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Publisher
    name = factory.Sequence(lambda n: f"Publisher {n}")
    country = "US"

class AuthorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Author
    name = factory.Sequence(lambda n: f"Author {n}")
    email = factory.LazyAttribute(lambda o: f"{o.name.lower().replace(' ', '.')}@example.com")
    bio = "A prolific author."
    publisher = factory.SubFactory(PublisherFactory)

class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category
    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))

class BookFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Book
    title = factory.Sequence(lambda n: f"Book {n}")
    isbn = factory.Sequence(lambda n: f"{n:013d}")
    author = factory.SubFactory(AuthorFactory)
    publisher = factory.SubFactory(PublisherFactory)
    price = factory.LazyFunction(lambda: 19.99)

class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review
    book = factory.SubFactory(BookFactory)
    reviewer_name = factory.Sequence(lambda n: f"Reviewer {n}")
    rating = 4
    content = "Great book!"
```

## 2. Core Data Structures

These MUST be implemented exactly as specified. They are the contract between all modules.

```python
# src/query_doctor/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class Severity(Enum):
    CRITICAL = "critical"   # N+1 with 10+ queries
    WARNING = "warning"     # N+1 with 3-9, duplicates
    INFO = "info"           # Suggestions (only, defer)
    
class IssueType(Enum):
    N_PLUS_ONE = "n_plus_one"
    DUPLICATE_QUERY = "duplicate_query"
    MISSING_INDEX = "missing_index"
    FAT_SELECT = "fat_select"
    QUERYSET_EVAL = "queryset_eval"
    DRF_SERIALIZER = "drf_serializer"

@dataclass(frozen=True)
class CallSite:
    """Where in user code a query originated."""
    filepath: str
    line_number: int
    function_name: str
    code_context: str = ""  # The actual line of code if available

@dataclass(frozen=True)
class CapturedQuery:
    """A single SQL query captured during a request."""
    sql: str
    params: tuple[Any, ...] | None
    duration_ms: float
    fingerprint: str       # Normalized SQL hash
    normalized_sql: str    # SQL with params replaced by ?
    callsite: CallSite | None
    is_select: bool
    tables: list[str]      # Tables referenced in the query

@dataclass
class Prescription:
    """A diagnosed issue with an actionable fix."""
    issue_type: IssueType
    severity: Severity
    description: str          # Human-readable: "N+1 detected: 47 queries for Author"
    fix_suggestion: str       # Exact code: "Add .select_related('author') to queryset"
    callsite: CallSite | None
    query_count: int = 0      # How many queries this issue involves
    time_saved_ms: float = 0  # Estimated time saved if fixed
    fingerprint: str = ""     # Which query pattern this relates to
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class DiagnosisReport:
    """Complete report for one request/context."""
    prescriptions: list[Prescription] = field(default_factory=list)
    total_queries: int = 0
    total_time_ms: float = 0
    captured_queries: list[CapturedQuery] = field(default_factory=list)
    
    @property
    def issues(self) -> int:
        return len(self.prescriptions)
    
    @property
    def n_plus_one_count(self) -> int:
        return sum(1 for p in self.prescriptions if p.issue_type == IssueType.N_PLUS_ONE)
    
    @property
    def has_critical(self) -> bool:
        return any(p.severity == Severity.CRITICAL for p in self.prescriptions)
```

## 3. Module Implementation Details

### 3.1 interceptor.py

The execute_wrapper callable. This is the foundation everything else builds on.

```
class QueryInterceptor:
    """Callable that wraps database query execution to capture SQL queries."""
    
    - Uses threading.local() to store captured queries per-thread
    - __call__(self, execute, sql, params, many, context):
        1. Capture stack trace BEFORE execute (if enabled in config)
        2. Record start time with time.perf_counter()
        3. Call execute(sql, params, many, context)  — MUST always call this
        4. Record end time
        5. Build CapturedQuery with: sql, params, duration, fingerprint, callsite
        6. Append to thread-local list
        7. Return the execute result
    - CRITICAL: Wrap everything in try/except. If OUR code fails, log warning, 
      still return execute result. Never break the host app.
    - get_queries() -> list[CapturedQuery]: return captured queries for this thread
    - clear(): reset the thread-local query list
```

### 3.2 fingerprint.py

```
def normalize_sql(sql: str) -> str:
    """Replace literals with ?, collapse whitespace, lowercase."""
    - Replace quoted strings ('...' and "...") with ?
    - Replace numbers (integers and floats) with ?
    - Replace IN (...) lists with IN (?)
    - Replace boolean literals TRUE/FALSE with ?
    - Collapse whitespace
    - Strip trailing semicolons
    - Lowercase everything
    
def fingerprint(sql: str) -> str:
    """SHA-256 hash of normalized SQL."""
    return hashlib.sha256(normalize_sql(sql).encode()).hexdigest()[:16]

def extract_tables(sql: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses."""
    - Regex-based extraction
    - Handle: FROM table, JOIN table, FROM table AS alias
    - Return list of table names (without aliases, without schema prefix)
```

### 3.3 stack_tracer.py

```
def capture_callsite(exclude_modules: list[str] | None = None) -> CallSite | None:
    """Walk the stack and find the first frame in user code."""
    - Use traceback.extract_stack()
    - Filter out frames from:
        - query_doctor package itself
        - django.db.backends
        - django.db.models.sql
        - django.db.models.query
        - Python stdlib (importlib, threading, etc.)
        - Any module in exclude_modules config
    - Take the LAST remaining frame (closest to the query trigger)
    - Return CallSite with filepath, line_number, function_name
    - Try to read the actual source line with linecache.getline()
    - If ANYTHING fails, return None (never crash)
```

### 3.4 analyzers/base.py

```python
from abc import ABC, abstractmethod

class BaseAnalyzer(ABC):
    """Base class for all query analyzers."""
    
    name: str  # e.g., "nplusone"
    
    @abstractmethod
    def analyze(
        self, 
        queries: list[CapturedQuery],
        models_meta: dict | None = None,
    ) -> list[Prescription]:
        """Analyze captured queries and return prescriptions."""
        ...
    
    def is_enabled(self) -> bool:
        """Check if this analyzer is enabled in config."""
        ...
```

### 3.5 analyzers/nplusone.py

**This is the highest-priority analyzer. Get this right.**

Algorithm:
1. Group `queries` by `fingerprint`
2. For each fingerprint group with `count >= threshold` (default 3):
   a. Check if it's a SELECT query
   b. Extract the table name from the query
   c. Check if the WHERE clause has a single FK-like condition 
      (e.g., `WHERE "author_id" = ?` or `WHERE "book_id" = ?`)
   d. If yes → this is an N+1 pattern
3. Use Django's model `_meta` to determine:
   a. Which model owns the table being queried (the "one" side)
   b. What field on the parent model relates to it
   c. Whether it's FK/O2O (→ select_related) or M2M/reverse FK (→ prefetch_related)
4. Generate Prescription with:
   - Exact field name for select_related/prefetch_related
   - The callsite where the loop is happening
   - Count of queries that would be eliminated

Edge cases to handle:
- Multiple N+1 patterns in same request (e.g., book.author AND book.publisher)
- Nested N+1 (book.author.publisher) — detect as separate prescriptions
- Non-model tables (auth_user, django_session) — skip gracefully
- Raw SQL queries that look like N+1 but aren't ORM-generated — skip

### 3.6 analyzers/duplicate.py

Algorithm:
1. Group queries by (fingerprint + params_hash) → exact duplicates
2. Any group with count >= 2 → duplicate query issue
3. Also group by fingerprint alone → near-duplicates (same structure, different params)
4. For near-duplicates from the SAME callsite with count >= threshold:
   suggest consolidation with filter(id__in=[...])

### 3.7 reporters/console.py

Output format (use Rich if available, plain text fallback):

```
╭─── Query Doctor Report ───────────────────────────────╮
│ Total queries: 53 | Time: 127.3ms | Issues: 3         │
╰────────────────────────────────────────────────────────╯

🔴 CRITICAL: N+1 Query Detected
   47 queries for table "testapp_author"
   Location: myapp/views.py:83 in BookListView.get_queryset
   
   Fix: Add .select_related('author') to your queryset
   
   books = Book.objects.all()
                       ↓
   books = Book.objects.select_related('author').all()
   
   Estimated savings: ~45 queries, ~89ms

🟡 WARNING: Duplicate Queries
   6 identical queries for table "testapp_publisher"  
   Location: myapp/views.py:91 in get_context_data
   
   Fix: Assign the queryset result to a variable and reuse it
```

### 3.8 middleware.py

```
class QueryDoctorMiddleware:
    """Django middleware that activates query diagnosis per request."""
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Validate config on startup
    
    def __call__(self, request):
        # 1. Check if enabled + sampling
        # 2. Check URL against ignore list
        # 3. Install execute_wrapper on connection
        # 4. Call get_response(request)
        # 5. Collect captured queries
        # 6. Run all enabled analyzers
        # 7. Send report to all enabled reporters
        # 8. Return response
        
    IMPORTANT:
    - Use connection.execute_wrapper() as context manager
    - Handle multi-db: iterate connections if needed (start with 'default' only)
    - NEVER crash the request. Wrap analysis in try/except.
```

### 3.9 conf.py

```
DEFAULT_CONFIG = {
    "ENABLED": True,
    "SAMPLE_RATE": 1.0,
    "CAPTURE_STACK_TRACES": True,
    "STACK_TRACE_EXCLUDE": [],
    "ANALYZERS": {
        "nplusone": {"enabled": True, "threshold": 3},
        "duplicate": {"enabled": True, "threshold": 2},
    },
    "REPORTERS": ["console"],
    "IGNORE_PATTERNS": [],
    "IGNORE_URLS": [],
    "QUERY_BUDGET": {"DEFAULT_MAX_QUERIES": None, "DEFAULT_MAX_TIME_MS": None},
}

def get_config() -> dict:
    """Merge user settings with defaults. Cache the result."""
    from django.conf import settings
    user_config = getattr(settings, "QUERY_DOCTOR", {})
    # Deep merge user_config over DEFAULT_CONFIG
    ...
```

### 3.10 context_managers.py

```python
@contextmanager
def diagnose_queries(**kwargs) -> Generator[DiagnosisReport, None, None]:
    """Context manager for targeted query diagnosis."""
    report = DiagnosisReport()
    interceptor = QueryInterceptor()
    
    from django.db import connection
    with connection.execute_wrapper(interceptor):
        yield report
    
    # After context exits, run analysis
    queries = interceptor.get_queries()
    report.captured_queries = queries
    report.total_queries = len(queries)
    report.total_time_ms = sum(q.duration_ms for q in queries)
    
    # Run analyzers
    for analyzer in get_enabled_analyzers():
        report.prescriptions.extend(analyzer.analyze(queries))
```

## 4. Implementation Order (Phase 1)

Execute in EXACTLY this order. Each step depends on the previous.

| Step | Module | Depends On | Tests First |
|------|--------|------------|-------------|
| 1 | Project scaffold + pyproject.toml + test models | Nothing | conftest.py + test_models.py |
| 2 | types.py (data structures) | Nothing | test_types.py |
| 3 | fingerprint.py | Nothing | test_fingerprint.py |
| 4 | stack_tracer.py | Nothing | test_stack_tracer.py |
| 5 | interceptor.py | fingerprint, stack_tracer | test_interceptor.py |
| 6 | conf.py | Nothing | test_conf.py |
| 7 | analyzers/base.py | types | (tested via subclasses) |
| 8 | analyzers/nplusone.py | base, types | test_nplusone.py |
| 9 | analyzers/duplicate.py | base, types | test_duplicate.py |
| 10 | reporters/console.py | types | test_console_reporter.py |
| 11 | middleware.py | interceptor, analyzers, reporters, conf | test_middleware.py |
| 12 | context_managers.py | interceptor, analyzers | test_context_managers.py |
| 13 | __init__.py public API | everything | test_public_api.py |
| 14 | README.md + docs/ | everything | N/A |

## 5. Test Scenarios (Must-Pass)

### N+1 Detection (test_nplusone.py)
```python
def test_detects_fk_nplusone():
    """Iterating books and accessing .author without select_related → N+1 detected."""
    # Create 5 books with different authors
    # Loop: for book in Book.objects.all(): book.author.name
    # Assert: 1 prescription with IssueType.N_PLUS_ONE
    # Assert: fix_suggestion contains "select_related('author')"

def test_no_false_positive_with_select_related():
    """Using select_related → no N+1 reported."""
    # Book.objects.select_related('author') + loop accessing .author
    # Assert: 0 prescriptions

def test_detects_m2m_nplusone():
    """Iterating books and accessing .categories.all() without prefetch → N+1."""
    # Assert: fix_suggestion contains "prefetch_related('categories')"

def test_multiple_nplusone_patterns():
    """Accessing both .author and .publisher → 2 separate prescriptions."""

def test_below_threshold_not_flagged():
    """Only 2 similar queries (below default threshold 3) → no issue."""
```

### Duplicate Detection (test_duplicate.py)
```python
def test_detects_exact_duplicates():
    """Same query executed 3 times → duplicate detected."""

def test_no_false_positive_different_queries():
    """Different queries → no duplicate flagged."""

def test_near_duplicates_from_same_callsite():
    """Same structure, different params, same callsite → consolidation suggestion."""
```

### Fingerprint (test_fingerprint.py)
```python
def test_same_structure_different_params_same_fingerprint():
    """SELECT * FROM book WHERE id = 1 and WHERE id = 42 → same fingerprint."""

def test_different_tables_different_fingerprint():
    """SELECT * FROM book vs SELECT * FROM author → different fingerprints."""

def test_in_clause_normalization():
    """WHERE id IN (1,2,3) and WHERE id IN (4,5) → same fingerprint."""

def test_whitespace_normalization():
    """Extra spaces/newlines don't change fingerprint."""
```

## 6. CI Workflow (.github/workflows/ci.yml)

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
        django-version: ["4.2", "5.0", "5.1"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]" django==${{ matrix.django-version }}.*
      - run: pytest --cov=query_doctor --cov-report=xml
      - run: ruff check src/ tests/
      - run: mypy src/query_doctor/
  
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff
      - run: ruff check src/ tests/
      - run: ruff format src/ tests/ --check
```
