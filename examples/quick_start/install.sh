#!/bin/bash
# Quick Start — 30 seconds to working query diagnosis

# Install
pip install django-query-doctor

# Add to settings.py — ONE line:
# MIDDLEWARE = [
#     ...
#     "query_doctor.QueryDoctorMiddleware",
# ]

# Run your app
python manage.py runserver

# Visit any page. Check the console. Done.

echo "Quick start complete! Visit http://localhost:8000 and check your terminal."
