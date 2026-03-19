"""Test models for the benchmark suite.

Simple schema covering common Django ORM patterns:
FK relations, M2M, aggregations, and multi-table JOINs.
"""

from __future__ import annotations

from django.db import models


class Author(models.Model):
    """A book author."""

    name = models.CharField(max_length=100)
    email = models.EmailField()

    class Meta:
        app_label = "benchmarks"


class Publisher(models.Model):
    """A book publisher."""

    name = models.CharField(max_length=100)

    class Meta:
        app_label = "benchmarks"


class Book(models.Model):
    """A book with FK to Author and Publisher."""

    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="books")
    published_date = models.DateField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "benchmarks"


class Review(models.Model):
    """A book review with FK to Book."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    rating = models.IntegerField()
    text = models.TextField()

    class Meta:
        app_label = "benchmarks"
