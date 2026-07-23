"""Claims gate: regenerate every quantitative claim from the tree and diff it.

``claims.json`` records each quantitative claim this project publishes --
analyzer count, test count, coverage, supported Django and Python ranges --
against the measurement that derives it from the source. This script performs
the measurements and reports every claim that disagrees.

It also applies two prose rules to the gated files: build durations are never
facts about the tree, and a dated assertion about something's *current status*
rots on its own, while dated *provenance* ("comparisons current as of ...")
does not.

Coverage cannot be measured without a coverage run, so the coverage rows read
``coverage.xml``. Produce it with::

    pytest -q --cov=query_doctor --cov-report=xml

Missing that file is an error, not a skip -- a gate that quietly drops rows
reports green for the wrong reason.

Exit code 0 = every claim matches, 1 = at least one violation (printed).

Usage::

    python scripts/claims_check.py [--coverage-xml coverage.xml]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "claims.json"
ANALYZERS_DIR = REPO_ROOT / "src" / "query_doctor" / "analyzers"

# Modules in analyzers/ that are infrastructure, not analyzers. Counting them
# is how "8 analyzers" would come back.
_NON_ANALYZER_MODULES = {"__init__", "base", "discovery"}


class MeasurementError(RuntimeError):
    """A measurement could not be taken, so its claims cannot be checked."""


def measure_analyzer_count() -> int:
    """Count analyzer modules on disk, excluding infrastructure."""
    return len([p for p in ANALYZERS_DIR.glob("*.py") if p.stem not in _NON_ANALYZER_MODULES])


def measure_test_count() -> int:
    """Return the number of tests pytest collects."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    if not match:
        raise MeasurementError(
            f"could not read a collection count from pytest (exit {proc.returncode}).\n"
            f"{proc.stdout[-2000:]}"
        )
    return int(match.group(1))


def measure_coverage_percent(coverage_xml: Path) -> float:
    """Return total line coverage as a percentage, from a coverage XML report."""
    if not coverage_xml.exists():
        raise MeasurementError(
            f"{coverage_xml} not found. Produce it with "
            "`pytest -q --cov=query_doctor --cov-report=xml`."
        )
    root = ET.parse(coverage_xml).getroot()
    line_rate = root.get("line-rate")
    if line_rate is None:
        raise MeasurementError(f"{coverage_xml} has no line-rate attribute")
    return float(line_rate) * 100


def _pyproject() -> dict[str, Any]:
    """Return the parsed pyproject.toml.

    Raises:
        MeasurementError: on Python 3.10, which has no ``tomllib``. This is
            repo tooling rather than shipped code, so it states the
            requirement instead of degrading to a regex parse of TOML.
    """
    try:
        import tomllib
    except ModuleNotFoundError as exc:  # pragma: no cover - 3.10 only
        raise MeasurementError(
            "reading pyproject.toml requires tomllib (Python 3.11+); "
            "run the claims gate under 3.11 or newer"
        ) from exc

    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data: dict[str, Any] = tomllib.load(fh)
    return data


def measure_coverage_fail_under() -> int:
    """Return the coverage floor CI actually enforces."""
    return int(_pyproject()["tool"]["coverage"]["report"]["fail_under"])


def _versions_from_classifiers(prefix: str) -> list[tuple[int, int]]:
    """Return sorted (major, minor) pairs from classifiers starting with prefix."""
    found = []
    for classifier in _pyproject()["project"]["classifiers"]:
        if classifier.startswith(prefix):
            tail = classifier[len(prefix) :].strip()
            if re.fullmatch(r"\d+\.\d+", tail):
                major, minor = tail.split(".")
                found.append((int(major), int(minor)))
    return sorted(found)


def _range_label(versions: list[tuple[int, int]], what: str) -> str:
    """Render a version list as a 'low-high' label."""
    if not versions:
        raise MeasurementError(f"no {what} versions found in pyproject classifiers")
    low, high = versions[0], versions[-1]
    return f"{low[0]}.{low[1]}-{high[0]}.{high[1]}"


def measure_django_range() -> str:
    """Return the supported Django range, cross-checked against the CI matrix."""
    declared = _versions_from_classifiers("Framework :: Django ::")
    label = _range_label(declared, "Django")
    _cross_check_ci_matrix("django-version", declared, "Django")
    return label


def measure_python_range() -> str:
    """Return the supported Python range, cross-checked against the CI matrix."""
    declared = _versions_from_classifiers("Programming Language :: Python ::")
    label = _range_label(declared, "Python")
    _cross_check_ci_matrix("python-version", declared, "Python")
    return label


def _cross_check_ci_matrix(key: str, declared: list[tuple[int, int]], what: str) -> None:
    """Fail if the CI matrix does not span the same range the classifiers claim.

    A classifier is a promise; the matrix is what is actually exercised. If
    they disagree, the claim is unbacked regardless of which one is right.
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    match = re.search(rf"{key}:\s*\[(.*?)\]", ci)
    if not match:
        raise MeasurementError(f"no '{key}' matrix found in ci.yml")
    tested = sorted(
        (int(m.group(1)), int(m.group(2))) for m in re.finditer(r'"(\d+)\.(\d+)"', match.group(1))
    )
    if tested != declared:
        raise MeasurementError(
            f"{what} classifiers and the CI matrix disagree: "
            f"classifiers {declared}, ci.yml {tested}"
        )


def _gathered_files(manifest: dict[str, Any]) -> list[Path]:
    """Expand the manifest's explicit gated-file list."""
    paths: list[Path] = []
    for entry in manifest["gated_files"]:
        if "*" in entry:
            paths.extend(sorted(REPO_ROOT.glob(entry)))
        else:
            paths.append(REPO_ROOT / entry)
    return [p for p in paths if p.is_file()]


def check_prose_rules(manifest: dict[str, Any]) -> list[str]:
    """Apply the build-time and dated-status rules to the gated files."""
    violations: list[str] = []
    rules = manifest["prose_rules"]
    build_patterns = [re.compile(p, re.IGNORECASE) for p in rules["build_time"]["patterns"]]
    status_words = [w.lower() for w in rules["dated_status"]["status_words"]]
    provenance = [m.lower() for m in rules["dated_status"]["provenance_markers"]]
    date_re = re.compile(r"\b20\d\d-\d\d-\d\d\b")

    for path in _gathered_files(manifest):
        relpath = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in build_patterns:
                if pattern.search(line):
                    violations.append(
                        f"{relpath}:{lineno}: build duration quoted as a fact "
                        f"(matched /{pattern.pattern}/)"
                    )
                    break  # one report per line; the patterns overlap by design
            lowered = line.lower()
            if (
                date_re.search(line)
                and any(w in lowered for w in status_words)
                and not any(m in lowered for m in provenance)
            ):
                violations.append(
                    f"{relpath}:{lineno}: dated status claim -- rots without an edit; "
                    f"state the status by reference instead"
                )
    return violations


def check_claims(manifest: dict[str, Any], coverage_xml: Path) -> tuple[list[str], list[str]]:
    """Check every manifest row against its measurement.

    Returns:
        A ``(violations, deferrals)`` pair. Deferrals are rows whose surface
        cannot be corrected from here and that carry an explicit ``deferred``
        block; they are reported on every run, including clean ones, so a
        deferral cannot become a hiding place.
    """
    violations: list[str] = []
    deferrals: list[str] = []
    measurements: dict[str, Any] = {}

    def measured(name: str) -> Any:
        if name not in measurements:
            if name == "coverage_percent":
                measurements[name] = measure_coverage_percent(coverage_xml)
            else:
                measurements[name] = globals()[f"measure_{name}"]()
        return measurements[name]

    for claim in manifest["claims"]:
        deferred = claim.get("deferred")
        if deferred is not None:
            missing = [f for f in ("reason", "action") if not deferred.get(f)]
            if missing:
                violations.append(
                    f"{claim['id']}: deferred row is missing {', '.join(missing)}. "
                    f"A deferral without a reason and a named action is where a claim hides."
                )
                continue

        try:
            actual = measured(claim["measurement"])
        except MeasurementError as exc:
            violations.append(f"{claim['id']}: measurement failed: {exc}")
            continue

        if claim["surface_kind"] == "repo":
            path = REPO_ROOT / claim["surface"]
            if not path.exists():
                violations.append(f"{claim['id']}: surface {claim['surface']} does not exist")
                continue
            if claim["locator"] not in path.read_text(encoding="utf-8"):
                violations.append(
                    f"{claim['id']}: locator not found in {claim['surface']} -- "
                    f"the claim was reworded or removed and this row is now checking nothing: "
                    f"{claim['locator']!r}"
                )
                continue

        expected = claim["value"]
        if claim["kind"] == "exact":
            disagrees = str(expected) != str(actual)
        elif claim["kind"] == "floor":
            disagrees = float(expected) > float(actual)
        else:
            violations.append(f"{claim['id']}: unknown kind {claim['kind']!r}")
            continue

        if not disagrees:
            if deferred is not None:
                violations.append(
                    f"{claim['id']}: row is marked deferred but now agrees with the tree "
                    f"({actual!r}). Remove the deferral."
                )
            continue

        message = (
            f"{claim['id']}: {claim['surface']} claims {expected!r}, tree measures {actual!r}"
        )
        if deferred is None:
            violations.append(message)
        else:
            deferrals.append(
                f"{message}\n"
                f"      reason: {deferred['reason']}\n"
                f"      action: {deferred['action']}"
            )

    return violations, deferrals


def main() -> int:
    """Run the claims gate; return 0 when clean, 1 when any claim disagrees."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        default=REPO_ROOT / "coverage.xml",
        help="coverage XML report to read the coverage percentage from",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    violations, deferrals = check_claims(manifest, args.coverage_xml)
    violations += check_prose_rules(manifest)

    if deferrals:
        print(f"Claims gate: {len(deferrals)} deferred row(s), reported every run:\n")
        for deferral in deferrals:
            print(f"  {deferral}\n")

    if violations:
        print(f"Claims gate: {len(violations)} violation(s).\n")
        for violation in violations:
            print(f"  {violation}")
        return 1

    print(f"Claims gate: clean ({len(manifest['claims'])} claims checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
