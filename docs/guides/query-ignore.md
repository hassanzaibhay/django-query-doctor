# Query Ignore

The `.queryignore` file lets you suppress specific django-query-doctor findings. This is useful for known issues that you plan to fix later, third-party code you cannot modify, or intentional patterns that are not actually problems.

---

## Setup

Create a `.queryignore` file in your project root (the same directory as `manage.py`):

```bash
touch .queryignore
```

django-query-doctor checks for this file automatically. No settings changes are needed.

---

## Syntax

Each line in `.queryignore` specifies a **file pattern** and an **analyzer name**, separated by whitespace:

```text title=".queryignore"
# Syntax: file_pattern  analyzer_name

myapp/views.py  nplusone
myapp/serializers.py  duplicate
```

This suppresses:

- All N+1 prescriptions originating from `myapp/views.py`.
- All duplicate query prescriptions originating from `myapp/serializers.py`.

### Wildcards

Standard glob wildcards are supported in file patterns:

```text title=".queryignore"
# All files in the legacy app
legacy_app/*  nplusone
legacy_app/*  duplicate

# All serializers in any app
*/serializers.py  drf_serializer

# All Python files in a specific directory
reports/**/*.py  fat_select

# A specific file, all analyzers
myapp/views.py  *
```

| Pattern | Matches |
|---|---|
| `myapp/views.py` | Exactly `myapp/views.py` |
| `myapp/*.py` | All `.py` files directly in `myapp/` |
| `myapp/**/*.py` | All `.py` files in `myapp/` and subdirectories |
| `*/views.py` | `views.py` in any top-level app directory |
| `*` (as analyzer) | All analyzers |

### Comments

Lines starting with `#` are comments. Blank lines are ignored:

```text title=".queryignore"
# Known N+1 in the legacy dashboard — will fix in Q3
dashboard/views.py  nplusone

# Third-party integration we cannot modify
vendor/api_client.py  *

# Intentional: we want SELECT * here for caching
cache/warmers.py  fat_select
```

---

## Analyzer Names

Use the analyzer's `name` attribute as the second field:

| Analyzer Name | What It Detects |
|---|---|
| `nplusone` | N+1 query patterns |
| `duplicate` | Duplicate queries |
| `missing_index` | Missing database indexes |
| `fat_select` | Unnecessary `SELECT *` |
| `queryset_eval` | Redundant queryset evaluations |
| `drf_serializer` | N+1 in DRF serializers |
| `query_complexity` | Overly complex queries |
| `*` | All analyzers |

For custom analyzers, use the name specified in the analyzer's `name` class attribute.

---

## Examples

### Suppress a Known N+1 in a Legacy View

```text title=".queryignore"
# Legacy view has N+1 on author — tracked in JIRA-1234
blog/views.py  nplusone
```

### Suppress All Issues in Generated Code

```text title=".queryignore"
# Auto-generated admin views
*/admin.py  *
```

### Suppress Duplicate Queries in Tests

```text title=".queryignore"
# Test fixtures create duplicate queries intentionally
tests/**/*.py  duplicate
```

### Suppress Missing Index Warnings for Small Tables

```text title=".queryignore"
# settings table has <100 rows, index would add overhead
config/models.py  missing_index
```

---

## How Matching Works

When django-query-doctor generates a prescription, it checks the prescription's `location` (file path) against each line in `.queryignore`:

1. The file path from the prescription is made relative to the project root.
2. Each `.queryignore` entry's file pattern is matched against this relative path using glob matching.
3. If the file pattern matches **and** the analyzer name matches (or is `*`), the prescription is suppressed.

Suppressed prescriptions are not shown in console output, not included in JSON reports, and do not cause `--fail` to trigger.

---

## Viewing Suppressed Issues

To see what is being suppressed, use the `--show-ignored` flag with any management command:

```bash
python manage.py check_queries --url /api/books/ --show-ignored
```

This prints suppressed prescriptions separately, so you can review whether your ignore rules are still appropriate.

---

## Use Sparingly

> **Warning:** The `.queryignore` file should be a temporary measure, not a permanent fix. Every entry represents a known performance issue in your codebase. Review it regularly and remove entries as issues are resolved.

Best practices:

- **Add a comment** explaining why each entry exists and link to a tracking issue.
- **Review periodically** -- include `.queryignore` review in your sprint/quarterly planning.
- **Prefer fixing** over ignoring. Use the [Auto-Fix](auto-fix.md) system to resolve common issues quickly.
- **Do not ignore entire directories** unless they truly contain only code you cannot modify (third-party, generated).

---

## Further Reading

- [CI Integration](ci-integration.md) -- How `.queryignore` interacts with CI pipelines.
- [Auto-Fix](auto-fix.md) -- Fix issues instead of ignoring them.
- [Custom Plugins](custom-plugins.md) -- Custom analyzers respect `.queryignore` automatically.
