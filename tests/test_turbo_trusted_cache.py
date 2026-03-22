"""Tests for QueryTurbo three-phase trust lifecycle (untrusted/trusted/poisoned)."""

from __future__ import annotations

import pytest
from django.db.models import Count, Q

from query_doctor.turbo.context import turbo_disabled, turbo_enabled
from query_doctor.turbo.patch import (
    get_cache,
    install_patch,
    uninstall_patch,
)
from tests.factories import AuthorFactory, BookFactory


@pytest.fixture(autouse=True)
def _turbo_patch(settings):
    """Install and uninstall the turbo patch for each test."""
    settings.QUERY_DOCTOR = {
        "TURBO": {
            "ENABLED": True,
            "VALIDATION_THRESHOLD": 3,
        }
    }
    from query_doctor.conf import get_config

    get_config.cache_clear()

    install_patch()
    yield
    uninstall_patch()
    get_config.cache_clear()


@pytest.fixture()
def sample_data():
    """Create test data."""
    author1 = AuthorFactory(name="Alice")
    author2 = AuthorFactory(name="Bob")
    book1 = BookFactory(title="Book A", price=10, author=author1)
    book2 = BookFactory(title="Book B", price=20, author=author1)
    book3 = BookFactory(title="Book C", price=30, author=author2)
    return {
        "authors": [author1, author2],
        "books": [book1, book2, book3],
    }


@pytest.mark.django_db
class TestTrustLifecycle:
    """Verify the untrusted → trusted promotion."""

    def test_new_entry_starts_untrusted(self, sample_data):
        """First cache miss creates an untrusted entry."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            list(Book.objects.filter(price=10))

        stats = cache.stats()
        assert stats.trusted_entries == 0

    def test_entry_promoted_after_threshold(self, sample_data):
        """After VALIDATION_THRESHOLD hits, entry becomes trusted."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            # 1 miss + 3 validating hits = 4 total
            for price in [10, 20, 30, 40]:
                list(Book.objects.filter(price=price))

        stats = cache.stats()
        assert stats.trusted_entries >= 1

    def test_trusted_hit_counter(self, sample_data):
        """Trusted hits increment the trusted_hits counter."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            # Build trust: 1 miss + 3 validations
            for price in [10, 20, 30, 40]:
                list(Book.objects.filter(price=price))

            trusted_before = cache.stats().trusted_hits

            # This should use the trusted path
            list(Book.objects.filter(price=50))

            trusted_after = cache.stats().trusted_hits

        assert trusted_after > trusted_before


@pytest.mark.django_db
class TestTrustedPathCorrectness:
    """Most important: results must be IDENTICAL on trusted path."""

    def test_simple_filter_correct_on_trusted(self, sample_data):
        """filter(price=X) returns correct results after trust."""
        from tests.testapp.models import Book

        # Get expected results without turbo
        with turbo_disabled():
            expected_10 = sorted([b.pk for b in Book.objects.filter(price=10)])
            expected_20 = sorted([b.pk for b in Book.objects.filter(price=20)])

        cache = get_cache()
        assert cache is not None
        cache.clear()

        # Build trust
        with turbo_enabled():
            for price in [10, 20, 30, 40]:
                list(Book.objects.filter(price=price))

            # Now on TRUSTED path
            result_10 = sorted([b.pk for b in Book.objects.filter(price=10)])
            result_20 = sorted([b.pk for b in Book.objects.filter(price=20)])

        assert result_10 == expected_10
        assert result_20 == expected_20

    def test_values_correct_on_trusted(self, sample_data):
        """values() returns correct results on trusted path."""
        from tests.testapp.models import Book

        with turbo_disabled():
            expected = list(
                Book.objects.filter(price__gte=10).values("title", "price").order_by("price")
            )

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            qs = Book.objects.filter(price__gte=10).values("title", "price").order_by("price")
            for _ in range(4):  # build trust
                list(qs)
            result = list(qs)  # trusted path

        assert result == expected

    def test_annotate_correct_on_trusted(self, sample_data):
        """annotate().filter() returns correct results on trusted path."""
        from tests.testapp.models import Author

        with turbo_disabled():
            expected = list(
                Author.objects.annotate(bc=Count("books")).filter(bc__gt=0).order_by("name")
            )

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            qs = Author.objects.annotate(bc=Count("books")).filter(bc__gt=0).order_by("name")
            for _ in range(4):
                list(qs)
            result = list(qs)

        assert [(a.name, a.bc) for a in result] == [(a.name, a.bc) for a in expected]

    def test_q_objects_correct_on_trusted(self, sample_data):
        """Q(a=1)|Q(b=2) returns correct results on trusted path."""
        from tests.testapp.models import Book

        with turbo_disabled():
            expected = sorted([b.pk for b in Book.objects.filter(Q(price=10) | Q(price=30))])

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            qs = Book.objects.filter(Q(price=10) | Q(price=30))
            for _ in range(4):
                list(qs)
            result = sorted([b.pk for b in qs])

        assert result == expected

    def test_in_lookup_correct_on_trusted(self, sample_data):
        """__in lookup returns correct results on trusted path."""
        from tests.testapp.models import Book

        pks = [b.pk for b in sample_data["books"][:2]]

        with turbo_disabled():
            expected = sorted([b.pk for b in Book.objects.filter(id__in=pks)])

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            for _ in range(4):
                list(Book.objects.filter(id__in=pks))
            result = sorted([b.pk for b in Book.objects.filter(id__in=pks)])

        assert result == expected

    def test_exclude_correct_on_trusted(self, sample_data):
        """exclude() returns correct results on trusted path."""
        from tests.testapp.models import Book

        with turbo_disabled():
            expected = sorted([b.pk for b in Book.objects.exclude(price=10)])

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            for price in [10, 20, 30, 40]:
                list(Book.objects.exclude(price=price))
            result = sorted([b.pk for b in Book.objects.exclude(price=10)])

        assert result == expected

    def test_select_related_correct_on_trusted(self, sample_data):
        """select_related + filter returns correct results on trusted path."""
        from tests.testapp.models import Book

        with turbo_disabled():
            expected = list(Book.objects.select_related("author").filter(price=10))

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            qs = Book.objects.select_related("author").filter(price=10)
            for _ in range(4):
                list(qs)
            result = list(qs)

        assert [b.pk for b in result] == [b.pk for b in expected]
        assert result[0].author.name == expected[0].author.name


@pytest.mark.django_db
class TestPoisonedEntries:
    """Poisoned entries bypass the cache permanently."""

    def test_collision_poisons_entry(self, sample_data):
        """If cached SQL differs from fresh, entry is poisoned."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            list(Book.objects.filter(price=10))

        # Corrupt the cached entry
        with cache._lock:
            for key in list(cache._cache.keys()):
                cache._cache[key].sql = "SELECT CORRUPTED"
                cache._cache[key].validated_count = 0
                cache._cache[key].trusted = False

        # Next query detects collision and poisons
        with turbo_enabled():
            result = list(Book.objects.filter(price=20))

        stats = cache.stats()
        assert stats.poisoned_entries >= 1
        # Should still get correct results
        assert len(result) == 1

    def test_poisoned_entry_always_bypassed(self, sample_data):
        """After poisoning, further hits bypass the cache."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        with turbo_enabled():
            list(Book.objects.filter(price=10))

        # Poison via corruption
        with cache._lock:
            for key in list(cache._cache.keys()):
                cache._cache[key].sql = "SELECT CORRUPTED"

        # Hit 1: detects collision, poisons
        with turbo_enabled():
            list(Book.objects.filter(price=20))

        # Hit 2: should bypass (poisoned) — still works correctly
        with turbo_enabled():
            result = list(Book.objects.filter(price=30))

        assert len(result) == 1


@pytest.mark.django_db
class TestParamCountDemotion:
    """Param count mismatches demote trusted entries."""

    def test_different_in_lengths_are_separate_entries(self, sample_data):
        """__in with different lengths produce different fingerprints."""
        from tests.testapp.models import Book

        cache = get_cache()
        assert cache is not None
        cache.clear()

        # These have different fingerprints due to in_count
        with turbo_enabled():
            list(Book.objects.filter(id__in=[1, 2, 3]))
            list(Book.objects.filter(id__in=[1, 2, 3, 4]))

        # At least 2 entries (different fingerprints)
        assert cache.stats().size >= 2
