"""Django app configuration for django-query-doctor.

Registers signal handlers and installs the QueryTurbo monkey-patch
at app ready time when TURBO is enabled.
"""

from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger("query_doctor")


class QueryDoctorConfig(AppConfig):
    """App configuration for django-query-doctor."""

    name = "query_doctor"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "Query Doctor"

    def ready(self) -> None:
        """Initialize QueryTurbo if enabled.

        Installs the SQLCompiler monkey-patch and registers the
        post_migrate signal handler for cache invalidation.
        """
        try:
            from query_doctor.turbo.config import is_turbo_enabled
            from query_doctor.turbo.patch import install_patch
            from query_doctor.turbo.signals import clear_cache_on_migrate

            if is_turbo_enabled():
                install_patch()

                from django.db.models.signals import post_migrate

                post_migrate.connect(clear_cache_on_migrate)
                logger.info("QueryTurbo enabled and patch installed")
        except Exception:
            logger.warning("Failed to initialize QueryTurbo", exc_info=True)
