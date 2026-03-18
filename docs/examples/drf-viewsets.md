# DRF ViewSet Examples

Django REST Framework viewsets and generic views have specific patterns that
commonly lead to N+1 queries. This page covers the most frequent scenarios
and how django-query-doctor detects and fixes them.

---

## ModelViewSet with Nested Serializers

### The Problem

```python title="books/serializers.py"
from rest_framework import serializers
from books.models import Book, Chapter


class ChapterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chapter
        fields = ["id", "title", "page_count"]


class BookSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.name", read_only=True)
    publisher_name = serializers.CharField(source="publisher.name", read_only=True)
    chapters = ChapterSerializer(many=True, read_only=True, source="chapter_set")
    category_names = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name", source="categories",
    )

    class Meta:
        model = Book
        fields = [
            "id", "title", "author_name", "publisher_name",
            "chapters", "category_names", "published_date",
        ]
```

```python title="books/views.py"
from rest_framework.viewsets import ModelViewSet
from books.models import Book
from books.serializers import BookSerializer


class BookViewSet(ModelViewSet):
    serializer_class = BookSerializer
    queryset = Book.objects.all()
```

### The Fix

Override `get_queryset` to add the necessary joins and prefetches:

```python title="books/views.py"
from rest_framework.viewsets import ModelViewSet
from books.models import Book
from books.serializers import BookSerializer


class BookViewSet(ModelViewSet):
    serializer_class = BookSerializer

    def get_queryset(self):
        """Optimize queryset based on the action being performed."""
        qs = Book.objects.all()

        if self.action == "list":
            # List needs all relations for the serializer
            qs = qs.select_related(
                "author",
                "publisher",
            ).prefetch_related(
                "chapter_set",
                "categories",
            )
        elif self.action == "retrieve":
            # Retrieve also needs all relations
            qs = qs.select_related(
                "author",
                "publisher",
            ).prefetch_related(
                "chapter_set",
                "categories",
            )
        # create/update/delete don't need prefetching

        return qs
```

!!! tip "Action-aware optimization"
    Different ViewSet actions may need different prefetch strategies.
    `list` often needs the most prefetching, while `create` and `update`
    rarely need any. Use `self.action` to optimize only when necessary.

---

## ListAPIView with Filtering

### The Problem

Filtering does not change the need for prefetching, but developers often
forget to add it when using `django-filter` or custom filtering:

```python title="products/views.py"
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import ListAPIView
from products.models import Product
from products.serializers import ProductSerializer


class ProductListView(ListAPIView):
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["category", "brand", "in_stock"]
    queryset = Product.objects.all()  # Missing prefetch
```

### The Fix

```python title="products/views.py"
class ProductListView(ListAPIView):
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["category", "brand", "in_stock"]
    queryset = Product.objects.select_related(
        "category",
        "brand",
    ).prefetch_related(
        "tags",
        "images",
    )
```

!!! note "Filters and prefetch"
    `select_related` and `prefetch_related` work correctly with
    `django-filter`. The filter is applied before prefetching executes,
    so you only prefetch related objects for the filtered result set.

---

## SerializerMethodField Patterns

`SerializerMethodField` is a common source of hidden N+1 queries because the
database access is buried inside a method rather than being visible in field
declarations.

### The Problem

```python title="users/serializers.py"
class UserSerializer(serializers.ModelSerializer):
    recent_orders_count = serializers.SerializerMethodField()
    last_login_device = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "recent_orders_count", "last_login_device"]

    def get_recent_orders_count(self, obj):
        # This executes a COUNT query for EVERY user in the list
        return obj.orders.filter(created_at__gte=thirty_days_ago).count()

    def get_last_login_device(self, obj):
        # This executes a query for EVERY user in the list
        session = obj.login_sessions.order_by("-created_at").first()
        return session.device_name if session else None
```

### The Fix: Use Annotations

Replace method-level queries with queryset annotations:

```python title="users/views.py"
from django.db.models import Count, Q, Subquery, OuterRef
from django.utils import timezone


class UserListView(ListAPIView):
    serializer_class = UserSerializer

    def get_queryset(self):
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)

        latest_session = LoginSession.objects.filter(
            user=OuterRef("pk"),
        ).order_by("-created_at").values("device_name")[:1]

        return User.objects.annotate(
            recent_orders_count=Count(
                "orders",
                filter=Q(orders__created_at__gte=thirty_days_ago),
            ),
            last_login_device=Subquery(latest_session),
        )
```

```python title="users/serializers.py"
class UserSerializer(serializers.ModelSerializer):
    recent_orders_count = serializers.IntegerField(read_only=True)
    last_login_device = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "recent_orders_count", "last_login_device"]
```

!!! warning "SerializerMethodField audit"
    django-query-doctor's DRF Serializer analyzer specifically looks for
    database access inside `SerializerMethodField` methods. If you see
    prescriptions pointing at `get_*` methods, annotations are almost
    always the correct fix.

---

## Pagination and Prefetch Interaction

### The Problem

Django REST Framework's pagination evaluates the queryset (to get the count
and the page slice) before serialization. Prefetching works correctly with
pagination, but there is a subtle performance consideration:

```python title="articles/views.py"
class ArticleListView(ListAPIView):
    serializer_class = ArticleSerializer
    pagination_class = PageNumberPagination
    queryset = Article.objects.prefetch_related(
        "tags",
        "comments",
        "comments__author",
    )
```

### How It Works

With a page size of 25 and 10,000 total articles:

1. DRF calls `queryset.count()` -- 1 query (no prefetch executed)
2. DRF slices `queryset[offset:offset+25]` -- 1 query
3. Django executes prefetch queries for the 25 articles on the page -- 3 queries

Total: 5 queries regardless of total article count.

!!! info "Prefetch is pagination-aware"
    Django is smart about prefetching: it only prefetches related objects for
    the objects in the evaluated queryset slice, not for the entire table.
    You do not need to worry about prefetching all 10,000 articles' related
    data.

### Cursor Pagination for Large Tables

For very large tables, switch from `PageNumberPagination` (which requires a
`COUNT(*)`) to `CursorPagination`:

```python title="articles/views.py"
from rest_framework.pagination import CursorPagination


class ArticleCursorPagination(CursorPagination):
    page_size = 25
    ordering = "-published_at"


class ArticleListView(ListAPIView):
    serializer_class = ArticleSerializer
    pagination_class = ArticleCursorPagination
    queryset = Article.objects.select_related(
        "author",
    ).prefetch_related(
        "tags",
    )
```

---

## Generic Views with get_queryset Optimization

### The Pattern

For views that serve both list and detail endpoints, optimize the queryset
based on the context:

```python title="projects/views.py"
from rest_framework.generics import ListAPIView, RetrieveAPIView


class ProjectListView(ListAPIView):
    serializer_class = ProjectListSerializer

    def get_queryset(self):
        """List view: lightweight fields only."""
        return Project.objects.select_related(
            "owner",
        ).only(
            "id", "name", "owner__username", "created_at", "status",
        )


class ProjectDetailView(RetrieveAPIView):
    serializer_class = ProjectDetailSerializer

    def get_queryset(self):
        """Detail view: full data with all relations."""
        return Project.objects.select_related(
            "owner",
            "organization",
        ).prefetch_related(
            "members",
            "tags",
            Prefetch(
                "task_set",
                queryset=Task.objects.select_related("assignee").order_by("-created_at")[:50],
            ),
        )
```

!!! tip "Use .only() for list views"
    List views typically display a subset of fields. Using `.only()` reduces
    the data transferred from the database. django-query-doctor's Fat SELECT
    analyzer will flag cases where you are fetching columns that the
    serializer never accesses.

### Combined ViewSet Pattern

```python title="projects/views.py"
from rest_framework.viewsets import ModelViewSet


class ProjectViewSet(ModelViewSet):
    def get_serializer_class(self):
        if self.action == "list":
            return ProjectListSerializer
        return ProjectDetailSerializer

    def get_queryset(self):
        qs = Project.objects.all()

        if self.action == "list":
            qs = qs.select_related("owner").only(
                "id", "name", "owner__username", "status",
            )
        elif self.action in ("retrieve", "update", "partial_update"):
            qs = qs.select_related(
                "owner", "organization",
            ).prefetch_related(
                "members", "tags", "task_set",
            )

        return qs
```

---

## Quick Reference

| DRF Pattern | Common Issue | Fix |
|-------------|-------------|-----|
| `source="fk.field"` on serializer field | N+1 on FK | `select_related('fk')` in `get_queryset` |
| Nested `ModelSerializer` with `many=True` | N+1 on reverse FK / M2M | `prefetch_related('child_set')` in `get_queryset` |
| `SerializerMethodField` with DB query | Hidden N+1 | Annotate on queryset, use plain serializer field |
| `SlugRelatedField` on M2M | N+1 on M2M | `prefetch_related('m2m_field')` in `get_queryset` |
| ViewSet with no `get_queryset` override | All of the above | Override `get_queryset` per action |

See also: [Real-World Examples](real-world.md) | [Large Codebase Strategies](large-codebases.md)
