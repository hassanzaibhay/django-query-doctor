#!/usr/bin/env python
"""
Example 7: Async View Support
"""

print("=" * 60)
print("Example 7: Async View Support")
print("=" * 60)

print("""
# The middleware auto-detects async views. No extra config needed.

# settings.py — same as always:
MIDDLEWARE = [
    "query_doctor.QueryDoctorMiddleware",
]

# Async view — query doctor captures queries via sync_to_async:
from django.http import JsonResponse
from asgiref.sync import sync_to_async

async def async_book_list(request):
    books = await sync_to_async(list)(
        Book.objects.select_related("author").all()
    )
    return JsonResponse({"count": len(books)})

# The middleware sets:
#   sync_capable = True
#   async_capable = True
#
# State is stored in contextvars.ContextVar (not threading.local),
# so it works correctly in both sync WSGI and async ASGI deployments.
""")
