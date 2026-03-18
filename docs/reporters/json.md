# JSON Reporter

The JSON reporter writes structured output files suitable for CI/CD pipelines,
automated tooling, and programmatic analysis. Each request produces a JSON file
containing all prescriptions along with metadata about the request.

## Configuration

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.JSONReporter",
    ],

    # JSON-specific settings
    "JSON_OUTPUT_DIR": "reports/query-doctor/",
    "JSON_FILENAME_PATTERN": "{timestamp}_{method}_{path}.json",
    "JSON_INDENT": 2,
    "JSON_INCLUDE_SQL": True,
    "JSON_INCLUDE_TRACEBACK": False,
}
```

### Setting Details

| Setting | Default | Description |
|---------|---------|-------------|
| `JSON_OUTPUT_DIR` | `"reports/query-doctor/"` | Directory where JSON files are written. Created automatically if it does not exist. |
| `JSON_FILENAME_PATTERN` | `"{timestamp}_{method}_{path}.json"` | File naming pattern. Available variables: `{timestamp}`, `{method}`, `{path}`, `{status_code}`. |
| `JSON_INDENT` | `2` | JSON indentation level. Set to `None` for compact single-line output. |
| `JSON_INCLUDE_SQL` | `True` | Include the raw SQL statement in each prescription entry. |
| `JSON_INCLUDE_TRACEBACK` | `False` | Include the Python stack trace for each query. |

## Example JSON Output

```json
{
  "version": "1.0.0",
  "timestamp": "2026-03-18T14:32:01.123456Z",
  "request": {
    "method": "GET",
    "path": "/api/books/",
    "status_code": 200,
    "total_queries": 127,
    "total_time_ms": 342.5
  },
  "summary": {
    "total_prescriptions": 4,
    "by_severity": {
      "critical": 1,
      "warning": 2,
      "info": 1
    }
  },
  "prescriptions": [
    {
      "severity": "critical",
      "analyzer": "NPlusOneAnalyzer",
      "issue": "50 queries fetching Author for each Book",
      "location": {
        "file": "myapp/views.py",
        "line": 42,
        "function": "BookListView.get_queryset"
      },
      "suggestion": "Add select_related('author') to queryset",
      "sql_fingerprint": "SELECT \"myapp_author\".\"id\", ... FROM \"myapp_author\" WHERE \"myapp_author\".\"id\" = ?",
      "query_count": 50
    },
    {
      "severity": "warning",
      "analyzer": "DuplicateQueryAnalyzer",
      "issue": "Query executed 12 times",
      "location": {
        "file": "myapp/serializers.py",
        "line": 18,
        "function": "BookSerializer.get_categories"
      },
      "suggestion": "Hoist query above the loop or use prefetch_related('categories')",
      "sql_fingerprint": "SELECT \"myapp_category\".\"id\", ... FROM \"myapp_category\" INNER JOIN ...",
      "query_count": 12
    }
  ]
}
```

## Filtering with jq

The JSON output works well with [jq](https://jqlang.github.io/jq/) for
filtering and transforming results on the command line.

### Show Only Critical Issues

```bash
cat reports/query-doctor/*.json | jq '.prescriptions[] | select(.severity == "critical")'
```

### Count Prescriptions by Analyzer

```bash
cat reports/query-doctor/*.json | jq '[.prescriptions[].analyzer] | group_by(.) | map({(.[0]): length}) | add'
```

### Extract Locations Needing Fixes

```bash
cat reports/query-doctor/*.json | jq -r '.prescriptions[] | "\(.location.file):\(.location.line) [\(.severity)] \(.issue)"'
```

### Find Endpoints with Most Issues

```bash
cat reports/query-doctor/*.json | jq '{path: .request.path, count: .summary.total_prescriptions}' | jq -s 'sort_by(.count) | reverse | .[:10]'
```

## CI/CD Integration

### GitHub Actions

```yaml title=".github/workflows/query-check.yml"
name: Query Doctor Check

on: [pull_request]

jobs:
  query-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e ".[dev]"

      - name: Run query analysis
        run: python manage.py check_queries --reporter json --output reports/
        env:
          DJANGO_SETTINGS_MODULE: myproject.settings.ci

      - name: Check for critical issues
        run: |
          CRITICAL=$(cat reports/query-doctor/*.json | jq '[.prescriptions[] | select(.severity == "critical")] | length')
          if [ "$CRITICAL" -gt 0 ]; then
            echo "::error::Found $CRITICAL critical query issues"
            cat reports/query-doctor/*.json | jq '.prescriptions[] | select(.severity == "critical")'
            exit 1
          fi

      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: query-doctor-reports
          path: reports/query-doctor/
```

### GitLab CI

```yaml title=".gitlab-ci.yml"
query-doctor:
  stage: test
  script:
    - pip install -e ".[dev]"
    - python manage.py check_queries --reporter json --output reports/
    - |
      CRITICAL=$(cat reports/query-doctor/*.json | jq '[.prescriptions[] | select(.severity == "critical")] | length')
      if [ "$CRITICAL" -gt 0 ]; then
        echo "Found $CRITICAL critical query issues"
        exit 1
      fi
  artifacts:
    when: always
    paths:
      - reports/query-doctor/
    expire_in: 30 days
```

!!! warning "Output directory in .gitignore"
    Add your JSON output directory to `.gitignore` to avoid committing
    generated reports:
    ```
    reports/query-doctor/
    ```

## Combining with Other Reporters

JSON output pairs well with the Console reporter for local development and the
HTML reporter for human-readable summaries:

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
        "query_doctor.reporters.JSONReporter",
    ],
}
```

See also: [Reporters Overview](overview.md) | [Console Reporter](console.md) | [HTML Reporter](html.md)
