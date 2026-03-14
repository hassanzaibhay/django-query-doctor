"""Test application models for django-query-doctor test suite."""

from __future__ import annotations

from django.db import models


class Publisher(models.Model):
    """A book publisher."""

    name = models.CharField(max_length=200)
    country = models.CharField(max_length=100, db_index=True)

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return self.name


class Author(models.Model):
    """A book author."""

    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)  # Large field, good for .defer() testing
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="authors")

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    """A book category."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    """A book with FK to Author and Publisher, M2M to Category."""

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

    def __str__(self) -> str:
        return self.title


class Review(models.Model):
    """A book review."""

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    reviewer_name = models.CharField(max_length=200)
    rating = models.IntegerField()
    content = models.TextField()

    class Meta:
        app_label = "testapp"

    def __str__(self) -> str:
        return f"Review of {self.book_id} by {self.reviewer_name}"
