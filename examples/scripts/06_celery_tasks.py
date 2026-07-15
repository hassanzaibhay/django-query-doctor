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

# --- Option A: Decorator with callback (recommended) ---
# diagnose_task does NOT print or dispatch to the REPORTERS setting;
# results are delivered only via the on_report callback.
def log_findings(report):
    for rx in report.prescriptions:
        logger.warning("%s: %s", rx.severity.value, rx.description)


@shared_task
@diagnose_task(on_report=log_findings)
def send_weekly_report():
    users = User.objects.all()
    for user in users:
        send_email(user.profile.email, generate_report(user))  # N+1 detected


# --- Option B: Inline callback ---
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


# Celery is NOT a required dependency — @diagnose_task wraps any
# callable and works the same with or without Celery installed.
""")
