"""Record every ``Prescription.description`` a pytest session constructs.

Loaded as a plugin by :mod:`tests.test_description_invariance`, which runs the
suite in a subprocess and diffs the result against the stored corpus. The
collection point is ``Prescription.__init__`` rather than any analyzer's entry
point, so a description is recorded whoever built it.

Writes to the path in ``QD_DESCRIPTION_OUT``: one description per line, sorted,
deduplicated. Sorting makes the file diffable; deduplicating makes it
independent of how many tests happen to exercise a given string.
"""

from __future__ import annotations

import os
import pathlib

from query_doctor.analyzers.base import Prescription

_seen: set[str] = set()
_original_init = Prescription.__init__


def _recording_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Construct the prescription, then note the description it carries."""
    _original_init(self, *args, **kwargs)
    description = getattr(self, "description", None)
    if isinstance(description, str) and description:
        _seen.add(description)


Prescription.__init__ = _recording_init  # type: ignore[method-assign]


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    """Write the sorted, deduplicated corpus."""
    out = os.environ.get("QD_DESCRIPTION_OUT")
    if not out:
        return
    body = "\n".join(sorted(_seen))
    pathlib.Path(out).write_text(body + "\n", encoding="utf-8")
