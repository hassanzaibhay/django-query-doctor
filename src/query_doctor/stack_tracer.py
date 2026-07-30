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

# Modules/paths to always exclude from callsite detection.
#
# The whole ``django/db`` package is excluded rather than module by module. The
# list previously named only ``backends``, ``models/sql`` and ``models/query``,
# which left ``models/manager`` (every ``.objects.create()``) and ``models/base``
# (every ``.save()``) to be caught incidentally by the "site-packages" substring
# below -- so on a layout that installs to ``dist-packages`` instead, those
# frames were returned and prescriptions were attributed inside Django. Nothing
# under ``django/db`` is ever user code, so naming the package is both narrower
# to state and broader in effect than enumerating its modules.
#
# The separators are part of the pattern. These are substring tests, so an
# unanchored ``django/db`` would also drop a user's own ``/srv/mydjango/db/``
# or ``/srv/mydjango/dbrouters.py`` -- dropping a real callsite, which is the
# same class of harm in the other direction.
_DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    "query_doctor",
    "/django/db/",
    "\\django\\db\\",
    "importlib",
    "threading",
    "_bootstrap",
]

# Installed-package and test-runner paths. Both "site-packages" and
# "dist-packages" are needed: Debian and Ubuntu system Python use the latter.
_INSTALL_PATH_PATTERNS: list[str] = [
    "_pytest",
    "pluggy",
    "site-packages",
    "dist-packages",
    "runpy.py",
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
            # Skip frames from installed packages and test-runner internals
            if any(p in filename for p in _INSTALL_PATH_PATTERNS):
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
