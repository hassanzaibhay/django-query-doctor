#!/usr/bin/env python
"""
Example 10: OpenTelemetry Export
"""

print("=" * 60)
print("Example 10: OpenTelemetry Export")
print("=" * 60)

print("""
# Step 1: Install optional dependency
# pip install django-query-doctor[otel]

# Step 2: Configure your OTel SDK as usual
# (Datadog, Jaeger, Grafana Tempo, etc.)

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

# Step 3: Invoke OTelReporter yourself. It is NOT dispatched by the
# REPORTERS setting (which recognizes only console/json/log) — call it
# with a report you produced, e.g. via diagnose_queries():

from query_doctor.context_managers import diagnose_queries
from query_doctor.reporters.otel_exporter import OTelReporter

with diagnose_queries() as report:
    ...  # your ORM code

OTelReporter().report(report)

# Each call creates a "query_doctor.diagnosis" span with:
#   - Attributes: query_doctor.total_queries, .total_time_ms, .issues_found
#   - Events: one per prescription (issue_type, severity, description, fix)
#   - Status: ERROR if critical issues found, OK otherwise

# Works with any OTel-compatible backend:
#   - Datadog APM
#   - Grafana Tempo
#   - Jaeger
#   - AWS X-Ray
#   - Honeycomb
""")
