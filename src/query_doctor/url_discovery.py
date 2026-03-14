"""Discover all URL patterns in the Django project.

Walks the Django URL resolver tree to find all concrete URL patterns,
groups them by app namespace, and detects HTTP methods from views.
Used by the diagnose_project command for project-wide health scanning.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("query_doctor")

_DEFAULT_EXCLUDES = ["/admin/", "/static/", "/media/", "/__debug__/"]


@dataclass
class DiscoveredURL:
    """A URL pattern discovered from the Django URL configuration."""

    pattern: str
    name: str | None
    app_name: str
    view_name: str
    methods: list[str] = field(default_factory=lambda: ["GET"])
    has_parameters: bool = False


def discover_urls(
    apps: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[DiscoveredURL]:
    """Walk the URL resolver tree and return all concrete URL patterns.

    Resolves nested includes recursively, groups by app namespace,
    and detects HTTP methods from view classes.

    Args:
        apps: Only return URLs from these app namespaces. None means all.
        exclude_patterns: URL prefixes to exclude. Defaults to admin/static/media.

    Returns:
        List of DiscoveredURL objects.
    """
    excludes = exclude_patterns if exclude_patterns is not None else _DEFAULT_EXCLUDES

    try:
        from django.urls import get_resolver

        resolver = get_resolver()
        urls: list[DiscoveredURL] = []
        _walk_resolver(resolver, "", "", urls, excludes)

        if apps is not None:
            urls = [u for u in urls if u.app_name in apps]

        return urls
    except Exception:
        logger.warning("query_doctor: URL discovery failed", exc_info=True)
        return []


def _walk_resolver(
    resolver: Any,
    prefix: str,
    namespace: str,
    urls: list[DiscoveredURL],
    excludes: list[str],
) -> None:
    """Recursively walk URL resolver tree.

    Args:
        resolver: Django URLResolver or URLPattern.
        prefix: Current URL prefix.
        namespace: Current app namespace.
        urls: Accumulator list for discovered URLs.
        excludes: URL prefixes to skip.
    """
    from django.urls import URLPattern, URLResolver

    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            new_prefix = prefix + _pattern_to_str(pattern.pattern)
            new_namespace = pattern.namespace or namespace
            _walk_resolver(pattern, new_prefix, new_namespace, urls, excludes)
        elif isinstance(pattern, URLPattern):
            full_path = "/" + prefix + _pattern_to_str(pattern.pattern)
            full_path = re.sub(r"//+", "/", full_path)

            if any(full_path.startswith(ex) for ex in excludes if ex):
                continue

            has_params = bool(re.search(r"<\w+:?\w*>", full_path))
            view_name = _get_view_name(pattern.callback)
            app_name = namespace or _infer_app_name(pattern.callback)
            methods = _detect_methods(pattern.callback)

            urls.append(
                DiscoveredURL(
                    pattern=full_path,
                    name=pattern.name,
                    app_name=app_name,
                    view_name=view_name,
                    methods=methods,
                    has_parameters=has_params,
                )
            )


def _pattern_to_str(pattern: Any) -> str:
    """Convert a URL pattern object to its string representation.

    Args:
        pattern: Django RoutePattern or RegexPattern.

    Returns:
        The URL pattern string.
    """
    if hasattr(pattern, "_route"):
        return str(pattern._route)
    return str(pattern)


def _get_view_name(callback: Any) -> str:
    """Extract the view name from a callback.

    Args:
        callback: View function or class.

    Returns:
        Human-readable view name string.
    """
    if hasattr(callback, "view_class"):
        return str(callback.view_class.__name__)
    if hasattr(callback, "__name__"):
        return str(callback.__name__)
    return str(callback)


def _infer_app_name(callback: Any) -> str:
    """Infer the app name from a view's module path.

    Args:
        callback: View function or class.

    Returns:
        Inferred app name string.
    """
    module = getattr(callback, "__module__", "") or ""
    parts = module.split(".")
    # Filter out common non-app parts
    for part in parts:
        if part not in ("django", "views", "api", "rest_framework", ""):
            return part
    return parts[0] if parts else "unknown"


def _detect_methods(callback: Any) -> list[str]:
    """Detect HTTP methods supported by a view.

    Args:
        callback: View function or class.

    Returns:
        List of HTTP method strings (e.g., ["GET", "POST"]).
    """
    # Class-based views
    view_class = getattr(callback, "view_class", None)
    if view_class is not None:
        method_names = getattr(view_class, "http_method_names", None)
        if method_names:
            return [m.upper() for m in method_names if m != "options"]

    # DRF ViewSets
    actions = getattr(callback, "actions", None)
    if actions and isinstance(actions, dict):
        return [m.upper() for m in actions]

    # Function views — assume GET
    return ["GET"]
