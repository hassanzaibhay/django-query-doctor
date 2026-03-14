"""
DRF serializers — triggering DRF N+1 analyzer.
"""

from rest_framework import serializers

from models import Author, Book, Publisher, Review


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = ["id", "name", "email"]


class PublisherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publisher
        fields = ["id", "name", "country"]


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["id", "reviewer_name", "rating", "comment"]


class BookSerializer(serializers.ModelSerializer):
    # BUG: DRF N+1 — nested serializers without prefetch on viewset
    author = AuthorSerializer(read_only=True)
    publisher = PublisherSerializer(read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True, source="reviews.all")

    class Meta:
        model = Book
        fields = ["id", "title", "author", "publisher", "price",
                  "published_date", "reviews"]
