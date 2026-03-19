"""Tests for QueryTurbo fingerprint correctness and stability."""

from __future__ import annotations

import pytest
from django.db.models import Count, F, Q, Sum

from query_doctor.turbo.fingerprint import compute_fingerprint
from tests.testapp.models import Author, Book


def _get_compiler(queryset):
    """Get the SQLCompiler for a queryset without executing it."""
    query = queryset.query

    compiler = query.get_compiler(using="default")
    return query, compiler


@pytest.mark.django_db
class TestFingerprintStability:
    """Fingerprints must be stable: same structure → same hash."""

    def test_simple_filter_same_fingerprint(self):
        """Same filter structure with different values → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10))
        q2, c2 = _get_compiler(Book.objects.filter(price=20))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_multiple_filters_same_fingerprint(self):
        """Same multi-field filter structure → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10, title="A"))
        q2, c2 = _get_compiler(Book.objects.filter(price=20, title="B"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_q_objects_same_fingerprint(self):
        """Same Q object structure with different values → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(Q(price=10) | Q(title="A")))
        q2, c2 = _get_compiler(Book.objects.filter(Q(price=20) | Q(title="B")))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_select_related_same_fingerprint(self):
        """Same select_related structure → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.select_related("author").filter(price=10))
        q2, c2 = _get_compiler(Book.objects.select_related("author").filter(price=20))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_annotate_same_fingerprint(self):
        """Same annotation structure → same fingerprint."""
        q1, c1 = _get_compiler(
            Author.objects.annotate(book_count=Count("books")).filter(book_count__gt=1)
        )
        q2, c2 = _get_compiler(
            Author.objects.annotate(book_count=Count("books")).filter(book_count__gt=5)
        )

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_order_by_same_fingerprint(self):
        """Same order_by structure → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10).order_by("-title"))
        q2, c2 = _get_compiler(Book.objects.filter(price=20).order_by("-title"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_values_same_fingerprint(self):
        """Same values() structure → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10).values("title", "price"))
        q2, c2 = _get_compiler(Book.objects.filter(price=20).values("title", "price"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_exclude_same_fingerprint(self):
        """Same exclude structure with different values → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.exclude(price=10))
        q2, c2 = _get_compiler(Book.objects.exclude(price=20))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_f_expression_same_fingerprint(self):
        """Same F expression structure → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=F("id")))
        q2, c2 = _get_compiler(Book.objects.filter(price=F("id")))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_chained_operations_same_fingerprint(self):
        """Same chained operations → same fingerprint."""
        q1, c1 = _get_compiler(
            Book.objects.filter(price__gt=5).exclude(title="X").order_by("-price")
        )
        q2, c2 = _get_compiler(
            Book.objects.filter(price__gt=10).exclude(title="Y").order_by("-price")
        )

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_distinct_same_fingerprint(self):
        """Same distinct query → same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10).distinct())
        q2, c2 = _get_compiler(Book.objects.filter(price=20).distinct())

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2


@pytest.mark.django_db
class TestFingerprintUniqueness:
    """Different structures must produce different fingerprints."""

    def test_different_filter_fields(self):
        """Filtering on different fields → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10))
        q2, c2 = _get_compiler(Book.objects.filter(title="A"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_different_models(self):
        """Different models → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.all())
        q2, c2 = _get_compiler(Author.objects.all())

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_different_order_by(self):
        """Different order_by → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.order_by("title"))
        q2, c2 = _get_compiler(Book.objects.order_by("-price"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_with_vs_without_distinct(self):
        """With distinct vs without → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.all())
        q2, c2 = _get_compiler(Book.objects.all().distinct())

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_different_select_related(self):
        """Different select_related → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.select_related("author"))
        q2, c2 = _get_compiler(Book.objects.select_related("publisher"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_filter_vs_exclude(self):
        """filter vs exclude on same field → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10))
        q2, c2 = _get_compiler(Book.objects.exclude(price=10))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_different_lookup_types(self):
        """Different lookup types on same field → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10))
        q2, c2 = _get_compiler(Book.objects.filter(price__gt=10))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_different_annotations(self):
        """Different annotation names → different fingerprint."""
        q1, c1 = _get_compiler(Author.objects.annotate(cnt=Count("books")))
        q2, c2 = _get_compiler(Author.objects.annotate(total=Sum("books__price")))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_different_values_fields(self):
        """Different values() fields → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.values("title"))
        q2, c2 = _get_compiler(Book.objects.values("price"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2

    def test_q_or_vs_q_and(self):
        """Q with OR vs AND → different fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(Q(price=10) | Q(title="A")))
        q2, c2 = _get_compiler(Book.objects.filter(Q(price=10) & Q(title="A")))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 != fp2


@pytest.mark.django_db
class TestFingerprintFormat:
    """Fingerprint format and properties."""

    def test_fingerprint_is_hex_string(self):
        """Fingerprint should be a 32-char hex string (blake2b 16 bytes)."""
        q, c = _get_compiler(Book.objects.all())
        fp = compute_fingerprint(q, c)

        assert isinstance(fp, str)
        assert len(fp) == 32
        assert all(ch in "0123456789abcdef" for ch in fp)

    def test_fingerprint_is_deterministic(self):
        """Same query computed twice → identical fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(price=10))
        q2, c2 = _get_compiler(Book.objects.filter(price=10))

        assert compute_fingerprint(q1, c1) == compute_fingerprint(q2, c2)
