"""Fail if an em dash or en dash reaches a comment, a docstring, or a config file.

CLAUDE.md forbids U+2014 and U+2013 in Python source and in config files, and
grants three exemptions because in those places the dash is *data*, not prose:

1. **Program output** -- anything that reaches a terminal, a file we write, or
   a generated artifact. Changing it changes observable output and, for the
   SVGs, requires regenerating committed artifacts.
2. **Test assertions and fixtures** -- an expected value is the thing under
   test.
3. **Functional literals** -- a dash inside a regex character class matches
   real repo prose.

The baseline when this gate was written was **zero** violations, which is the
cheapest moment to install it: it ships green with no accompanying sweep. The
exposure it closes is that the clean state was unenforced, so the next
contributor -- or the next generated patch -- could reintroduce it silently.

Classification is by **token kind**, as CLAUDE.md prescribes, not by grepping:
a bare grep cannot tell a docstring from the inside of a ``print()`` heredoc,
and that distinction is exactly what the exemptions turn on. Each ``.py`` file
is tokenized; only COMMENT tokens and docstring STRING tokens are flagged. A
docstring is the first statement of a Module, ClassDef, FunctionDef or
AsyncFunctionDef. Every other string -- including the ``title=`` arguments in
``examples/generate_svgs.py`` and the ``print(\"\"\"...\"\"\")`` heredocs in
``examples/scripts/`` -- falls outside the check automatically, so exemption 1
does not have to be maintained as a list.

Config files have no token kinds, so they are checked line by line against an
explicit allowlist of the two known-exempt occurrences.

Repo markdown is deliberately **out of scope**: CLAUDE.md states it
intentionally keeps em dashes. The ASCII goal is program output plus fixer
bytes, not the whole tree.

Run:

    python -m scripts.dash_gate
"""

from __future__ import annotations

import ast
import io
import subprocess
import sys
import tokenize
from pathlib import Path

# Built by code point rather than written literally. This file is the one
# place in the tree that has to name these characters, and spelling them out
# would make the gate the only source of the bytes it exists to keep out --
# as well as tripping ruff's own RUF001 ambiguous-character rule.
EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)
DASHES = (EM_DASH, EN_DASH)

CONFIG_SUFFIXES = (".toml", ".yaml", ".yml", ".cfg", ".ini", ".sh")
CONFIG_NAMES = (".gitignore",)

# Exemption 1 applied to config files, which have no token kinds to classify
# by. Both of these are program output: mkdocs.yml's site_description is
# rendered onto the documentation site, and the .sh line is an echo. Keyed by
# (path, exact line content) so a *different* dash on the same line still
# fails.
CONFIG_ALLOWLIST: set[tuple[str, str]] = {
    (
        "mkdocs.yml",
        f"  Detects N+1s, duplicates, missing indexes, and more {EM_DASH} with exact",
    ),
    (
        "examples/scripts/11_auto_fix.sh",
        f'echo "# Preview fixes (safe {EM_DASH} changes nothing):"',
    ),
}


def tracked_files() -> list[str]:
    """Return every git-tracked path, so untracked scratch files are ignored."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode()
    return [p for p in out.split("\0") if p]


def docstring_line_ranges(source: str) -> set[int]:
    """Return the line numbers occupied by docstrings in ``source``.

    Args:
        source: The Python source text.

    Returns:
        Every 1-based line number that is part of a docstring.
    """
    lines: set[int] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return lines
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = first.end_lineno or first.lineno
            lines.update(range(first.lineno, end + 1))
    return lines


def check_python(path: str, source: str) -> list[str]:
    """Flag dashes in COMMENT tokens and docstring STRING tokens.

    Args:
        path: Repo-relative path, used only in messages.
        source: The Python source text.

    Returns:
        One message per violation.
    """
    violations: list[str] = []
    doc_lines = docstring_line_ranges(source)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return violations

    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            kind = "comment"
        elif tok.type == tokenize.STRING and tok.start[0] in doc_lines:
            kind = "docstring"
        else:
            continue
        for dash in DASHES:
            if dash in tok.string:
                name = "em dash" if dash == EM_DASH else "en dash"
                violations.append(f"{path}:{tok.start[0]}: {name} in {kind}")
                break
    return violations


def check_config(path: str, text: str) -> list[str]:
    """Flag dashes in a config file, honouring the program-output allowlist.

    Args:
        path: Repo-relative path, used for the allowlist lookup and messages.
        text: The file contents.

    Returns:
        One message per violation.
    """
    violations: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not any(dash in line for dash in DASHES):
            continue
        if (path, line) in CONFIG_ALLOWLIST:
            continue
        name = "em dash" if EM_DASH in line else "en dash"
        violations.append(f"{path}:{number}: {name} in config")
    return violations


def main() -> int:
    """Run the gate over the tracked tree.

    Returns:
        0 when clean, 1 when any violation was found.
    """
    violations: list[str] = []
    for rel in tracked_files():
        path = Path(rel)
        is_config = path.suffix in CONFIG_SUFFIXES or path.name in CONFIG_NAMES
        if path.suffix != ".py" and not is_config:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if path.suffix == ".py":
            violations.extend(check_python(rel, text))
        else:
            violations.extend(check_config(rel, text))

    if violations:
        print(f"Dash gate: {len(violations)} violation(s).")
        for line in violations:
            print(f"  {line}")
        print(
            "\nWrite '--' for an em dash and '-' for an en dash. If the dash is "
            "program output, a test fixture or a functional literal, it is "
            "exempt -- see scripts/dash_gate.py."
        )
        return 1

    print("Dash gate: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
