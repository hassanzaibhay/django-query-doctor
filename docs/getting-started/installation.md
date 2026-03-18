# Installation

## Basic Install
```bash
pip install django-query-doctor
```

## With Extras

django-query-doctor has optional dependencies for enhanced functionality:

=== "Rich Console Output"
    ```bash
    pip install django-query-doctor[rich]
    ```

=== "Celery Support"
    ```bash
    pip install django-query-doctor[celery]
    ```

=== "OpenTelemetry Export"
    ```bash
    pip install django-query-doctor[otel]
    ```

=== "Everything"
    ```bash
    pip install django-query-doctor[all]
    ```

## Requirements

| Dependency | Version |
|------------|---------|
| Python | >= 3.10 |
| Django | >= 4.2 (tested up to 6.0) |

No other dependencies are required for the base install.

## Verify Installation
```python
>>> import query_doctor
>>> print(query_doctor.__version__)
1.0.2
```

## Add to Django
```python title="settings.py"
INSTALLED_APPS = [
    ...,
    "query_doctor",
]
```

!!! tip
    You don't need to add the middleware right away. You can start with just the management commands and add the middleware later when you want real-time analysis.

## Next Steps

- [Quick Start](quickstart.md) — Get running in 2 minutes
- [Configuration](configuration.md) — Customize behavior
