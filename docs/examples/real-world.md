# Real-World Examples

These examples demonstrate how django-query-doctor diagnoses and fixes query
performance issues in production-like scenarios. Each example shows the original
code, the prescription output, and the optimized solution.

!!! note "Illustrative numbers"
    The response times and improvement percentages in these examples are
    illustrative estimates based on typical Django applications. Your actual
    results will vary depending on database, dataset size, and hardware.

---

## E-Commerce: Order API with Nested Serializers

### The Problem

A typical e-commerce API endpoint that lists orders with their items and
customer information. The naive implementation triggers an N+1 cascade:

```python title="orders/serializers.py"
from rest_framework import serializers
from orders.models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name")

    class Meta:
        model = OrderItem
        fields = ["id", "product_name", "quantity", "unit_price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, source="orderitem_set")
    customer_name = serializers.CharField(source="customer.full_name")

    class Meta:
        model = Order
        fields = ["id", "order_number", "customer_name", "items", "total", "created_at"]
```

```python title="orders/views.py"
from rest_framework.generics import ListAPIView
from orders.models import Order
from orders.serializers import OrderSerializer


class OrderListView(ListAPIView):
    serializer_class = OrderSerializer
    queryset = Order.objects.all()  # No select_related or prefetch_related
```

With 50 orders in the database, this produces **101 queries**:

- 1 query for all orders
- 50 queries fetching `customer` for each order (N+1)
- 50 queries fetching `orderitem_set` for each order (N+1)

And each order item triggers another query for `product`, adding even more.

### Prescription Output

```
 query-doctor  GET /api/orders/ (251 queries, 3 prescriptions)

[CRITICAL] N+1 Query (NPlusOneAnalyzer)
  50 queries fetching Customer for each Order.
  Location: orders/views.py:9 (OrderListView.get_queryset)
  Fix: Add select_related('customer') to queryset
  Suggested code:
    queryset = Order.objects.select_related('customer').all()

[CRITICAL] N+1 Query (NPlusOneAnalyzer)
  50 queries fetching OrderItem set for each Order.
  Location: orders/views.py:9 (OrderListView.get_queryset)
  Fix: Add prefetch_related('orderitem_set') to queryset
  Suggested code:
    queryset = Order.objects.prefetch_related('orderitem_set').all()

[CRITICAL] N+1 Query (NPlusOneAnalyzer)
  150 queries fetching Product for each OrderItem.
  Location: orders/serializers.py:6 (OrderItemSerializer.product_name)
  Fix: Add select_related or prefetch with nested select
  Suggested code:
    queryset = Order.objects.prefetch_related(
        Prefetch('orderitem_set', queryset=OrderItem.objects.select_related('product'))
    ).all()
```

### The Fix

```python title="orders/views.py"
from django.db.models import Prefetch
from rest_framework.generics import ListAPIView

from orders.models import Order, OrderItem
from orders.serializers import OrderSerializer


class OrderListView(ListAPIView):
    serializer_class = OrderSerializer
    queryset = Order.objects.select_related(
        "customer",
    ).prefetch_related(
        Prefetch(
            "orderitem_set",
            queryset=OrderItem.objects.select_related("product"),
        ),
    )
```

**Result: 251 queries reduced to 3 queries.**

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Queries | 251 | 3 | 98.8% fewer |
| Response time | 1,240 ms | 45 ms | 96.4% faster |

!!! tip "Prefetch with nested select_related"
    When a prefetched relation itself has foreign keys that are accessed,
    use `Prefetch()` with a custom queryset that applies `select_related`.
    This is the pattern for multi-level optimization.

---

## Healthcare API: Deep Nested Relations

### The Problem

A healthcare system API that returns patient records with their full visit
history, including diagnoses and medications at each visit:

```python title="patients/serializers.py"
from rest_framework import serializers
from patients.models import Patient, Visit, Diagnosis, Medication


class MedicationSerializer(serializers.ModelSerializer):
    prescribed_by = serializers.CharField(source="doctor.full_name")

    class Meta:
        model = Medication
        fields = ["id", "name", "dosage", "prescribed_by", "start_date"]


class DiagnosisSerializer(serializers.ModelSerializer):
    medications = MedicationSerializer(many=True, source="medication_set")

    class Meta:
        model = Diagnosis
        fields = ["id", "code", "description", "medications", "diagnosed_at"]


class VisitSerializer(serializers.ModelSerializer):
    doctor_name = serializers.CharField(source="doctor.full_name")
    diagnoses = DiagnosisSerializer(many=True, source="diagnosis_set")

    class Meta:
        model = Visit
        fields = ["id", "visit_date", "doctor_name", "diagnoses", "notes"]


class PatientDetailSerializer(serializers.ModelSerializer):
    visits = VisitSerializer(many=True, source="visit_set")
    primary_doctor = serializers.CharField(source="primary_doctor.full_name")

    class Meta:
        model = Patient
        fields = ["id", "name", "dob", "primary_doctor", "visits"]
```

```python title="patients/views.py"
class PatientListView(ListAPIView):
    serializer_class = PatientDetailSerializer
    queryset = Patient.objects.all()
```

For 10 patients, each with 5 visits, each visit with 2 diagnoses, each
diagnosis with 3 medications, this generates **1,000+ queries**.

### Prescription Output

```
 query-doctor  GET /api/patients/ (1,071 queries, 4 prescriptions)

[CRITICAL] N+1 Query — 10 queries fetching primary_doctor for Patient
  Location: patients/views.py:3
  Fix: select_related('primary_doctor')

[CRITICAL] N+1 Query — 50 queries fetching doctor for Visit
  Location: patients/serializers.py:19
  Fix: Use Prefetch with select_related on visit_set

[CRITICAL] N+1 Query — 100 queries fetching medication_set for Diagnosis
  Location: patients/serializers.py:11
  Fix: Use nested Prefetch for diagnosis_set -> medication_set

[CRITICAL] N+1 Query — 300 queries fetching doctor for Medication
  Location: patients/serializers.py:6
  Fix: Use Prefetch with select_related on medication_set
```

### The Fix

```python title="patients/views.py"
from django.db.models import Prefetch
from rest_framework.generics import ListAPIView

from patients.models import Patient, Visit, Diagnosis, Medication
from patients.serializers import PatientDetailSerializer


class PatientListView(ListAPIView):
    serializer_class = PatientDetailSerializer
    queryset = Patient.objects.select_related(
        "primary_doctor",
    ).prefetch_related(
        Prefetch(
            "visit_set",
            queryset=Visit.objects.select_related("doctor").prefetch_related(
                Prefetch(
                    "diagnosis_set",
                    queryset=Diagnosis.objects.prefetch_related(
                        Prefetch(
                            "medication_set",
                            queryset=Medication.objects.select_related("doctor"),
                        ),
                    ),
                ),
            ),
        ),
    )
```

**Result: 1,071 queries reduced to 4 queries.**

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Queries | 1,071 | 4 | 99.6% fewer |
| Response time | 4,800 ms | 120 ms | 97.5% faster |

!!! warning "Deep prefetch chains"
    Deeply nested `Prefetch` objects are powerful but can become hard to
    maintain. Consider splitting very deep hierarchies into separate API
    endpoints (e.g., `/patients/` and `/patients/{id}/visits/`) to keep
    each queryset manageable.

---

## Common Patterns Summary

| Pattern | Symptom | Fix |
|---------|---------|-----|
| FK access in serializer field | N+1 on parent queryset | `select_related('fk_field')` on the view's queryset |
| Reverse FK / M2M in nested serializer | N+1 on child set | `prefetch_related('child_set')` on the view's queryset |
| FK on a prefetched child | N+1 within prefetch | `Prefetch('child_set', queryset=Child.objects.select_related('fk'))` |
| Multi-level nesting | Cascading N+1 | Nested `Prefetch` objects with `select_related` at each level |
| `SerializerMethodField` with query | Hidden N+1 | Prefetch or annotate at the queryset level |

!!! info "Auto-fix mode"
    For straightforward `select_related` and `prefetch_related` fixes,
    django-query-doctor can apply them automatically:
    ```bash
    python manage.py fix_queries --dry-run  # Preview changes
    python manage.py fix_queries            # Apply fixes with .bak backups
    ```
    See the [management commands documentation](../guides/management-commands.md)
    for details.

See also: [DRF ViewSet Examples](drf-viewsets.md) | [Large Codebase Strategies](large-codebases.md)
