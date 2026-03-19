"""Signal handlers for QueryTurbo cache invalidation.

Clears the compilation cache on post_migrate to ensure schema changes
(new columns, removed fields, altered indexes) don't cause stale SQL.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("query_doctor.turbo")


def clear_cache_on_migrate(sender: Any, **kwargs: Any) -> None:
    """Clear the SQL compilation cache after migrations run.

    Connected to Django's post_migrate signal. Ensures that any schema
    changes are reflected in subsequent query compilations.

    Args:
        sender: The AppConfig that was migrated.
        **kwargs: Additional signal kwargs (app_config, verbosity, etc.).
    """
    from query_doctor.turbo.patch import get_cache

    cache = get_cache()
    if cache is not None:
        cache.clear()
        logger.info(
            "QueryTurbo cache cleared after migration of %s",
            getattr(sender, "label", sender),
        )
