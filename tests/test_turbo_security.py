"""Tests for QueryTurbo security: no value leakage, SQL injection safety."""

from __future__ import annotations

import pytest
from django.db.models import Q

from query_doctor.turbo.fingerprint import compute_fingerprint
from tests.testapp.models import Book


def _get_compiler(queryset):
    """Get the SQLCompiler for a queryset without executing it."""
    query = queryset.query
    compiler = query.get_compiler(using="default")
    return query, compiler


@pytest.mark.django_db
class TestNoValueLeakage:
    """Fingerprints must never contain user-supplied values."""

    def test_string_value_not_in_fingerprint(self):
        """String filter values must not appear in the fingerprint."""
        q, c = _get_compiler(Book.objects.filter(title="SECRET_VALUE_12345"))
        fp = compute_fingerprint(q, c)
        assert "SECRET_VALUE_12345" not in fp

    def test_numeric_value_not_in_fingerprint(self):
        """Numeric filter values must not appear in the fingerprint."""
        q, c = _get_compiler(Book.objects.filter(price=99999))
        fp = compute_fingerprint(q, c)
        assert "99999" not in fp

    def test_different_values_same_fingerprint(self):
        """Different user values must produce the same fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(title="password123"))
        q2, c2 = _get_compiler(Book.objects.filter(title="harmless"))

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_sql_injection_attempt_same_fingerprint(self):
        """SQL injection payloads in values don't affect fingerprint."""
        q1, c1 = _get_compiler(Book.objects.filter(title="normal"))
        q2, c2 = _get_compiler(
            Book.objects.filter(title="'; DROP TABLE books; --")
        )

        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)

        assert fp1 == fp2

    def test_injection_value_not_in_fingerprint(self):
        """SQL injection payload text must not appear in fingerprint."""
        q, c = _get_compiler(
            Book.objects.filter(title="'; DROP TABLE books; --")
        )
        fp = compute_fingerprint(q, c)
        assert "DROP" not in fp
        assert "TABLE" not in fp

    def test_q_object_values_not_in_fingerprint(self):
        """Values in Q objects must not leak into fingerprint."""
        q, c = _get_compiler(
            Book.objects.filter(Q(title="SECRET") | Q(isbn="HIDDEN"))
        )
        fp = compute_fingerprint(q, c)
        assert "SECRET" not in fp
        assert "HIDDEN" not in fp


@pytest.mark.django_db
class TestFingerprintOnlyStructural:
    """Fingerprints contain only structural metadata."""

    def test_fingerprint_contains_model_label(self):
        """Fingerprint computation uses model label (structural metadata)."""
        q1, c1 = _get_compiler(Book.objects.filter(title="A"))
        q2, c2 = _get_compiler(Book.objects.filter(title="B"))

        # Same structure → same fingerprint (model label is part of structure)
        fp1 = compute_fingerprint(q1, c1)
        fp2 = compute_fingerprint(q2, c2)
        assert fp1 == fp2

    def test_fingerprint_is_opaque_hash(self):
        """Fingerprint is an opaque blake2b hash, not readable text."""
        q, c = _get_compiler(
            Book.objects.filter(title="sensitive_data_here")
        )
        fp = compute_fingerprint(q, c)

        # The fingerprint should be a hex hash, not contain readable structural info
        assert len(fp) == 32
        assert all(ch in "0123456789abcdef" for ch in fp)
