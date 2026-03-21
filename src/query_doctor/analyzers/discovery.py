"""Discovery utility for finding DRF serializer classes.

Scans installed Django apps or specific modules to find all classes that
subclass rest_framework.serializers.Serializer. Used by the check_serializers
management command and the SerializerMethodAnalyzer.

DRF may not be installed — all imports are guarded with try/except.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import Any

logger = logging.getLogger("query_doctor")


def discover_serializers(
    app_labels: list[str] | None = None,
    modules: list[str] | None = None,
) -> list[Any]:
    """Find all classes that subclass rest_framework.serializers.Serializer.

    If app_labels provided, only scan those apps.
    If modules provided, only scan those modules.
    Otherwise scan all installed apps.

    Args:
        app_labels: Optional list of Django app labels to restrict scanning.
        modules: Optional list of module paths to scan directly.

    Returns:
        List of serializer classes found. Empty list if DRF is not installed.
    """
    try:
        from rest_framework.serializers import Serializer as BaseSerializer
    except ImportError:
        logger.debug("DRF not installed, cannot discover serializers")
        return []

    found: list[Any] = []
    seen: set[int] = set()

    if modules:
        for module_path in modules:
            try:
                mod = importlib.import_module(module_path)
                _collect_serializers(mod, BaseSerializer, found, seen)
            except Exception:
                logger.debug("Failed to import module %s", module_path, exc_info=True)
        return found

    # Discover from Django apps
    app_modules = _get_app_modules(app_labels)
    for mod in app_modules:
        _collect_serializers(mod, BaseSerializer, found, seen)

    return found


def _get_app_modules(app_labels: list[str] | None = None) -> list[ModuleType]:
    """Get modules from Django apps that are likely to contain serializers.

    Scans for 'serializers' submodules within each app, as well as
    any module matching common naming patterns.

    Args:
        app_labels: Optional list of app labels to restrict to.

    Returns:
        List of imported modules.
    """
    from django.apps import apps

    modules: list[ModuleType] = []

    # Allow users to configure extra module suffixes via QUERY_DOCTOR settings
    try:
        from query_doctor.conf import get_config

        config = get_config()
        ast_config = config.get("AST_ANALYSIS", {})
        serializer_module_names = ast_config.get(
            "SERIALIZER_MODULES",
            ["serializers", "api.serializers", "api.v1.serializers", "api.v2.serializers"],
        )
    except Exception:
        serializer_module_names = [
            "serializers",
            "api.serializers",
            "api.v1.serializers",
            "api.v2.serializers",
        ]

    app_configs = apps.get_app_configs()
    if app_labels:
        app_configs = [c for c in app_configs if c.label in app_labels]

    for app_config in app_configs:
        app_module_name = app_config.name

        for suffix in serializer_module_names:
            module_path = f"{app_module_name}.{suffix}"
            try:
                mod = importlib.import_module(module_path)
                modules.append(mod)
            except ImportError:
                continue
            except Exception:
                logger.debug("Error importing %s", module_path, exc_info=True)

        # Also scan the app package itself for any serializer submodules
        try:
            app_module = importlib.import_module(app_module_name)
            if hasattr(app_module, "__path__"):
                for _importer, name, _ispkg in pkgutil.walk_packages(
                    app_module.__path__, prefix=f"{app_module_name}."
                ):
                    if "serializer" in name.lower():
                        try:
                            mod = importlib.import_module(name)
                            modules.append(mod)
                        except Exception:
                            continue
        except Exception:
            pass

    return modules


def _collect_serializers(
    module: ModuleType,
    base_class: type,
    found: list[Any],
    seen: set[int],
) -> None:
    """Collect serializer classes from a module.

    Only collects concrete (non-abstract) classes defined in the module
    (not imported from elsewhere, unless they're relevant).

    Args:
        module: The module to scan.
        base_class: The base DRF Serializer class.
        found: Accumulator list for found serializer classes.
        seen: Set of already-seen class ids to avoid duplicates.
    """
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if id(obj) in seen:
            continue

        if not issubclass(obj, base_class):
            continue

        # Skip the base classes themselves
        if obj is base_class:
            continue

        try:
            from rest_framework import serializers as drf_serializers

            if obj in (
                drf_serializers.Serializer,
                drf_serializers.ModelSerializer,
                drf_serializers.ListSerializer,
                drf_serializers.HyperlinkedModelSerializer,
            ):
                continue
        except ImportError:
            pass

        # Only include classes defined in this module or its package
        cls_module = getattr(obj, "__module__", "")
        if (
            cls_module
            and not cls_module.startswith(module.__name__.split(".")[0])
            and not cls_module.startswith("tests")
        ):
            continue

        seen.add(id(obj))
        found.append(obj)
