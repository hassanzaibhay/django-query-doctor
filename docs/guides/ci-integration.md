# CI Integration

django-query-doctor is designed to catch query regressions before they reach production. This page covers GitHub Actions setup, diff-aware mode, query budgets in CI, and integration with pytest.

---

## GitHub Actions Workflow

A complete workflow that checks for query issues on every pull request:

```yaml title=".github/workflows/query-doctor.yml"
name: Query Doctor

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  query-check:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for diff-aware mode

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run migrations
        run: python manage.py migrate
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/testdb

      - name: Check queries
        run: |
          python manage.py check_queries \
            --severity WARNING \
            --fail \
            --format json \
            --output query-report.json
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/testdb

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: query-doctor-report
          path: query-report.json
```

The key line is the `check_queries` step with `--severity WARNING --fail`. This causes the workflow to fail if any WARNING or CRITICAL issues are found.

---

## Diff-Aware Mode

In large projects, running a full scan on every PR is slow and noisy. **Diff-aware mode** analyzes only the endpoints affected by files changed in the current PR:

```bash
python manage.py check_queries \
    --diff-aware \
    --base-branch main \
    --severity WARNING \
    --fail
```

How it works:

1. Computes the file diff between the current branch and `--base-branch`.
2. Identifies which Django views and URL patterns are affected by the changed files.
3. Only analyzes those endpoints.

This dramatically reduces scan time and focuses feedback on the code being changed.

### GitHub Actions with Diff-Aware Mode

```yaml
      - name: Check queries (diff-aware)
        run: |
          python manage.py check_queries \
            --diff-aware \
            --base-branch origin/main \
            --severity WARNING \
            --fail \
            --format json \
            --output query-report.json
```

> **Note:** The `fetch-depth: 0` option in the checkout step is required for diff-aware mode. Without it, Git does not have the history needed to compute the diff.

---

## Query Budgets in CI

Use the `query_budget` command to enforce hard limits on query counts per endpoint:

```yaml
      - name: Enforce query budgets
        run: |
          python manage.py query_budget \
            --budget-file query_budgets.yml \
            --fail
```

With a budget file:

```yaml title="query_budgets.yml"
/api/books/: 10
/api/books/{id}/: 8
/api/authors/: 5
/api/authors/{id}/: 6
/dashboard/: 25
```

When an endpoint exceeds its budget, the command prints the offending queries and exits with code 1.

### Generating an Initial Budget File

If you do not have a budget file yet, use `diagnose_project` to generate one based on current behavior:

```bash
python manage.py diagnose_project --generate-budget > query_budgets.yml
```

This sets each endpoint's budget to its current query count plus a small margin. You can then tighten the budgets over time.

---

## Using with Pytest

The pytest plugin integrates naturally with CI. Add the `--query-doctor` flag to your pytest command:

```yaml
      - name: Run tests with query analysis
        run: |
          pytest \
            --query-doctor \
            -v \
            --junitxml=test-results.xml
```

Tests decorated with `@pytest.mark.query_budget` or `@pytest.mark.no_nplusone` will fail if their constraints are violated, causing the CI job to fail.

### Combined Workflow

For maximum coverage, run both pytest and management commands:

```yaml title=".github/workflows/query-doctor.yml"
name: Query Doctor

on:
  pull_request:
    branches: [main]

jobs:
  query-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install
        run: pip install -e ".[dev]"

      - name: Migrate
        run: python manage.py migrate

      - name: Pytest with query checks
        run: pytest --query-doctor -v

      - name: Management command checks (diff-aware)
        run: |
          python manage.py check_queries \
            --diff-aware \
            --base-branch origin/main \
            --severity WARNING \
            --fail

      - name: Enforce query budgets
        run: |
          python manage.py query_budget \
            --budget-file query_budgets.yml \
            --fail
```

---

## PR Comments

For visibility, you can post query doctor results as PR comments using the GitHub CLI:

```yaml
      - name: Post results as PR comment
        if: failure() && github.event_name == 'pull_request'
        run: |
          echo "## Query Doctor Report" > comment.md
          echo "" >> comment.md
          echo "Query issues were found in this PR. See the full report in the job artifacts." >> comment.md
          echo "" >> comment.md
          python manage.py check_queries \
            --diff-aware \
            --base-branch origin/main \
            --severity WARNING \
            --format markdown >> comment.md 2>/dev/null || true
          gh pr comment ${{ github.event.pull_request.number }} --body-file comment.md
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Tips

- **Start with `--severity CRITICAL`** on existing projects to catch only the worst issues. Lower the threshold to `WARNING` as you fix existing problems.
- **Use diff-aware mode** on PRs to keep CI fast. Run full scans on a nightly schedule for comprehensive coverage.
- **Commit your `query_budgets.yml`** to the repository so the entire team shares the same constraints.
- **Use `.queryignore`** to suppress known issues that you plan to fix later. See [Query Ignore](query-ignore.md).

---

## Further Reading

- [Management Commands](management-commands.md) -- Detailed command reference.
- [Pytest Plugin](pytest-plugin.md) -- Markers, fixtures, and configuration.
- [Query Ignore](query-ignore.md) -- Suppressing known issues.
