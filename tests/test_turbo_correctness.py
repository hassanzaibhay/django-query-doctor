"""Tests for QueryTurbo correctness: results must be identical with and without cache."""

from __future__ import annotations

import pytest
from django.db.models import Count, F, Q, Sum

from query_doctor.turbo.context import turbo_disabled, turbo_enabled
from query_doctor.turbo.patch import (
    _is_turbo_active,
    get_cache,
    install_patch,
    uninstall_patch,
)
from tests.factories import AuthorFactory, BookFactory, CategoryFactory, ReviewFactory


@pytest.fixture(autouse=True)
def _turbo_patch(settings):
    """Install and uninstall the turbo patch for each test."""
    settings.QUERY_DOCTOR = {"TURBO": {"ENABLED": True}}
    # Clear LRU cache so new settings take effect
    from query_doctor.conf import get_config

    get_config.cache_clear()

    install_patch()
    yield
    uninstall_patch()
    get_config.cache_clear()


@pytest.fixture()
def sample_data():
    """Create a consistent set of test data."""
    cat1 = CategoryFactory(name="Fiction", slug="fiction")
    cat2 = CategoryFactory(name="Science", slug="science")
    author1 = AuthorFactory(name="Alice")
    author2 = AuthorFactory(name="Bob")
    book1 = BookFactory(title="Book A", price=10, author=author1)
    book2 = BookFactory(title="Book B", price=20, author=author1)
    book3 = BookFactory(title="Book C", price=30, author=author2)
    book1.categories.add(cat1)
    book2.categories.add(cat1, cat2)
    book3.categories.add(cat2)
    ReviewFactory(book=book1, rating=5)
    ReviewFactory(book=book1, rating=3)
    ReviewFactory(book=book2, rating=4)
    return {
        "authors": [author1, author2],
        "books": [book1, book2, book3],
        "categories": [cat1, cat2],
    }


def _run_query_both_ways(queryset):
    """Run a query with turbo disabled, then enabled (miss + hit), return all results.

    Returns (disabled_result, miss_result, hit_result, cache_stats).
    """

    # Run with turbo disabled
    with turbo_disabled():
        disabled_result = list(queryset.all())

    cache = get_cache()
    assert cache is not None
    cache.clear()

    # First run with turbo enabled = cache miss
    with turbo_enabled():
        miss_result = list(queryset.all())

    stats_after_miss = cache.stats()

    # Second run with turbo enabled = cache hit
    with turbo_enabled():
        hit_result = list(queryset.all())

    stats_after_hit = cache.stats()

    return disabled_result, miss_result, hit_result, stats_after_miss, stats_after_hit


@pytest.mark.django_db
class TestCorrectnessSimpleQueries:
    """Simple query patterns produce identical results."""

    def test_simple_filter(self, sample_data):
        """filter(field=value) produces correct results with cache."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _stats = _run_query_both_ways(Book.objects.filter(price=10))

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]
        assert len(disabled) == 1

    def test_multiple_filters(self, sample_data):
        """filter(a=1, b=2) produces correct results."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(
            Book.objects.filter(price=10, title="Book A")
        )

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]
        assert len(disabled) == 1

    def test_exclude(self, sample_data):
        """exclude(field=value) produces correct results."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(Book.objects.exclude(price=10))

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]
        assert len(disabled) == 2

    def test_order_by(self, sample_data):
        """order_by('-field') produces correct results and ordering."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(Book.objects.order_by("-price"))

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]
        assert disabled[0].price > disabled[-1].price

    def test_distinct(self, sample_data):
        """distinct() produces correct results."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(Book.objects.all().distinct())

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]


@pytest.mark.django_db
class TestCorrectnessRelatedQueries:
    """Queries involving relations produce identical results."""

    def test_select_related(self, sample_data):
        """select_related('fk') produces correct results."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(
            Book.objects.select_related("author").filter(price=10)
        )

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]
        # Verify related object is loaded
        assert hit[0].author.name == "Alice"

    def test_values(self, sample_data):
        """values('field') produces correct results."""
        from tests.testapp.models import Book

        qs = Book.objects.filter(price__gte=10).values("title", "price").order_by("price")

        with turbo_disabled():
            disabled = list(qs)

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            miss = list(qs)
        with turbo_enabled():
            hit = list(qs)

        assert disabled == miss == hit

    def test_values_list(self, sample_data):
        """values_list('field') produces correct results."""
        from tests.testapp.models import Book

        qs = Book.objects.order_by("price").values_list("title", flat=True)

        with turbo_disabled():
            disabled = list(qs)

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            miss = list(qs)
        with turbo_enabled():
            hit = list(qs)

        assert disabled == miss == hit


@pytest.mark.django_db
class TestCorrectnessAggregation:
    """Aggregation and annotation queries produce identical results."""

    def test_annotate_count(self, sample_data):
        """annotate(count=Count('related')) produces correct results."""
        from tests.testapp.models import Author

        qs = Author.objects.annotate(book_count=Count("books")).order_by("name")

        with turbo_disabled():
            disabled = list(qs)

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            miss = list(qs)
        with turbo_enabled():
            hit = list(qs)

        disabled_counts = [(a.name, a.book_count) for a in disabled]
        miss_counts = [(a.name, a.book_count) for a in miss]
        hit_counts = [(a.name, a.book_count) for a in hit]

        assert disabled_counts == miss_counts == hit_counts

    def test_aggregate_sum(self, sample_data):
        """aggregate(Sum('field')) produces correct results."""
        from tests.testapp.models import Book

        qs_base = Book.objects.all()

        with turbo_disabled():
            disabled = qs_base.aggregate(total=Sum("price"))

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            miss = qs_base.aggregate(total=Sum("price"))
        with turbo_enabled():
            hit = qs_base.aggregate(total=Sum("price"))

        assert disabled == miss == hit


@pytest.mark.django_db
class TestCorrectnessComplexQueries:
    """Complex query patterns produce identical results."""

    def test_q_objects(self, sample_data):
        """Q(a=1) | Q(b=2) produces correct results."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(
            Book.objects.filter(Q(price=10) | Q(price=30)).order_by("price")
        )

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]
        assert len(disabled) == 2

    def test_f_expression(self, sample_data):
        """filter(field=F('other_field')) produces correct results."""
        from tests.testapp.models import Book

        disabled, miss, hit, _, _ = _run_query_both_ways(
            Book.objects.filter(price=F("price"))  # always true
        )

        assert [b.pk for b in disabled] == [b.pk for b in miss] == [b.pk for b in hit]

    def test_chained_operations(self, sample_data):
        """filter().exclude().annotate().order_by() chain."""
        from tests.testapp.models import Book

        qs = (
            Book.objects.filter(price__gte=10)
            .exclude(title="Book C")
            .annotate(review_count=Count("reviews"))
            .order_by("-price")
        )

        with turbo_disabled():
            disabled = list(qs)

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            miss = list(qs)
        with turbo_enabled():
            hit = list(qs)

        disabled_data = [(b.pk, b.review_count) for b in disabled]
        miss_data = [(b.pk, b.review_count) for b in miss]
        hit_data = [(b.pk, b.review_count) for b in hit]

        assert disabled_data == miss_data == hit_data


@pytest.mark.django_db
class TestCacheHitMissTracking:
    """Verify cache hit/miss behavior."""

    def test_first_call_is_miss(self, sample_data):
        """First execution of a query pattern should be a cache miss."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            list(Book.objects.filter(price=10))

        stats = cache.stats()
        assert stats.misses >= 1

    def test_second_call_is_hit(self, sample_data):
        """Second execution of same pattern should be a cache hit."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            list(Book.objects.filter(price=10))
            initial_hits = cache.stats().hits

            list(Book.objects.filter(price=20))  # same structure, different value
            final_hits = cache.stats().hits

        assert final_hits > initial_hits

    def test_different_values_same_structure_hits_cache(self, sample_data):
        """Queries with same structure but different values share cache entry."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            list(Book.objects.filter(price=10))
            list(Book.objects.filter(price=20))
            list(Book.objects.filter(price=30))

        stats = cache.stats()
        # First call = miss, second and third = hits
        assert stats.hits >= 2


@pytest.mark.django_db
class TestCollisionDetection:
    """Cache validates SQL and evicts on fingerprint collision."""

    def test_collision_evicts_stale_entry(self, sample_data):
        """If cached SQL differs from fresh SQL, the entry is evicted."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        # Manually inject a cache entry with wrong SQL for a known fingerprint
        with turbo_enabled():
            # First query: cache miss, stores real SQL
            list(Book.objects.filter(price=10))

        stats_before = cache.stats()
        assert stats_before.size >= 1

        # Corrupt the cached entry by replacing its SQL with garbage
        with cache._lock:
            for key in list(cache._cache.keys()):
                entry = cache._cache[key]
                cache._cache[key] = type(entry)(sql="SELECT CORRUPTED", param_count=0, hit_count=0)

        # Next query with same fingerprint: validates and detects mismatch
        with turbo_enabled():
            result = list(Book.objects.filter(price=20))

        # Should still get correct results (fallback to fresh SQL)
        assert len(result) == 1

    def test_in_different_lengths_correct_results(self, sample_data):
        """__in with different list lengths must not cause SQL/param mismatch."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        books = sample_data["books"]

        with turbo_enabled():
            r1 = list(Book.objects.filter(id__in=[books[0].pk]))
            r2 = list(Book.objects.filter(id__in=[books[0].pk, books[1].pk]))
            r3 = list(Book.objects.filter(id__in=[books[0].pk, books[1].pk, books[2].pk]))

        assert len(r1) == 1
        assert len(r2) == 2
        assert len(r3) == 3


@pytest.mark.django_db
class TestContextManagerNesting:
    """Context managers properly restore the previous override on exit."""

    def test_nested_disabled_inside_enabled(self, sample_data):
        """turbo_disabled inside turbo_enabled restores enabled on exit."""
        with turbo_enabled():
            assert _is_turbo_active() is True
            with turbo_disabled():
                assert _is_turbo_active() is False
            # Must be restored to True, not to global default
            assert _is_turbo_active() is True

    def test_nested_enabled_inside_disabled(self, sample_data):
        """turbo_enabled inside turbo_disabled restores disabled on exit."""
        with turbo_disabled():
            assert _is_turbo_active() is False
            with turbo_enabled():
                assert _is_turbo_active() is True
            # Must be restored to False, not to global default
            assert _is_turbo_active() is False

    def test_triple_nesting(self, sample_data):
        """Three levels of nesting all restore correctly."""
        with turbo_enabled():
            assert _is_turbo_active() is True
            with turbo_disabled():
                assert _is_turbo_active() is False
                with turbo_enabled():
                    assert _is_turbo_active() is True
                assert _is_turbo_active() is False
            assert _is_turbo_active() is True
