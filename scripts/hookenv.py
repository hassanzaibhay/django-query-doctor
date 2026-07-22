"""Run a development tool inside this repository's virtualenv.

Pre-push hooks declared with ``language: system`` resolve their executables
from ``PATH``, not from the project environment. That has failed three times
in this repository (see ``FOLLOWUPS.md`` item 11): ``ruff`` and ``mypy``
absent from ``PATH`` entirely, and ``pytest`` resolving to an unrelated
system interpreter with none of the project's dependencies. The dangerous
version of the same failure is silent -- a ``PATH`` carrying a *different*
project's virtualenv would run that project's ``pytest`` against this
repository and could exit 0, producing a green gate that proves nothing.

This launcher removes ``PATH`` from the decision. It resolves the interpreter
explicitly, runs the tool as ``<interpreter> -m <tool>``, and prints which
interpreter it used so that every hook run states its own provenance rather
than leaving it to be assumed.

Usage::

    python scripts/hookenv.py ruff check src/ tests/

Exit code is the tool's own, or 1 if the tool is not importable in the
resolved interpreter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Both layouts, because contributors are not all on the same platform:
# Windows venvs put the interpreter in Scripts/, POSIX venvs in bin/.
_VENV_CANDIDATES = (
    REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    REPO_ROOT / ".venv" / "bin" / "python",
)


def resolve_interpreter() -> tuple[Path, str]:
    """Return the interpreter to run tools with, and how it was chosen.

    Prefers this repository's ``.venv``. Falls back to the interpreter
    running this script, which is what happens in an environment that
    installs dependencies directly (CI, or a contributor using a
    differently-named environment).

    Returns:
        A ``(path, source)`` pair; ``source`` is a short label naming which
        rule selected the interpreter, for printing.
    """
    for candidate in _VENV_CANDIDATES:
        if candidate.exists():
            return candidate, "repo .venv"
    return Path(sys.executable), "current interpreter (no .venv found)"


def main(argv: list[str]) -> int:
    """Run ``argv[0]`` as a module under the resolved interpreter.

    Args:
        argv: The tool name followed by its arguments.

    Returns:
        The tool's exit code, or 1 if the tool is not importable.
    """
    if not argv:
        print("hookenv: no tool given", file=sys.stderr)
        return 1

    tool, args = argv[0], argv[1:]
    interpreter, source = resolve_interpreter()

    try:
        probe_failed = (
            subprocess.run(
                [str(interpreter), "-c", f"import {tool}"],
                capture_output=True,
                cwd=REPO_ROOT,
            ).returncode
            != 0
        )
    except OSError:
        # The interpreter path exists but will not execute -- a truncated or
        # otherwise broken venv. Report it the same way as a missing tool
        # rather than surfacing a traceback from the hook.
        probe_failed = True

    if probe_failed:
        print(f"hookenv: '{tool}' is not importable in {interpreter} ({source}).", file=sys.stderr)
        if interpreter in _VENV_CANDIDATES:
            print(
                'hookenv: install the development dependencies there: pip install -e ".[dev]"',
                file=sys.stderr,
            )
        else:
            # Under pre-commit this interpreter is pre-commit's own managed
            # environment, which will never hold the project's tools.
            # Installing into it is not the remedy; creating the project venv is.
            print(
                f"hookenv: no project virtualenv found at {REPO_ROOT / '.venv'}\n"
                f"hookenv: create one and install the development dependencies:\n"
                f"hookenv:     python -m venv .venv\n"
                f'hookenv:     .venv/Scripts/pip install -e ".[dev]"'
                f"   (POSIX: .venv/bin/pip)",
                file=sys.stderr,
            )
        return 1

    print(f"hookenv: {tool} via {interpreter} [{source}]", file=sys.stderr)
    return subprocess.run([str(interpreter), "-m", tool, *args], cwd=REPO_ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
