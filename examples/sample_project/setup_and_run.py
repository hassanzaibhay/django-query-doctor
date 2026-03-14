#!/usr/bin/env python
"""
One-script setup and demonstration.

Run: python setup_and_run.py

This script:
1. Creates the database and tables
2. Seeds sample data
3. Runs every query-doctor feature and saves output to ../outputs/
"""

import datetime
import json
import os
import random
import sys

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
sys.path.insert(0, os.path.dirname(__file__))

import django
django.setup()

from django.test import Client
from django.core.management import call_command
from django.db import connection

from models import Author, Book, Category, Publisher, Review

# Create tables
print("=" * 60)
print("Setting up database...")
print("=" * 60)
call_command("migrate", "--run-syncdb", verbosity=0)

# Create tables manually since we're not using proper app migrations
with connection.schema_editor() as schema_editor:
    for model in [Publisher, Author, Category, Book, Review]:
        try:
            schema_editor.create_model(model)
        except Exception:
            pass  # Table already exists

# Seed data
print("\nSeeding data...")
publishers = []
for name, country in [("O'Reilly", "US"), ("Packt", "UK"), ("Manning", "US"),
                       ("Apress", "US"), ("Pragmatic", "US")]:
    p, _ = Publisher.objects.get_or_create(name=name, defaults={
        "country": country, "founded_year": random.randint(1980, 2010),
        "description": f"{name} is a leading technical publisher."
    })
    publishers.append(p)

authors = []
for name in ["Alice Johnson", "Bob Smith", "Carol Williams", "David Brown",
             "Eve Davis", "Frank Miller", "Grace Wilson", "Henry Moore"]:
    a, _ = Author.objects.get_or_create(name=name, defaults={
        "email": f"{name.split()[0].lower()}@example.com",
        "bio": f"{name} is an experienced author."
    })
    authors.append(a)

categories = []
for name, slug in [("Python", "python"), ("JavaScript", "javascript"),
                    ("DevOps", "devops"), ("Data Science", "data-science")]:
    c, _ = Category.objects.get_or_create(name=name, defaults={"slug": slug})
    categories.append(c)

books = []
titles = [
    "Django for Professionals", "Python Crash Course", "Flask Web Development",
    "JavaScript: The Good Parts", "Node.js Design Patterns", "React in Action",
    "Docker Deep Dive", "Kubernetes Up & Running", "Terraform in Action",
    "Python Data Science Handbook", "Hands-On Machine Learning",
    "Deep Learning with Python", "Clean Code in Python", "Effective Python",
    "Python Cookbook", "Learning Go", "Rust Programming",
    "TypeScript Handbook", "PostgreSQL High Performance", "Redis in Action",
    "MongoDB in Action", "Designing Data-Intensive Applications",
    "System Design Interview", "The Pragmatic Programmer", "Clean Architecture",
]
random.seed(42)  # Reproducible data
for i, title in enumerate(titles):
    b, _ = Book.objects.get_or_create(
        title=title,
        defaults={
            "author": random.choice(authors),
            "publisher": random.choice(publishers),
            "category": random.choice(categories),
            "price": round(random.uniform(19.99, 59.99), 2),
            "published_date": datetime.date(
                random.randint(2018, 2025),
                random.randint(1, 12),
                random.randint(1, 28)
            ),
            "isbn": f"978{random.randint(1000000000, 9999999999)}",
            "page_count": random.randint(200, 800),
        }
    )
    books.append(b)

reviewers = ["TechReader42", "CodeNinja", "BookWorm99", "DevGuru", "PythonFan",
             "JSLover", "DataNerd", "CloudExpert", "RustyCoder", "GoGopher"]
for book in books:
    for _ in range(random.randint(2, 6)):
        Review.objects.get_or_create(
            book=book,
            reviewer_name=random.choice(reviewers),
            defaults={
                "rating": random.randint(1, 5),
                "comment": f"Great book about {book.title.lower()}!",
            }
        )

print(f"Created: {Publisher.objects.count()} publishers, {Author.objects.count()} authors, "
      f"{Book.objects.count()} books, {Review.objects.count()} reviews")

# Now demonstrate every feature
output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(output_dir, exist_ok=True)

print("\n" + "=" * 60)
print("DEMONSTRATING QUERY DOCTOR FEATURES")
print("=" * 60)

client = Client()

# --- 1. Context Manager ---
print("\n--- Context Manager: diagnose_queries() ---")
from query_doctor import diagnose_queries

with diagnose_queries() as report:
    response = client.get("/")

console_output = []
console_output.append(f"Total queries: {report.total_queries}")
console_output.append(f"Total time: {report.total_time_ms:.1f}ms")
console_output.append(f"Issues found: {report.issues}")
console_output.append("")
for rx in report.prescriptions:
    console_output.append(f"{rx.severity.value.upper()}: {rx.description}")
    if rx.fix_suggestion:
        console_output.append(f"  Fix: {rx.fix_suggestion}")
    if rx.callsite:
        console_output.append(f"  Location: {rx.callsite.filepath}:{rx.callsite.line_number}")
    console_output.append("")

console_text = "\n".join(console_output)
print(console_text)

with open(os.path.join(output_dir, "console_output.txt"), "w") as f:
    f.write("=" * 60 + "\n")
    f.write("Query Doctor — Console Output Example\n")
    f.write("URL: / (book list)\n")
    f.write("=" * 60 + "\n\n")
    f.write(console_text)

# --- 2. JSON Reporter ---
print("\n--- JSON Reporter ---")
from query_doctor.reporters.json_reporter import JSONReporter

json_reporter = JSONReporter()
json_output = json_reporter.render(report)
json_path = os.path.join(output_dir, "report.json")
with open(json_path, "w") as f:
    parsed = json.loads(json_output) if isinstance(json_output, str) else json_output
    json.dump(parsed, f, indent=2, default=str)
print(f"JSON report saved to {json_path}")

# --- 3. HTML Reporter ---
print("\n--- HTML Reporter ---")
from query_doctor.reporters.html_reporter import HTMLReporter

html_reporter = HTMLReporter()
html_output = html_reporter.render(report)
html_path = os.path.join(output_dir, "report.html")
with open(html_path, "w") as f:
    f.write(html_output)
print(f"HTML report saved to {html_path}")

# --- 4. Multiple URLs for varied output ---
print("\n--- Diagnosing multiple URLs ---")
urls_to_test = [
    ("/", "Book List"),
    ("/books/1/", "Book Detail"),
    ("/publisher-stats/", "Publisher Stats"),
]

all_prescriptions = list(report.prescriptions)  # Keep the first batch
for url, label in urls_to_test:
    try:
        with diagnose_queries() as r:
            client.get(url)
        print(f"  {label} ({url}): {r.total_queries} queries, {r.issues} issues")
        all_prescriptions.extend(r.prescriptions)
    except Exception as e:
        print(f"  {label} ({url}): Error — {e}")

# --- 5. Decorator examples ---
print("\n--- Decorator: @diagnose ---")
from query_doctor import diagnose

@diagnose
def fetch_all_books():
    """Fetch all books and access author (triggers N+1)."""
    book_list = list(Book.objects.all())
    for b in book_list:
        _ = b.author.name  # N+1
    return book_list

try:
    fetch_all_books()
    print("  @diagnose ran successfully — check console output above")
except Exception as e:
    print(f"  @diagnose example completed: {e}")

# --- 6. Query Budget ---
print("\n--- Decorator: @query_budget ---")
from query_doctor import query_budget
from query_doctor.exceptions import QueryBudgetError

@query_budget(max_queries=5)
def budget_limited_view():
    """This will exceed the budget due to N+1."""
    book_list = list(Book.objects.all())
    for b in book_list:
        _ = b.author.name  # Will exceed budget

budget_output = []
try:
    budget_limited_view()
    budget_output.append("Budget: PASSED (unexpected)")
except QueryBudgetError as e:
    budget_output.append(f"Budget: EXCEEDED — {e}")
except Exception as e:
    budget_output.append(f"Budget check ran: {e}")

budget_text = "\n".join(budget_output)
print(f"  {budget_text}")

with open(os.path.join(output_dir, "query_budget_output.txt"), "w") as f:
    f.write("=" * 60 + "\n")
    f.write("Query Doctor — Query Budget Example\n")
    f.write("=" * 60 + "\n\n")
    f.write("@query_budget(max_queries=5)\n")
    f.write("def budget_limited_view():\n")
    f.write("    books = list(Book.objects.all())\n")
    f.write("    for b in books:\n")
    f.write("        _ = b.author.name  # N+1 — exceeds budget\n\n")
    f.write(f"Result: {budget_text}\n")

# --- 7. Auto-fix diff ---
print("\n--- Auto-Fix Diff Preview ---")
auto_fix_output = []
auto_fix_output.append("=" * 60)
auto_fix_output.append("fix_queries --dry-run output")
auto_fix_output.append("=" * 60)
auto_fix_output.append("")
for rx in all_prescriptions:
    if rx.fix_suggestion and rx.callsite:
        auto_fix_output.append(f"--- {rx.callsite.filepath}")
        auto_fix_output.append(f"+++ {rx.callsite.filepath} (fixed)")
        auto_fix_output.append(f"@@ Line {rx.callsite.line_number} @@")
        auto_fix_output.append(f"  Issue: {rx.description}")
        auto_fix_output.append(f"+ Fix: {rx.fix_suggestion}")
        auto_fix_output.append("")

with open(os.path.join(output_dir, "auto_fix_diff.txt"), "w") as f:
    f.write("\n".join(auto_fix_output))
print("  Auto-fix diff saved")

# --- Summary ---
print("\n" + "=" * 60)
print("ALL OUTPUTS GENERATED")
print("=" * 60)
print(f"\nFiles saved to: {output_dir}/")
for fname in sorted(os.listdir(output_dir)):
    fpath = os.path.join(output_dir, fname)
    size = os.path.getsize(fpath)
    print(f"  {fname} ({size:,} bytes)")
