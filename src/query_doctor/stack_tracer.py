"""Stack trace capture for mapping SQL queries to user source code.

Walks the call stack to find the first frame in user code (filtering out
Django internals, this package, and stdlib modules) so each query can be
attributed to a specific file:line in the application.
"""

from __future__ import annotations

import linecache
import logging
import traceback

from query_doctor.types import CallSite

logger = logging.getLogger("query_doctor")

# Modules/paths to always exclude from callsite detection
_DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "query_doctor",
    "django/db/backends",
    "django/db/models/sql",
    "django/db/models/query",
    "django\\db\\backends",
    "django\\db\\models\\sql",
    "django\\db\\models\\query",
    "importlib",
    "threading",
    "_bootstrap",
]


def capture_callsite(
    exclude_modules: list[str] | None = None,
) -> CallSite | None:
    """Walk the stack and find the first frame in user code.

    Filters out frames from query_doctor, Django internals, and stdlib.
    Returns the last remaining frame (closest to the query trigger),
    or None if no user code frame is found.
    """
    try:
        stack = traceback.extract_stack()
        if exclude_modules:
            exclude = _DEFAULT_EXCLUDE_PATTERNS + list(exclude_modules)
        else:
            exclude = _DEFAULT_EXCLUDE_PATTERNS

        # Filter frames to find user code
        user_frames = []
        for frame in stack:
            filename = frame.filename
            # Skip frames matching any exclude pattern
            if any(pattern in filename for pattern in exclude):
                continue
            # Skip frames from pytest/pluggy internals
            if any(p in filename for p in ["_pytest", "pluggy", "site-packages", "runpy.py"]):
                continue
            user_frames.append(frame)

        if not user_frames:
            return None

        # Take the last user-code frame (closest to the call site)
        frame = user_frames[-1]

        # Try to read the actual source line
        line_no = frame.lineno or 0
        code_context = linecache.getline(frame.filename, line_no).strip()

        return CallSite(
            filepath=frame.filename,
            line_number=line_no,
            function_name=frame.name,
            code_context=code_context,
        )
    except Exception:
        logger.warning("query_doctor: failed to capture callsite", exc_info=True)
        return None
