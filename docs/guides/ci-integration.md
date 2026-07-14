# CI Integration

django-query-doctor is designed to catch query regressions before they reach production. This page covers GitHub Actions setup, diff-scoped reporting, baselines, query budgets in CI, and integration with pytest.

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
          fetch-depth: 0  # Required for --diff mode

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
            --url /api/books/ \
            --fail-on warning \
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

The key line is the `check_queries` step with `--fail-on warning`. This causes the workflow to fail if any issue at WARNING severity or higher is found. Valid values are `critical`, `warning`, and `info`.

`check_queries` analyzes one URL per invocation (`--url`, default `/`). To check several endpoints, run it once per URL, or use `diagnose_project` to sweep every discovered URL in one run.

---

## Diff-Scoped Reporting

In large projects, reporting every pre-existing issue on every PR is noisy. The `--diff` flag limits the report to issues whose callsite is in a file changed relative to a git ref:

```bash
python manage.py check_queries \
    --url /api/books/ \
    --diff origin/main \
    --fail-on warning
```

How it works:

1. Computes the file diff between the working tree and the given git ref (e.g. `main`, `origin/develop`, a commit SHA).
2. Filters the report to prescriptions whose file:line callsite falls inside a changed file.

The analysis itself still runs against the URL you specify; `--diff` filters which findings are reported.

### GitHub Actions with `--diff`

```yaml
      - name: Check queries (changed files only)
        run: |
          python manage.py check_queries \
            --url /api/books/ \
            --diff origin/main \
            --fail-on warning \
            --format json \
            --output query-report.json
```

> **Note:** The `fetch-depth: 0` option in the checkout step is required for `--diff`. Without it, Git does not have the history needed to compute the diff.

You can also scope the report to specific files or modules (substring match, repeatable):

```bash
python manage.py check_queries --url /api/books/ --file myapp/views.py
python manage.py check_queries --url /api/books/ --module myapp.api
```

---

## Baselines

To adopt django-query-doctor on an existing project without failing CI on every pre-existing issue, snapshot the current state and fail only on regressions:

```bash
# Once, on main: record the current issues
python manage.py check_queries --url /api/books/ --save-baseline .query-baseline.json

# On every PR: report and fail only on NEW issues vs the baseline
python manage.py check_queries \
    --url /api/books/ \
    --baseline .query-baseline.json \
    --fail-on-regression
```

Commit `.query-baseline.json` to the repository so the whole team shares the same baseline. Regenerate it after upgrading django-query-doctor (analyzer coverage can widen between versions) and after fixing a batch of issues.

---

## Query Budgets in CI

Use the `query_budget` command to enforce a hard limit on query count (and optionally total query time) for a block of code:

```yaml
      - name: Enforce query budget
        run: |
          python manage.py query_budget \
            --max-queries 10 \
            --max-time-ms 500 \
            --execute "from myapp.services import build_dashboard; build_dashboard()"
```

`--max-queries` is required. When the executed code exceeds the budget, the command prints the measured counts and exits with code 1.

> **Warning:** `--execute` runs the given string with `exec()`. Only run trusted code.

There is no per-endpoint budget file; to budget several code paths, run the command once per path, or assert budgets inside your test suite with the [pytest fixture](pytest-plugin.md).

---

## Using with Pytest

The pytest plugin provides a `query_doctor` fixture. Any test that requests the fixture gets query capture and analysis for that test, and can assert on the result:

```python
def test_book_list_has_no_issues(client, query_doctor):
    client.get("/api/books/")
    assert query_doctor.issues == 0
    assert query_doctor.total_queries <= 10
```

Failing assertions fail the test, which fails the CI job — no extra flags needed:

```yaml
      - name: Run tests with query analysis
        run: |
          pytest -v --junitxml=test-results.xml
```

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

      - name: Pytest with query assertions
        run: pytest -v

      - name: Management command checks (changed files only)
        run: |
          python manage.py check_queries \
            --url /api/books/ \
            --diff origin/main \
            --fail-on warning
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
          gh pr comment ${{ github.event.pull_request.number }} --body-file comment.md
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

The JSON report written with `--format json --output query-report.json` is machine-readable if you want to render a richer comment body yourself.

---

## Tips

- **Start with `--fail-on critical`** on existing projects to catch only the worst issues. Lower the threshold to `warning` as you fix existing problems.
- **Use `--diff origin/main`** on PRs to keep feedback focused on the code being changed. Run full scans (`diagnose_project`) on a nightly schedule for comprehensive coverage.
- **Commit your `.query-baseline.json`** to the repository so the entire team shares the same baseline.
- **Use `.queryignore`** to suppress known issues that you plan to fix later. See [Query Ignore](query-ignore.md).

---

## Further Reading

- [Management Commands](management-commands.md) -- Detailed command reference.
- [Pytest Plugin](pytest-plugin.md) -- Fixture usage and assertion patterns.
- [Query Ignore](query-ignore.md) -- Suppressing known issues.
- [Baseline](baseline.md) -- Baseline workflow in depth.
