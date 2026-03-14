"""
Minimal setup — just the middleware, zero other config.
This is all you need to get started.
"""

MIDDLEWARE = [
    # ... your middleware ...
    "query_doctor.QueryDoctorMiddleware",
]
# Done. Everything uses sensible defaults.
