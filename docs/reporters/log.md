# Log File Reporter

The Log reporter outputs prescriptions through Python's standard `logging`
module. This integrates naturally with your existing logging infrastructure --
prescriptions appear alongside your application logs and flow through whatever
handlers you already have configured (files, Sentry, ELK, CloudWatch, etc.).

## Configuration

```python title="settings.py"
QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.LogReporter",
    ],

    # Log-specific settings
    "LOG_LOGGER_NAME": "query_doctor",
    "LOG_LEVEL": "WARNING",
    "LOG_INCLUDE_SQL": False,
    "LOG_FORMAT": "{severity} | {analyzer} | {issue} | {location} | {suggestion}",
}
```

### Setting Details

| Setting | Default | Description |
|---------|---------|-------------|
| `LOG_LOGGER_NAME` | `"query_doctor"` | Name of the Python logger to use. Change this to route prescriptions through a specific logger hierarchy. |
| `LOG_LEVEL` | `"WARNING"` | Python log level for prescription messages. Critical prescriptions always use `logging.ERROR`. |
| `LOG_INCLUDE_SQL` | `False` | Whether to include the SQL statement in log messages. |
| `LOG_FORMAT` | See above | Format string for prescription log messages. Available variables: `{severity}`, `{analyzer}`, `{issue}`, `{location}`, `{suggestion}`. |

## Log Level Mapping

The reporter maps prescription severities to Python log levels:

| Prescription Severity | Python Log Level |
|----------------------|------------------|
| `CRITICAL` | `logging.ERROR` |
| `WARNING` | `logging.WARNING` |
| `INFO` | `logging.INFO` |
| `DEBUG` | `logging.DEBUG` |

## Example Log Output

```
WARNING  query_doctor: WARNING | NPlusOneAnalyzer | 50 queries fetching Author for each Book | views.py:42 | Add select_related('author') to queryset
WARNING  query_doctor: WARNING | DuplicateQueryAnalyzer | Query executed 12 times | serializers.py:18 | Use prefetch_related('categories')
ERROR    query_doctor: CRITICAL | NPlusOneAnalyzer | 200 queries fetching OrderItem for each Order | views.py:87 | Add prefetch_related('items') to queryset
```

## Django Logging Configuration

Configure the `query_doctor` logger in your Django `LOGGING` setting to control
where prescriptions are sent:

### File Output

```python title="settings.py"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "query_doctor": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "query_doctor_file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": "logs/query_doctor.log",
            "formatter": "query_doctor",
        },
    },
    "loggers": {
        "query_doctor": {
            "handlers": ["query_doctor_file"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
```

### Sentry Integration

If you use [Sentry](https://sentry.io/) for error tracking, critical query
issues will appear as Sentry events automatically when you configure the logger
to propagate:

```python title="settings.py"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "query_doctor": {
            "level": "ERROR",     # Only critical issues go to Sentry
            "propagate": True,    # Let Sentry's handler pick them up
        },
    },
}
```

!!! tip "Sentry breadcrumbs"
    Lower-severity prescriptions (WARNING, INFO) will appear as Sentry
    breadcrumbs on error events, giving you query health context when
    debugging production errors.

### ELK Stack (Elasticsearch, Logstash, Kibana)

For structured logging compatible with ELK, use a JSON formatter:

```python title="settings.py"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "query_doctor_elk": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/query_doctor.json",
            "formatter": "json",
        },
    },
    "loggers": {
        "query_doctor": {
            "handlers": ["query_doctor_elk"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
```

!!! note "python-json-logger"
    The example above uses `python-json-logger` for structured JSON log output.
    Install it with `pip install python-json-logger`.

### CloudWatch / GCP Cloud Logging

Cloud logging services typically ingest structured JSON from stdout. Combine the
Log reporter with a JSON formatter and stream handler:

```python title="settings.py"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
        },
    },
    "handlers": {
        "console_json": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "query_doctor": {
            "handlers": ["console_json"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
```

## Combining with Other Reporters

The Log reporter pairs well with the Console reporter -- use Console for
interactive development and Log for production monitoring:

```python title="settings.py"
import os

QUERY_DOCTOR = {
    "REPORTERS": [
        "query_doctor.reporters.ConsoleReporter",
        "query_doctor.reporters.LogReporter",
    ] if not os.getenv("PRODUCTION") else [
        "query_doctor.reporters.LogReporter",
    ],
}
```

See also: [Reporters Overview](overview.md) | [Console Reporter](console.md) | [JSON Reporter](json.md)
