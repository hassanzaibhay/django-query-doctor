#!/usr/bin/env python
"""
Example 6: Celery Task Support
"""

print("=" * 60)
print("Example 6: Celery Task Support")
print("=" * 60)

print("""
from celery import shared_task
from query_doctor.celery_integration import diagnose_task
from query_doctor import diagnose_queries

# --- Option A: Decorator ---
@shared_task
@diagnose_task
def send_weekly_report():
    users = User.objects.all()
    for user in users:
        # N+1 — will be detected and reported via configured reporters
        send_email(user.profile.email, generate_report(user))


# --- Option B: Decorator with callback ---
@shared_task
@diagnose_task(on_report=lambda r: logger.warning(f"Issues: {len(r.prescriptions)}"))
def process_orders():
    orders = Order.objects.filter(status="pending")
    for order in orders:
        order.items.all()  # N+1


# --- Option C: Context manager (works anywhere) ---
@shared_task
def cleanup_old_data():
    with diagnose_queries() as report:
        old_logs = list(ActivityLog.objects.filter(created_at__lt=cutoff))
        for log in old_logs:
            log.delete()

    if report.issues:
        logger.warning(f"Query issues in cleanup: {report.issues}")


# Celery is NOT a required dependency.
# If not installed, @diagnose_task is a no-op passthrough.
""")
