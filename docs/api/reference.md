# API Reference

!!! note "Auto-generated documentation"
    This page uses [mkdocstrings](https://mkdocstrings.github.io/) to render
    API documentation directly from source code docstrings. Some references
    may not render if module paths differ from the documented structure.

---

## Core

### QueryDoctorMiddleware

The Django middleware that intercepts queries for each request and runs them
through the analysis pipeline.

::: query_doctor.middleware.QueryDoctorMiddleware
    options:
      show_source: true
      heading_level: 4

### Context Managers

Context managers for targeted query analysis outside of the middleware.

::: query_doctor.context_managers
    options:
      show_source: true
      heading_level: 4

### Decorators

Function and method decorators for query diagnosis and budgets.

::: query_doctor.decorators
    options:
      show_source: true
      heading_level: 4

---

## Data Types

### Severity

Severity levels for prescriptions.

::: query_doctor.types.Severity
    options:
      show_source: true
      heading_level: 4

### Prescription

The data class returned by analyzers describing a detected issue and its fix.

::: query_doctor.types.Prescription
    options:
      show_source: true
      heading_level: 4

### CapturedQuery

Information captured for each SQL query during interception.

::: query_doctor.types.CapturedQuery
    options:
      show_source: true
      heading_level: 4

### DiagnosisReport

Aggregated report of all prescriptions for a request or command.

::: query_doctor.types.DiagnosisReport
    options:
      show_source: true
      heading_level: 4

---

## Analyzers

### BaseAnalyzer

The abstract base class that all analyzers implement. Subclass this to create
custom analyzers.

::: query_doctor.analyzers.base.BaseAnalyzer
    options:
      show_source: true
      heading_level: 4

### NPlusOneAnalyzer

Detects N+1 query patterns using fingerprint-based grouping.

::: query_doctor.analyzers.nplusone.NPlusOneAnalyzer
    options:
      show_source: true
      heading_level: 4

### DuplicateAnalyzer

Detects exact and near-duplicate queries within a single request.

::: query_doctor.analyzers.duplicate.DuplicateAnalyzer
    options:
      show_source: true
      heading_level: 4

### MissingIndexAnalyzer

Detects queries filtering or ordering on non-indexed columns.

::: query_doctor.analyzers.missing_index.MissingIndexAnalyzer
    options:
      show_source: true
      heading_level: 4

### FatSelectAnalyzer

Detects queries selecting more columns than necessary.

::: query_doctor.analyzers.fat_select.FatSelectAnalyzer
    options:
      show_source: true
      heading_level: 4

### QuerySetEvalAnalyzer

Detects unintended queryset evaluation patterns.

::: query_doctor.analyzers.queryset_eval.QuerySetEvalAnalyzer
    options:
      show_source: true
      heading_level: 4

### DRFSerializerAnalyzer

Detects N+1 patterns caused by DRF serializer nesting.

::: query_doctor.analyzers.drf_serializer.DRFSerializerAnalyzer
    options:
      show_source: true
      heading_level: 4

### QueryComplexityAnalyzer

Scores queries by complexity and flags those above threshold.

::: query_doctor.analyzers.complexity.QueryComplexityAnalyzer
    options:
      show_source: true
      heading_level: 4

---

## Reporters

### ConsoleReporter

Terminal output with Rich formatting and plain-text fallback.

::: query_doctor.reporters.console.ConsoleReporter
    options:
      show_source: true
      heading_level: 4

### JSONReporter

Structured JSON output for CI/CD pipelines.

::: query_doctor.reporters.json_reporter.JSONReporter
    options:
      show_source: true
      heading_level: 4

### HTMLReporter

Interactive HTML dashboard report.

::: query_doctor.reporters.html_reporter.HTMLReporter
    options:
      show_source: true
      heading_level: 4

### LogReporter

Python logging integration for production monitoring.

::: query_doctor.reporters.log_reporter.LogReporter
    options:
      show_source: true
      heading_level: 4

### OTelReporter

OpenTelemetry span export for observability platforms.

::: query_doctor.reporters.otel_exporter.OTelReporter
    options:
      show_source: true
      heading_level: 4

---

## Configuration

### get_config

Access django-query-doctor settings with defaults.

::: query_doctor.conf.get_config
    options:
      show_source: true
      heading_level: 4

---

## Fingerprinting

### SQL Fingerprinting

Normalize and hash SQL statements for grouping.

::: query_doctor.fingerprint
    options:
      show_source: true
      heading_level: 4

---

## Stack Tracing

### Source Code Mapping

Map captured queries back to user source code locations.

::: query_doctor.stack_tracer
    options:
      show_source: true
      heading_level: 4

---

## Exceptions

All exceptions raised by django-query-doctor inherit from `QueryDoctorError`:

::: query_doctor.exceptions
    options:
      show_source: true
      heading_level: 4
