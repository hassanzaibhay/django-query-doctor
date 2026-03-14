#!/bin/bash
# Example 13: Diff-Aware CI

echo "============================================================"
echo "Example 13: Diff-Aware CI"
echo "============================================================"

echo ""
echo "# Only check files changed in this PR:"
echo "$ python manage.py check_queries --url /api/books/ --diff=main"
echo ""
echo "# In GitHub Actions:"
cat << 'EOF'
# .github/workflows/query-check.yml
name: Query Check

on:
  pull_request:
    branches: [main]

jobs:
  check-queries:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for diff

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install django-query-doctor

      - name: Check query performance
        run: |
          python manage.py migrate --run-syncdb
          python manage.py check_queries --url /api/books/ --diff=origin/main --fail-on critical
EOF
