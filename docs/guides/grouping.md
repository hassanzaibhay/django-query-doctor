# Prescription Grouping

Prescription grouping combines related prescriptions into actionable clusters, reducing noise in large codebases. Instead of seeing 30 individual N+1 warnings, you see "3 groups of related issues" sorted by severity and count.

---

## Grouping Strategies

The `--group` flag accepts an optional strategy name. If no strategy is specified, `file_analyzer` is used.

### `file_analyzer` (default)

Groups prescriptions by `{file_path}:{issue_type}`. All prescriptions from the same file with the same issue type are combined into one group.

**Before grouping:**

```
WARNING  N+1 detected in myapp/views.py:83
WARNING  N+1 detected in myapp/views.py:91
WARNING  N+1 detected in myapp/views.py:105
WARNING  Duplicate query in myapp/views.py:83
INFO     Fat SELECT in otherapp/api.py:42
```

**After grouping (`--group file_analyzer`):**

```
WARNING  3 related issues in myapp/views.py: N+1 detected (and 2 more)
WARNING  1 related issue in myapp/views.py: Duplicate query
INFO     1 related issue in otherapp/api.py: Fat SELECT
```

### `root_cause`

Groups prescriptions by their suggested fix. Prescriptions that share the same `fix_suggestion` are combined, regardless of which file they appear in.

This is useful when the same missing `select_related()` call causes N+1 issues across multiple files.

### `view`

Groups prescriptions by the originating view or endpoint. Uses the `endpoint` field from the prescription's `extra` metadata. Prescriptions from the same endpoint are combined.

This strategy is most useful with the `diagnose_project` command, which scans multiple URLs.

---

## Using the `--group` Flag

```bash
# Group with default strategy (file_analyzer)
python manage.py check_queries --group

# Group by root cause
python manage.py check_queries --group root_cause

# Group by view (best with diagnose_project)
python manage.py diagnose_project --group view
```

Both `check_queries` and `diagnose_project` support the `--group` flag.

---

## Severity of Groups

Each group's severity is the **maximum severity** of its members. A group containing one CRITICAL and five WARNINGs has severity CRITICAL.

Groups are sorted by:

1. Severity (CRITICAL first, then WARNING, then INFO)
2. Count (larger groups first within the same severity)

This ensures the most impactful groups appear at the top of the output.

---

## Further Reading

- [Management Commands](management-commands.md) — Full flag reference for `check_queries` and `diagnose_project`
- [CI/CD Integration](ci-integration.md) — Using grouping in CI pipelines
