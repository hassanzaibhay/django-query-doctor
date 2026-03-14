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

# Step 2: Enable the OTel reporter in settings
QUERY_DOCTOR = {
    "REPORTERS": ["console", "otel"],
}

# Step 3: Configure your OTel SDK as usual
# (Datadog, Jaeger, Grafana Tempo, etc.)

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

# Now every request creates a span with:
#   - Attributes: total_queries, total_time_ms, issues_found
#   - Events: one per prescription (issue_type, severity, description, fix)
#   - Status: ERROR if critical issues found, OK otherwise

# Works with any OTel-compatible backend:
#   - Datadog APM
#   - Grafana Tempo
#   - Jaeger
#   - AWS X-Ray
#   - Honeycomb
""")
