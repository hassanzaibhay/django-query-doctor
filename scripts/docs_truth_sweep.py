"""Docs truth sweep: verify every documented token has code backing.

Extracts CLI flags, QUERY_DOCTOR settings keys, management command names,
``from query_doctor... import ...`` statements, and pytest markers from
``docs/**/*.md`` and ``README.md``, then cross-checks each against the
actual source: argparse ``add_argument`` definitions, ``DEFAULT_CONFIG``
keys plus known ``config.get`` reads, files in ``management/commands/``,
and real importable names.

Exit code 0 = clean, 1 = violations found (printed with file:line).

Usage:
    python scripts/docs_truth_sweep.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "query_doctor"
COMMANDS_DIR = SRC / "management" / "commands"

# Django's own management commands that docs may legitimately mention.
DJANGO_BUILTIN_COMMANDS = {
    "migrate",
    "makemigrations",
    "runserver",
    "shell",
    "test",
    "check",
    "collectstatic",
    "startapp",
    "startproject",
    "createsuperuser",
    "dbshell",
    "loaddata",
    "dumpdata",
    "showmigrations",
    "sqlmigrate",
}

# Pytest's own markers that docs may legitimately show.
PYTEST_BUILTIN_MARKERS = {"django_db", "parametrize", "skip", "skipif", "xfail", "filterwarnings"}

# Documented placeholder modules: contributing.md walks through creating a NEW
# built-in analyzer, so its example imports a module that intentionally does
# not exist yet.
PLACEHOLDER_MODULES = {"query_doctor.analyzers.my_analyzer"}


def _load_command_flags() -> dict[str, set[str]]:
    """Parse argparse add_argument calls from each management command."""
    flags: dict[str, set[str]] = {}
    for py in sorted(COMMANDS_DIR.glob("*.py")):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.add(arg.value)
        flags[py.stem] = found
    return flags


def _load_config_keys() -> tuple[set[str], dict[str, set[str]]]:
    """Return (uppercase settings keys at any level, analyzer name -> option keys)."""
    conf_tree = ast.parse((SRC / "conf.py").read_text(encoding="utf-8"))
    default_config: dict[str, Any] | None = None
    for node in ast.walk(conf_tree):
        if (
            isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", "") == "DEFAULT_CONFIG"
            and node.value is not None
        ):
            default_config = ast.literal_eval(node.value)
    assert default_config is not None, "DEFAULT_CONFIG not found in conf.py"

    upper_keys: set[str] = set()

    def _collect(d: dict[str, Any]) -> None:
        for k, v in d.items():
            if isinstance(k, str) and k.isupper():
                upper_keys.add(k)
            if isinstance(v, dict):
                _collect(v)

    _collect(default_config)
    # Real keys read via config.get() but absent from DEFAULT_CONFIG
    # (middleware.py JSON_REPORT_PATH read; discovery.py AST_ANALYSIS +
    # SERIALIZER_MODULES read).
    upper_keys |= {"JSON_REPORT_PATH", "AST_ANALYSIS", "SERIALIZER_MODULES"}
    # Django's own settings shown alongside QUERY_DOCTOR in examples.
    upper_keys |= {"QUERY_DOCTOR", "DEBUG", "MIDDLEWARE", "INSTALLED_APPS", "DATABASES"}

    analyzers: dict[str, set[str]] = {
        name: set(opts.keys()) for name, opts in default_config["ANALYZERS"].items()
    }
    return upper_keys, analyzers


def _load_command_names() -> set[str]:
    """Return the real management command names."""
    return {p.stem for p in COMMANDS_DIR.glob("*.py") if p.name != "__init__.py"}


def _importable(module: str, names: list[str]) -> list[str]:
    """Return the subset of names NOT importable from module (static check)."""
    rel = module.replace("query_doctor", "", 1).lstrip(".")
    if rel:
        candidates = [SRC / (rel.replace(".", "/") + ".py"), SRC / rel.replace(".", "/")]
    else:
        candidates = [SRC / "__init__.py"]
    target = None
    for c in candidates:
        if c.is_file():
            target = c
        elif c.is_dir() and (c / "__init__.py").is_file():
            target = c / "__init__.py"
        if target:
            break
    if target is None:
        return names  # module itself does not exist
    tree = ast.parse(target.read_text(encoding="utf-8"))
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                defined.add(alias.asname or alias.name.split(".")[0])
    return [n for n in names if n not in defined]


def sweep() -> list[str]:
    """Run the sweep; return a list of violation strings."""
    flags_by_cmd = _load_command_flags()
    upper_keys, analyzer_opts = _load_config_keys()
    command_names = _load_command_names()
    known_commands = command_names | DJANGO_BUILTIN_COMMANDS

    violations: list[str] = []
    doc_files = [*sorted((REPO_ROOT / "docs").rglob("*.md")), REPO_ROOT / "README.md"]

    for doc in doc_files:
        text = doc.read_text(encoding="utf-8")
        # Join backslash-continued shell lines so flags stay with their command.
        joined = re.sub(r"\\\s*\n\s*", " ", text)
        lines = joined.splitlines()
        relpath = doc.relative_to(REPO_ROOT).as_posix()

        in_python_block = False
        python_block_has_qd = False

        for lineno, line in enumerate(lines, start=1):
            fence = re.match(r"^\s*```(\w*)", line)
            if fence:
                lang = fence.group(1)
                if in_python_block:
                    in_python_block = False
                    python_block_has_qd = False
                elif lang in ("python", "py", ""):
                    in_python_block = True
                continue
            if in_python_block and "QUERY_DOCTOR" in line:
                python_block_has_qd = True

            # 1. manage.py command names
            for m in re.finditer(r"manage\.py\s+([a-z_][a-z0-9_]*)", line):
                cmd = m.group(1)
                if cmd not in known_commands:
                    violations.append(f"{relpath}:{lineno}: unknown command 'manage.py {cmd}'")

            # 2. flags on lines invoking one of our commands
            for cmd in command_names:
                if re.search(rf"\b{cmd}\b", line) and ("manage.py" in line or "--" in line):
                    if not re.search(rf"manage\.py\s+{cmd}\b", line):
                        continue
                    for fm in re.finditer(r"(--[a-z][a-z0-9-]*)", line):
                        flag = fm.group(1)
                        if flag not in flags_by_cmd[cmd]:
                            violations.append(
                                f"{relpath}:{lineno}: flag '{flag}' not defined by '{cmd}'"
                            )

            # 3. UPPERCASE settings keys inside python blocks containing QUERY_DOCTOR
            if in_python_block and python_block_has_qd:
                for km in re.finditer(r"[\"']([A-Z][A-Z_]{2,})[\"']\s*:", line):
                    key = km.group(1)
                    if key not in upper_keys:
                        violations.append(f"{relpath}:{lineno}: unknown settings key '{key}'")

            # 4. dotted ANALYZERS.<name>[.<option>] references
            for am in re.finditer(r"ANALYZERS\.([a-z_]+)(?:\.([a-z_]+))?", line):
                name, opt = am.group(1), am.group(2)
                if name not in analyzer_opts:
                    violations.append(f"{relpath}:{lineno}: unknown analyzer 'ANALYZERS.{name}'")
                elif opt and opt not in analyzer_opts[name]:
                    violations.append(
                        f"{relpath}:{lineno}: unknown option 'ANALYZERS.{name}.{opt}'"
                    )

            # 5. imports from query_doctor
            im = re.match(r"\s*from (query_doctor[\w.]*) import (.+)$", line)
            if im and im.group(1) not in PLACEHOLDER_MODULES:
                module = im.group(1)
                names = [n.strip().split(" as ")[0] for n in im.group(2).split(",")]
                names = [n for n in names if n and n != "*"]
                for missing in _importable(module, names):
                    violations.append(
                        f"{relpath}:{lineno}: cannot import '{missing}' from '{module}'"
                    )

            # 6. pytest markers
            for mm in re.finditer(r"pytest\.mark\.([a-z_]+)", line):
                marker = mm.group(1)
                if marker not in PYTEST_BUILTIN_MARKERS:
                    violations.append(f"{relpath}:{lineno}: unknown pytest marker '{marker}'")

    return violations


def main() -> int:
    """Run the sweep and print results."""
    violations = sweep()
    if violations:
        print(f"{len(violations)} violation(s):")
        for v in violations:
            print(f"  {v}")
        return 1
    print("Docs truth sweep: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
