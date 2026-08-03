"""Fail when a document quotes tool output that ``src/`` can no longer emit.

Four of the six blockers found in the 2.3.0 post-release audit shared one
root cause: the release changed a string an analyzer emits, and nothing swept
for the statements downstream of it. The stale wording survived in the
README's headline example, in eleven other documents, and in the generator
that rebuilds the committed screenshots -- where it was re-emitted on every
regeneration, so the artifact and the generator agreed with each other and
the existing freshness check stayed green.

Two checks, both mechanical:

A. **Emitted-string shape.** Every f-string an analyzer builds is reduced by
   ``ast`` to its ordered constant segments. A line quoting the first segment
   must also carry the rest, in order, separated by non-empty gaps. The gap is
   the interpolated value, and requiring it non-empty is what discriminates:
   ``Add .select_related('author') to your queryset`` runs out of room before
   `` queryset`` and fails, while ``... to your Book queryset`` leaves ``Book``
   and passes.

B. **Version literals.** A version presented as *output* -- a bare ``X.Y.Z``
   in a block that printed ``__version__``, or a ``"version": "X.Y.Z"`` field
   a reporter emits -- must agree with ``src/query_doctor/__init__.py``. One
   such line read ``1.0.3`` for six releases.

Scoped to ``git ls-files``, so a gitignored ``site/`` build is invisible --
and so is an *untracked* file, including this one. That is why the module
scans itself and why a test asserts it is tracked: a clean run made before
the file under test is staged is a clean run over a different tree.

``scripts/`` is in scope deliberately: a docs-only gate would have stayed
green through the defect that motivated this one. ``tests/`` is out of scope,
because a fixture is allowed to carry any string it likes as input.

Imports nothing from ``query_doctor``: it is an ``ast`` and regex pass over
the tree, so it runs in the install-free ``docs-gate`` CI job alongside
``dash_gate`` and ``docs_truth_sweep``.

Run:

    python -m scripts.staleness_gate
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from html import unescape
from pathlib import Path

# Modules whose f-strings define what the tool can say. Prescription text is
# built here and nowhere else.
ANALYZER_DIR = "src/query_doctor/analyzers"
VERSION_FILE = "src/query_doctor/__init__.py"

# Documents that quote tool output. `tests/` is deliberately absent.
SCOPE_PREFIXES = ("docs/", "examples/", "scripts/")
SCOPE_FILES = ("README.md", "UPGRADING.md", "CHANGELOG.md", "CONTRIBUTING.md")
SCOPE_SUFFIXES = (".md", ".py", ".txt", ".svg", ".json", ".html", ".sh")

# This module scans itself. It is the one file guaranteed to be in the scan
# whenever the gate runs, so its presence is what proves the scan is reading
# the tree being committed rather than a stale or partial one -- see
# `test_the_gate_module_is_tracked`. Its own quotations of stale output are
# allowlisted line by line below rather than waved through wholesale.
SELF = "scripts/staleness_gate.py"

# A template needs enough literal text to identify itself. Below this a short
# anchor such as f"{a}: {b}" would match unrelated prose.
MIN_SEGMENTS = 2
MIN_LITERAL_CHARS = 15

# Keyed by (repo-relative posix path, exact full line content) so an entry
# excuses exactly one line on one page, and a *different* drift on the same
# line still fails. Line numbers are deliberately not used: they move.
# Each entry states why the line is allowed to disagree with src/.
ALLOWLIST: set[tuple[str, str]] = {
    (
        # A schematic, not a transcript: the block contrasts what the report
        # holds before and after applying select_related, and abbreviates both
        # findings to their analyzer tag plus the identifying clause. The
        # `[n_plus_one]` prefix is not something the reporter prints either.
        "docs/guides/how-it-works.md",
        'before: [n_plus_one] N+1 detected: 6 queries for table "testapp_author"',
    ),
    # The four entries below are this module quoting the pre-2.3.0 strings in
    # order to explain itself. They are listed individually rather than by
    # exempting the file, because the file must stay in its own scan: it is
    # the one path guaranteed present on every run, so its presence is what
    # shows the scan is reading the tree being committed. Each is keyed by
    # exact content, so rewording any of them fails until this list is
    # updated -- which is the intended cost.
    (
        SELF,
        "   ``Add .select_related('author') to your queryset`` runs out of room before",
    ),
    (
        SELF,
        "        'before: [n_plus_one] N+1 detected: 6 queries for table \"testapp_author\"',",
    ),
    (
        SELF,
        '        # trigger is often a substring of another -- `" queries for table \\""`',
    ),
    (
        SELF,
        '        # sits inside `" identical queries for table \\""` -- so a duplicate-query',
    ),
}

_VERSION_RE = re.compile(r"^\s*(\d+\.\d+\.\d+)\s*$")
_VERSION_FIELD_RE = re.compile(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"')
_VERSION_ECHO = "__version__"


def tracked_files(rev: str | None = None) -> list[str]:
    """Return every tracked path, at HEAD or at a historical revision.

    Args:
        rev: A git revision. ``None`` reads the working tree.

    Returns:
        Repo-relative posix paths.
    """
    if rev is None:
        cmd = ["git", "ls-files", "-z"]
        out = subprocess.run(cmd, capture_output=True, check=True).stdout.decode()
        return [p for p in out.split("\0") if p]
    cmd = ["git", "ls-tree", "-r", "--name-only", "-z", rev]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout.decode()
    return [p for p in out.split("\0") if p]


def make_reader(rev: str | None = None) -> Callable[[str], str | None]:
    """Return a reader for file contents at HEAD or a historical revision.

    Evaluating a past revision is what lets the gate's own test prove it
    would have caught the defects that motivated it, without a checkout.

    Args:
        rev: A git revision. ``None`` reads the working tree.

    Returns:
        A callable mapping a repo-relative path to its text, or ``None``
        when the path is unreadable or not valid UTF-8.
    """

    def read(relpath: str) -> str | None:
        try:
            if rev is None:
                return Path(relpath).read_text(encoding="utf-8")
            done = subprocess.run(
                ["git", "show", f"{rev}:{relpath}"],
                capture_output=True,
                check=True,
            )
            return done.stdout.decode("utf-8")
        except (OSError, UnicodeDecodeError, subprocess.CalledProcessError):
            return None

    return read


def _segments(node: ast.JoinedStr) -> list[str]:
    """Reduce an f-string to its ordered non-empty constant segments."""
    out: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str) and part.value:
            out.append(part.value)
    return out


def emitted_templates(read: Callable[[str], str | None], files: Iterable[str]) -> list[list[str]]:
    """Extract the constant segments of every analyzer f-string.

    Args:
        read: A reader from :func:`make_reader`.
        files: The tracked paths to consider.

    Returns:
        One list of ordered constant segments per template.
    """
    templates: list[list[str]] = []
    for relpath in files:
        if not relpath.startswith(ANALYZER_DIR) or not relpath.endswith(".py"):
            continue
        text = read(relpath)
        if text is None:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.JoinedStr):
                continue
            segs = _segments(node)
            if len(segs) < MIN_SEGMENTS:
                continue
            if sum(len(s) for s in segs) < MIN_LITERAL_CHARS:
                continue
            if segs not in templates:
                templates.append(segs)
    return templates


def line_matches_template(line: str, segments: list[str]) -> bool:
    """Report whether ``line`` carries every segment in order with real gaps.

    A gap is the interpolated value the template omits. Requiring it non-empty
    is the whole discriminating power of the check: without it, a line that
    simply concatenated the constants would pass.

    Args:
        line: A single line of a document.
        segments: Ordered constant segments of one template.

    Returns:
        ``True`` when the line is consistent with the template.
    """
    pos = line.find(segments[0])
    if pos < 0:
        return False
    pos += len(segments[0])
    for seg in segments[1:]:
        found = line.find(seg, pos)
        if found < 0:
            return False
        if found == pos:  # empty gap: nothing was interpolated
            return False
        pos = found + len(seg)
    return True


def allowlist_line_span(text: str) -> set[int]:
    """Return the lines the ``ALLOWLIST`` literal occupies in this module.

    Allowlisting a line means writing that line out again, so the entry
    quotes the very string it excuses and trips the check a second time.
    Skipping the literal's own span resolves that without exempting the
    module: every string inside it is, by construction, a quotation of a
    line already justified there.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    for node in ast.walk(tree):
        target = getattr(node, "target", None)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(target, ast.Name)
            and target.id == "ALLOWLIST"
        ):
            return set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return set()


def _readable(line: str, *, markup: bool) -> str:
    """Return the text a reader sees, undoing the quoting a format adds.

    Three formats re-spell the quotes the templates contain: SVG and HTML
    escape them as entities, and Python string literals, JSON values and
    fenced JSON samples backslash-escape them. Comparing against the raw
    bytes reports drift that is only encoding.
    """
    if markup:
        line = unescape(line)
    return line.replace('\\"', '"').replace("\\'", "'")


def trigger_of(segments: list[str]) -> str:
    """Return the segment that decides whether a line is quoting this template.

    The longest constant, not the first. ``missing_index`` opens with
    ``"Add to "``, which appears in ordinary prose; its longest segment,
    ``"'s Meta.indexes: indexes = ["``, does not. Anchoring on the first
    segment produced 20+ false positives on this tree.
    """
    return max(segments, key=len)


def group_by_trigger(templates: list[list[str]]) -> dict[str, list[list[str]]]:
    """Group templates by their trigger segment.

    Several templates legitimately share one: the N+1 analyzer emits a
    relation form, a bulk-fetch form and a write form, all carrying
    ``" queries for table \\""``. A line matching *any* template in the group
    is consistent with what the tool can emit.
    """
    grouped: dict[str, list[list[str]]] = {}
    for segments in templates:
        grouped.setdefault(trigger_of(segments), []).append(segments)
    return grouped


def check_emitted_strings(
    relpath: str,
    text: str,
    grouped: dict[str, list[list[str]]],
    skip_lines: set[int] | None = None,
) -> list[str]:
    """Flag lines that quote a template's trigger but match none of its forms.

    Args:
        relpath: Repo-relative posix path, used in the message.
        text: The document's contents.
        grouped: Output of :func:`group_by_trigger`.

    Returns:
        ``path:line: reason`` strings, one per violation.
    """
    markup = relpath.endswith((".svg", ".html"))
    violations: list[str] = []
    skip = skip_lines or set()
    for number, raw in enumerate(text.splitlines(), start=1):
        if number in skip or (relpath, raw) in ALLOWLIST:
            continue
        line = _readable(raw, markup=markup)

        # Every template the line could be quoting, not just the first. One
        # trigger is often a substring of another -- `" queries for table \""`
        # sits inside `" identical queries for table \""` -- so a duplicate-query
        # line trips the N+1 trigger too. Judging it against only the first
        # trigger found reported 8 false positives on this tree.
        candidates = [
            segments for trigger, forms in grouped.items() if trigger in line for segments in forms
        ]
        if not candidates:
            continue
        if any(line_matches_template(line, segments) for segments in candidates):
            continue

        shapes = " | ".join(" ... ".join(s) for s in candidates)
        violations.append(
            f"{relpath}:{number}: quotes tool output but matches no string src/ emits ({shapes})"
        )
    return violations


def check_version_literals(relpath: str, text: str, version: str) -> list[str]:
    """Flag a version presented as output that disagrees with ``__version__``.

    Args:
        relpath: Repo-relative posix path.
        text: The document's contents.
        version: The value of ``__version__``.

    Returns:
        ``path:line: reason`` strings, one per violation.
    """
    violations: list[str] = []
    lines = text.splitlines()
    echoed = False
    for number, line in enumerate(lines, start=1):
        if (relpath, line) in ALLOWLIST:
            continue

        field = _VERSION_FIELD_RE.search(line)
        if field and field.group(1) != version:
            violations.append(
                f"{relpath}:{number}: reports version {field.group(1)!r}, but "
                f"{VERSION_FILE} says {version!r}"
            )

        if _VERSION_ECHO in line:
            echoed = True
            continue
        bare = _VERSION_RE.match(line)
        if echoed and bare:
            if bare.group(1) != version:
                violations.append(
                    f"{relpath}:{number}: shows {bare.group(1)!r} as the output of "
                    f"{_VERSION_ECHO}, but {VERSION_FILE} says {version!r}"
                )
            echoed = False
        elif line.strip() and not bare:
            echoed = False
    return violations


def read_version(read: Callable[[str], str | None]) -> str:
    """Return ``__version__`` by parsing, never importing, the package."""
    text = read(VERSION_FILE)
    if text is None:
        raise RuntimeError(f"cannot read {VERSION_FILE}")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    return str(node.value.value)
    raise RuntimeError(f"no __version__ assignment in {VERSION_FILE}")


def in_scope(relpath: str) -> bool:
    """Report whether a tracked path is a document this gate reads."""
    if not relpath.endswith(SCOPE_SUFFIXES):
        return False
    if relpath in SCOPE_FILES:
        return True
    return relpath.startswith(SCOPE_PREFIXES)


def sweep(rev: str | None = None) -> list[str]:
    """Run both checks over the tracked tree at ``rev``.

    Args:
        rev: A git revision, or ``None`` for the working tree.

    Returns:
        Every violation, as ``path:line: reason``.
    """
    read = make_reader(rev)
    files = tracked_files(rev)
    grouped = group_by_trigger(emitted_templates(read, files))
    version = read_version(read)

    violations: list[str] = []
    for relpath in files:
        if not in_scope(relpath):
            continue
        text = read(relpath)
        if text is None:
            continue
        skip = allowlist_line_span(text) if relpath == SELF else None
        violations.extend(check_emitted_strings(relpath, text, grouped, skip))
        violations.extend(check_version_literals(relpath, text, version))
    return violations


def main() -> int:
    """Run the gate over the tracked tree.

    Returns:
        0 when clean, 1 when any violation was found.
    """
    violations = sweep()
    if violations:
        print(f"Staleness gate: {len(violations)} violation(s).")
        for line in violations:
            print(f"  {line}")
        print(
            "\nA document quotes output src/ no longer emits. Regenerate the "
            "captures (pytest scripts/regen_examples.py -c pyproject.toml -q -s) "
            "or correct the prose. If the line is deliberately historical, add "
            "it to ALLOWLIST in scripts/staleness_gate.py with a reason."
        )
        return 1

    print("Staleness gate: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
