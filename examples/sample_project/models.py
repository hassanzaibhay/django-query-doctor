"""
Sample models with deliberate anti-patterns.
Small enough to understand in 2 minutes, big enough to trigger every analyzer.
"""

from django.db import models


class Publisher(models.Model):
    name = models.CharField(max_length=100)
    country = models.CharField(max_length=50)
    founded_year = models.IntegerField(default=2000)
    description = models.TextField(blank=True)  # Large field — fat SELECT target

    class Meta:
        app_label = "sample_project"

    def __str__(self):
        return self.name


class Author(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    bio = models.TextField(blank=True)  # Large field — fat SELECT target

    class Meta:
        app_label = "sample_project"

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)

    class Meta:
        app_label = "sample_project"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Book(models.Model):
    title = models.CharField(max_length=200)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="books")
    publisher = models.ForeignKey(Publisher, on_delete=models.CASCADE, related_name="books")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="books")
    price = models.DecimalField(max_digits=6, decimal_places=2)
    # BUG: No db_index on published_date — used in ORDER BY and WHERE
    published_date = models.DateField()
    isbn = models.CharField(max_length=13, unique=True)
    description = models.TextField(blank=True)
    page_count = models.IntegerField(default=0)

    class Meta:
        app_label = "sample_project"

    def __str__(self):
        return self.title


class Review(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    reviewer_name = models.CharField(max_length=100)
    rating = models.IntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "sample_project"

    def __str__(self):
        return f"{self.rating}* by {self.reviewer_name}"
