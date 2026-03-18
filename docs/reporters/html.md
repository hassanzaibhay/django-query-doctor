# HTML Dashboard Reporter

The HTML reporter generates a standalone, interactive HTML file that can be
opened in any browser. It is designed for team reviews, periodic audits, and
sharing query health status with stakeholders who may not have access to the
terminal or CI logs.

## Configuration

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.HTMLReporter",
    ],

    # HTML-specific settings
    "HTML_OUTPUT_DIR": "reports/html/",
    "HTML_TEMPLATE": None,           # Use default template, or path to custom
    "HTML_TITLE": "Query Doctor Report",
    "HTML_INCLUDE_SQL": True,
    "HTML_MAX_REPORTS": 50,          # Keep last N reports
}
```

### Setting Details

| Setting | Default | Description |
|---------|---------|-------------|
| `HTML_OUTPUT_DIR` | `"reports/html/"` | Directory where HTML files are written. Created automatically. |
| `HTML_TEMPLATE` | `None` | Path to a custom Jinja2 or Django template. When `None`, the built-in template is used. |
| `HTML_TITLE` | `"Query Doctor Report"` | Title shown in the HTML page header and browser tab. |
| `HTML_INCLUDE_SQL` | `True` | Whether to include raw SQL in expandable sections. |
| `HTML_MAX_REPORTS` | `50` | Maximum number of report files to retain. Oldest files are deleted when this limit is exceeded. |

## Features

The generated HTML report includes these interactive features:

### Summary Dashboard

The top of the report shows an at-a-glance summary:

- Total queries executed across the analyzed scope
- Total prescriptions grouped by severity (critical, warning, info)
- Time spent in database queries
- Endpoints with the most issues

### Sortable Tables

Prescription tables can be sorted by clicking column headers:

- **Severity** -- group critical issues at the top
- **Analyzer** -- see all N+1 issues together
- **Location** -- group by file to plan fixes efficiently
- **Query Count** -- find the most repeated queries

### Severity Filtering

Toggle buttons allow filtering prescriptions by severity level. Click
"Critical" to see only the most impactful issues, or "All" to see everything.

### Expandable SQL

Each prescription row has an expand/collapse toggle that reveals the full SQL
statement and stack trace. This keeps the default view clean while allowing
drill-down when needed.

### Self-Contained

The HTML file embeds all CSS and JavaScript inline. No external dependencies
are required to open it -- just double-click the file or share it via email
or Slack.

## Example Usage

### Generate During Development

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
        "query_doctor.reporters.HTMLReporter",
    ],
    "HTML_OUTPUT_DIR": "reports/html/",
}
```

After browsing your application, open the generated report:

```bash
open reports/html/query_doctor_2026-03-18T14-32-01.html
```

### Generate via Management Command

```bash
python manage.py check_queries --reporter html --output reports/html/
```

### Generate a Project-Wide Report

The `diagnose_project` command can produce a comprehensive HTML report
covering all endpoints:

```bash
python manage.py diagnose_project --reporter html --output reports/project-health.html
```

This generates a report with:

- Per-app health scores
- Sortable app scoreboard
- Per-URL prescription details
- Aggregated severity breakdown

## Custom Templates

To customize the report appearance, provide your own template:

```python title="settings.py"
QUERY_DOCTOR = {
    "HTML_TEMPLATE": "my_templates/query_doctor_report.html",
}
```

The template receives these context variables:

| Variable | Type | Description |
|----------|------|-------------|
| `title` | `str` | Report title from settings |
| `timestamp` | `datetime` | When the report was generated |
| `prescriptions` | `list[dict]` | All prescriptions with full details |
| `summary` | `dict` | Aggregated counts by severity and analyzer |
| `request_metadata` | `dict` | HTTP method, path, status code, timing |

!!! note "Template engine"
    The built-in template uses Django's template engine. Custom templates
    must be valid Django templates or Jinja2 templates if you have
    Jinja2 configured as a Django template backend.

## Using for Team Reviews

The HTML report is particularly useful for periodic query health reviews:

1. Run `diagnose_project` on a staging environment weekly
2. Share the HTML file with the team
3. Sort by severity to prioritize fixes
4. Use expandable SQL sections to understand each issue
5. Track improvement by comparing reports over time

!!! tip "Archiving reports"
    Set `HTML_MAX_REPORTS` to control disk usage. For long-term tracking,
    archive reports to S3 or another object store as part of your CI pipeline.

See also: [Reporters Overview](overview.md) | [JSON Reporter](json.md) | [Console Reporter](console.md)
