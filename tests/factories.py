"""Factory Boy factories for test data generation."""

from __future__ import annotations

import factory

from tests.testapp.models import Author, Book, Category, Publisher, Review


class PublisherFactory(factory.django.DjangoModelFactory):
    """Factory for Publisher model."""

    class Meta:
        model = Publisher

    name = factory.Sequence(lambda n: f"Publisher {n}")
    country = "US"


class AuthorFactory(factory.django.DjangoModelFactory):
    """Factory for Author model."""

    class Meta:
        model = Author

    name = factory.Sequence(lambda n: f"Author {n}")
    email = factory.LazyAttribute(lambda o: f"{o.name.lower().replace(' ', '.')}@example.com")
    bio = "A prolific author."
    publisher = factory.SubFactory(PublisherFactory)


class CategoryFactory(factory.django.DjangoModelFactory):
    """Factory for Category model."""

    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.LazyAttribute(lambda o: o.name.lower().replace(" ", "-"))


class BookFactory(factory.django.DjangoModelFactory):
    """Factory for Book model."""

    class Meta:
        model = Book

    title = factory.Sequence(lambda n: f"Book {n}")
    isbn = factory.Sequence(lambda n: f"{n:013d}")
    author = factory.SubFactory(AuthorFactory)
    publisher = factory.SubFactory(PublisherFactory)
    price = factory.LazyFunction(lambda: 19.99)


class ReviewFactory(factory.django.DjangoModelFactory):
    """Factory for Review model."""

    class Meta:
        model = Review

    book = factory.SubFactory(BookFactory)
    reviewer_name = factory.Sequence(lambda n: f"Reviewer {n}")
    rating = 4
    content = "Great book!"
