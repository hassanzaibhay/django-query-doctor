# Examples

Practical examples showing how django-query-doctor diagnoses and fixes query performance issues in production-like scenarios.

!!! note "Illustrative numbers"
    Response times and improvement percentages are illustrative estimates. Your results vary by database, dataset size, and hardware.

---

## E-Commerce: Order API with Nested Serializers

An order list endpoint with nested items and customer info. With 50 orders, the naive implementation produces **251 queries**.

```python title="orders/views.py"
class OrderListView(ListAPIView):
    serializer_class = OrderSerializer
    queryset = Order.objects.all()  # No prefetching
```

Prescription output:

```
[CRITICAL] N+1 Query — 50 queries fetching Customer for each Order
  Location: orders/views.py:9
  Fix: select_related('customer')

[CRITICAL] N+1 Query — 150 queries fetching Product for each OrderItem
  Fix: Prefetch('orderitem_set', queryset=OrderItem.objects.select_related('product'))
```

The fix:

```python title="orders/views.py"
class OrderListView(ListAPIView):
    serializer_class = OrderSerializer
    queryset = Order.objects.select_related(
        "customer",
    ).prefetch_related(
        Prefetch("orderitem_set", queryset=OrderItem.objects.select_related("product")),
    )
```

**Result: 251 → 3 queries. Response time: 1,240ms → 45ms.**

---

## DRF ViewSet with Action-Aware Optimization

Different ViewSet actions need different prefetch strategies. `list` needs the most prefetching; `create` needs none.

```python title="books/views.py"
class BookViewSet(ModelViewSet):
    serializer_class = BookSerializer

    def get_queryset(self):
        qs = Book.objects.all()
        if self.action in ("list", "retrieve"):
            qs = qs.select_related(
                "author", "publisher",
            ).prefetch_related("chapter_set", "categories")
        return qs
```

---

## SerializerMethodField Hidden N+1

`SerializerMethodField` methods hide database access inside Python code. The AST analyzer (`check_serializers`) catches these statically.

```python title="users/serializers.py"
class UserSerializer(serializers.ModelSerializer):
    recent_orders_count = serializers.SerializerMethodField()

    def get_recent_orders_count(self, obj):
        return obj.orders.filter(created_at__gte=thirty_days_ago).count()  # N+1
```

Fix: replace with queryset annotation.

```python title="users/views.py"
class UserListView(ListAPIView):
    def get_queryset(self):
        return User.objects.annotate(
            recent_orders_count=Count("orders", filter=Q(orders__created_at__gte=thirty_days_ago)),
        )
```

```python title="users/serializers.py"
class UserSerializer(serializers.ModelSerializer):
    recent_orders_count = serializers.IntegerField(read_only=True)  # From annotation
```

---

## Large Codebase: Incremental Adoption

For large projects, avoid overwhelming developers with hundreds of prescriptions at once.

| Strategy | When to Use |
|----------|------------|
| Middleware off + CI commands | Large existing codebases — analysis in CI only |
| `--diff origin/main` | Active development — analyze only changed files |
| `.queryignore` | Suppress accepted trade-offs and false positives |
| `--app orders` | Monoliths — scan one Django app at a time |
| `@query_budget(max_queries=10)` | Enforce hard limits on critical endpoints |

Recommended rollout timeline:

| Week | Action |
|------|--------|
| 1–2 | Enable N+1 analyzer only, CI warning mode |
| 3–4 | Fix critical N+1s, add `.queryignore` for accepted ones |
| 5–6 | Enable duplicate analyzer |
| 7–8 | Enable remaining analyzers, set query budgets |
| 9+ | Enforce in CI (`--fail-on critical`), tighten budgets |

---

## Common Fix Patterns

| Pattern | Symptom | Fix |
|---------|---------|-----|
| FK access in serializer field | N+1 on parent queryset | `select_related('fk_field')` |
| Reverse FK / M2M in nested serializer | N+1 on child set | `prefetch_related('child_set')` |
| FK on a prefetched child | N+1 within prefetch | `Prefetch('child_set', queryset=Child.objects.select_related('fk'))` |
| `SerializerMethodField` with query | Hidden N+1 | Annotate at the queryset level |

---

## Next Steps

- [Management Commands](../guides/management-commands.md) — full CLI reference
- [CI/CD Integration](../guides/ci-integration.md) — automated checks in pipelines
- [Query Ignore](../guides/query-ignore.md) — suppressing known issues
