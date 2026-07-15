# Query Ignore

The `.queryignore` file lets you suppress specific django-query-doctor findings. This is useful for known issues that you plan to fix later, third-party code you cannot modify, or intentional patterns that are not actually problems.

---

## Setup

Create a `.queryignore` file in your project root (the directory containing `manage.py`; if none is found, the current working directory is used):

```bash
touch .queryignore
```

django-query-doctor checks for this file automatically. No settings changes are needed.

---

## Where It Applies

`.queryignore` rules are applied by:

- the **middleware** (per-request reports), and
- the **`fix_queries`** management command.

They are **not** applied by `check_queries`, `diagnose_project`, the pytest fixture, or the `diagnose_queries()` context manager. Suppressed prescriptions are removed before reporting, so they do not appear in middleware console/JSON output and do not produce fixes.

---

## Syntax

Each rule is one line in the form `type: pattern`. Four rule types exist: `file`, `callsite`, `ignore`, and `sql`. Lines starting with `#` and blank lines are skipped. Any line that does not contain a `:` is silently ignored — there is no error for a malformed rule, so double-check your spelling.

```text title=".queryignore"
# Suppress every finding whose callsite is in this file (glob, full path)
file: *myapp/views.py

# Suppress findings at one exact file:line
callsite: /app/myapp/views.py:42

# Suppress one issue type in files whose path contains a substring
ignore: n_plus_one:legacy_app

# Suppress findings whose description contains a SQL fragment
sql: %myapp_author%
```

### `file:` rules

The pattern is matched against the prescription's callsite file path with [`fnmatch`](https://docs.python.org/3/library/fnmatch.html) glob matching. The path recorded at capture time is the **full path** from the Python stack frame, so patterns usually need a leading `*`:

```text title=".queryignore"
# All findings from views.py in myapp
file: *myapp/views.py

# All findings anywhere under legacy_app/
file: *legacy_app/*
```

### `callsite:` rules

The pattern must equal the prescription's `filepath:line_number` exactly — no globbing. Use the file path exactly as django-query-doctor prints it in its reports:

```text title=".queryignore"
callsite: /app/blog/views.py:87
```

### `ignore:` rules

The pattern has the form `issue_type:path_substring` (an optional third `:`-separated part is accepted and ignored). It suppresses prescriptions whose issue type matches **and** whose callsite path **contains** the given substring (plain substring, not a glob):

```text title=".queryignore"
# Known N+1 in the legacy dashboard - tracked in JIRA-1234
ignore: n_plus_one:dashboard

# Duplicate queries in test fixtures are intentional
ignore: duplicate_query:tests/
```

The issue type must be one of the values below (these are the `IssueType` enum values, not the analyzer names):

| Issue type value | Produced by |
|---|---|
| `n_plus_one` | nplusone analyzer |
| `duplicate_query` | duplicate analyzer |
| `missing_index` | missing_index analyzer |
| `fat_select` | fat_select analyzer |
| `queryset_eval` | queryset_eval analyzer |
| `complexity` | complexity analyzer |
| `serializer_method_field` | serializer_method analyzer (`check_serializers`) |

> **Note:** It is `n_plus_one`, not `nplusone`, and `duplicate_query`, not `duplicate`. A rule written with the analyzer name instead of the issue type value never matches — and no warning is printed.

### `sql:` rules

Best-effort matching against the prescription's **description text**: the pattern is glob-matched as a substring of the description, and SQL `%` wildcards are treated as `*`:

```text title=".queryignore"
# Suppress findings that mention the author table
sql: %myapp_author%
```

Because prescription descriptions contain table names rather than full SQL, `sql:` rules are mostly useful for table-name matching. Prefer `file:` or `ignore:` rules where possible.

---

## Examples

### Suppress a Known N+1 in a Legacy View

```text title=".queryignore"
# Legacy view has N+1 on author - tracked in JIRA-1234
ignore: n_plus_one:blog/views.py
```

### Suppress All Issues in Generated Code

```text title=".queryignore"
# Auto-generated admin modules
file: *admin.py
```

### Suppress Missing Index Warnings for a Small Table

```text title=".queryignore"
# settings table has <100 rows, index would add overhead
ignore: missing_index:config/models.py
```

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

- [Auto-Fix](auto-fix.md) -- Fix issues instead of ignoring them.
- [Middleware](middleware.md) -- Where per-request suppression happens.
