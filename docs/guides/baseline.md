# Baseline Regression Detection

A baseline is a snapshot of known query issues saved to a JSON file. On subsequent runs, django-query-doctor compares the current issues against the baseline and reports only **new regressions** — issues that were not present when the baseline was created.

---

## How It Works

The baseline comparison logic is in `query_doctor.baseline.BaselineSnapshot`:

1. **What a baseline contains** — Each issue is stored as a serialized prescription dict with the analyzer type, file path, and description.

2. **Why line numbers are ignored** — The baseline hashes each issue using a SHA-256 digest of `{analyzer}:{file_path}:{description}`. Line numbers are deliberately excluded because refactoring changes line numbers without changing the underlying issue. This prevents false regressions from code reformatting.

3. **What counts as a regression** — Any issue in the current run whose hash is not found in the baseline. These are new issues introduced since the baseline was created.

4. **What counts as resolved** — Any issue in the baseline whose hash is not found in the current run. These are issues that have been fixed since the baseline was created.

---

## Creating a Baseline

```bash
python manage.py check_queries --save-baseline=.query-baseline.json
```

This runs the full analysis and saves all detected issues to the specified JSON file.

### Baseline File Format

```json
{
  "version": "2.0.0",
  "issue_count": 12,
  "issues": [
    {
      "issue_type": "n_plus_one",
      "description": "N+1 detected: 47 queries for table \"myapp_author\"",
      "callsite": {
        "filepath": "myapp/views.py",
        "line_number": 83
      },
      "severity": "CRITICAL",
      "fix_suggestion": "Add .select_related('author') to your queryset"
    }
  ]
}
```

---

## Using in CI

Compare the current run against a previously saved baseline:

```bash
python manage.py check_queries \
    --baseline=.query-baseline.json \
    --fail-on-regression
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | No regressions found. New issues may exist but they were already in the baseline. |
| `1` | One or more new issues not present in the baseline were detected. |

### GitHub Actions Example

```yaml
name: Query Regression Check

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

      - name: Run tests
        run: pytest

      - name: Check for query regressions
        run: |
          python manage.py check_queries \
            --baseline=.query-baseline.json \
            --fail-on-regression \
            --format=json \
            --output=query-report.json

      - name: Upload report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: query-regression-report
          path: query-report.json
```

The `diagnose_project` command also supports baseline flags:

```bash
python manage.py diagnose_project \
    --baseline=.query-baseline.json \
    --fail-on-regression
```

---

## Limitations

- **Per-project, not per-branch** — The baseline file does not track which git branch it was created on. If different branches have different query patterns, you may need separate baseline files.
- **Resolved issues are not automatically removed** — When you fix an issue, it remains in the baseline file until you regenerate it with `--save-baseline`.
- **Baseline file should be committed to version control** — This ensures all CI runs and developers compare against the same known state.
- **URL-dependent** — The baseline captures issues for whatever URLs were analyzed. If you add new endpoints, they won't be covered until you regenerate the baseline.

---

## Further Reading

- [Management Commands](management-commands.md) — Full flag reference for `check_queries` and `diagnose_project`
- [CI/CD Integration](ci-integration.md) — Setting up automated query checks in your pipeline
