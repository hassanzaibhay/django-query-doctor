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
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

FETCH_TIMEOUT_SECONDS = 30

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "claims.json"
ANALYZERS_DIR = REPO_ROOT / "src" / "query_doctor" / "analyzers"

# Modules in analyzers/ that are infrastructure, not analyzers. Counting them
# is how "8 analyzers" would come back.
_NON_ANALYZER_MODULES = {"__init__", "base", "discovery"}


class MeasurementError(RuntimeError):
    """A measurement could not be taken, so its claims cannot be checked."""


class SurfaceError(RuntimeError):
    """A published surface could not be retrieved, so its claim cannot be checked."""


_FETCH_CACHE: dict[str, str] = {}


def fetch_surface(url: str) -> str:
    """Retrieve a published surface over HTTP.

    Cached per URL for the run, so rows sharing a surface cost one request.

    ``Cache-Control``/``Pragma: no-cache`` are sent deliberately, not as a
    precaution: ``raw.githubusercontent.com`` is CDN-served, and reading a
    stale copy of a claim surface is a documented trap on this project. A
    stale hit is a false green, or -- worse -- a false red immediately after
    a legitimate surface edit, where the remedy is "wait", which teaches
    everyone to ignore the gate.

    Raises:
        SurfaceError: on any failure. There is no skip path; a gate that
            drops a row on a network blip reports green for the wrong reason.
    """
    if url in _FETCH_CACHE:
        return _FETCH_CACHE[url]

    request = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise SurfaceError(f"{url} returned HTTP {response.status}")
            body: str = response.read().decode("utf-8")
    except SurfaceError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise SurfaceError(f"could not fetch {url}: {exc}") from exc

    _FETCH_CACHE[url] = body
    return body


def measure_analyzer_count() -> int:
    """Count analyzer modules on disk, excluding infrastructure."""
    return len([p for p in ANALYZERS_DIR.glob("*.py") if p.stem not in _NON_ANALYZER_MODULES])


def measure_test_count() -> int:
    """Return the number of tests pytest collects.

    A non-zero exit is a failed measurement, not a number to salvage. Without
    that check, a run that errors during collection still emits a parseable
    line -- and the regex below takes the *denominator* of
    ``811/812 tests collected (1 error)``, so a broken collection would
    silently yield an inflated count.

    The denominator is nonetheless the right capture: under deselection
    (``-k``/``-m``, which exits 0) pytest emits ``N/M tests collected`` where
    ``M`` is the total. Do not "fix" this into capturing ``N``.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if proc.returncode != 0:
        raise MeasurementError(
            f"pytest collection exited {proc.returncode}; the count cannot be trusted.\n"
            f"--- stdout tail ---\n{proc.stdout[-1500:]}\n"
            f"--- stderr tail ---\n{proc.stderr[-1500:]}"
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


def measure_followups_open() -> int:
    """Count open entries in FOLLOWUPS.md.

    open = headings - tombstones - fully-resolved entries.

    - **heading** -- ``## <n>. <title>``. A *reserved* number has no heading at
      all (25 is reserved for the phase-1 disposition and unwritten), so a
      reservation can never inflate the count.
    - **tombstone** -- a heading whose title says ``merged into entry``. Kept so
      a number is not silently reused; excluded from the count, so a tombstone
      cannot inflate it either.
    - **resolved** -- the body carries a ``- **Resolved:**`` line.
      ``- **Resolved (partial):**`` does NOT count, which is why entry 12 --
      whose legacy-Windows half is still open -- remains open.
    """
    text = (REPO_ROOT / "FOLLOWUPS.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (\d+)\. (.+)$", text, re.M)
    bodies = re.split(r"^## \d+\. ", text, flags=re.M)[1:]

    open_count = 0
    for (_, title), body in zip(headings, bodies, strict=True):
        if "merged into entry" in title:
            continue
        if re.search(r"^- \*\*Resolved:\*\*", body, re.M):
            continue
        open_count += 1
    return open_count


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


def _provenance_pattern(markers: list[str]) -> re.Pattern[str]:
    """Build the anchored provenance pattern from the manifest's markers.

    Provenance means the marker *introduces* the date: marker, an optional
    connector, separators, then the date. Anchoring on that relationship is
    why there is no character-distance window here -- a distance constant is
    a tunable with no principle behind it, and a whole-line substring test
    (the previous implementation) exempts any line merely containing the word
    "measured" anywhere, including in an unrelated clause.

    If a real provenance line fails to match, extend the connector group.
    Do not reintroduce a distance window.
    """
    alternation = "|".join(re.escape(m) for m in markers)
    return re.compile(
        rf"(?:{alternation})(?:\s+(?:on|in|at))?[\s,:—-]*20\d\d-\d\d-\d\d",
        re.IGNORECASE,
    )


def check_prose_rules(manifest: dict[str, Any]) -> list[str]:
    """Apply the build-time and dated-status rules to the gated files."""
    violations: list[str] = []
    rules = manifest["prose_rules"]
    build_patterns = [re.compile(p, re.IGNORECASE) for p in rules["build_time"]["patterns"]]
    status_words = [w.lower() for w in rules["dated_status"]["status_words"]]
    provenance_re = _provenance_pattern(rules["dated_status"]["provenance_markers"])
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
                and not provenance_re.search(line)
            ):
                violations.append(
                    f"{relpath}:{lineno}: dated status claim -- rots without an edit; "
                    f"state the status by reference instead"
                )
    return violations


def _surface_text(claim: dict[str, Any]) -> str | None:
    """Return the surface's contents, or None when it cannot be read at all.

    One path for every kind, so the verbatim-locator rule below applies
    wherever a surface exists. ``external`` is the only kind that yields
    None, and that is exactly what makes it unverifiable.

    Raises:
        SurfaceError: when a surface that *should* be readable is not.
    """
    kind = claim["surface_kind"]
    if kind == "repo":
        path = REPO_ROOT / str(claim["surface"])
        if not path.exists():
            raise SurfaceError(f"surface {claim['surface']} does not exist")
        text: str = path.read_text(encoding="utf-8")
        return text
    if kind == "fetched":
        url = claim.get("url")
        if not url:
            raise SurfaceError(
                "surface_kind 'fetched' requires a 'url' field. Without it the row "
                "checks nothing but its own recorded value."
            )
        return fetch_surface(url)
    if kind == "external":
        return None
    raise SurfaceError(f"unknown surface_kind {kind!r}")


def check_claims(
    manifest: dict[str, Any], coverage_xml: Path
) -> tuple[list[str], list[str], list[str]]:
    """Check every manifest row against its measurement.

    Returns:
        A ``(violations, deferrals, unverified)`` triple. Deferrals are rows
        that currently disagree and cannot be corrected from here. Unverified
        are ``external`` rows without a deferral -- surfaces the gate cannot
        read at all. Both are reported on every run, including clean ones, so
        neither can become a hiding place, and each row appears under exactly
        one heading: a deferred row's actionable state is the informative one.
    """
    violations: list[str] = []
    deferrals: list[str] = []
    unverified: list[str] = []
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

        # `external` is the only kind whose surface is never read, so it is the
        # only kind that can silently check nothing. It must say why, and it is
        # reported on every run. This is deliberately NOT a deferral
        # requirement: unverifiable is permanent and definitional to the kind,
        # while deferred is temporary and self-cancelling, so requiring both
        # would leave an agreeing external row with no legal state.
        if claim["surface_kind"] == "external" and not claim.get("unverifiable_reason"):
            violations.append(
                f"{claim['id']}: surface_kind 'external' requires 'unverifiable_reason' "
                f"stating why the surface can be neither fetched nor corrected from a commit."
            )
            continue

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

        try:
            surface_text = _surface_text(claim)
        except SurfaceError as exc:
            violations.append(f"{claim['id']}: {exc}")
            continue

        if surface_text is not None and claim["locator"] not in surface_text:
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

        if claim["surface_kind"] == "external" and deferred is None:
            unverified.append(
                f"{claim['id']}: {claim['surface']} -- recorded {expected!r}, "
                f"tree measures {actual!r}; surface not read\n"
                f"      why: {claim['unverifiable_reason']}"
            )

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

    return violations, deferrals, unverified


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
    violations, deferrals, unverified = check_claims(manifest, args.coverage_xml)
    violations += check_prose_rules(manifest)

    if unverified:
        print(f"Claims gate: {len(unverified)} unverified row(s), reported every run:\n")
        for row in unverified:
            print(f"  {row}\n")

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
