## Summary

<!-- What does this PR do, and why? Link an issue if one exists. -->

## Type

<!-- Pick one -->
- [ ] fix
- [ ] feat
- [ ] docs
- [ ] chore
- [ ] breaking

## Changelog entry

<!--
Exact line(s) to add under `## [Unreleased]` in CHANGELOG.md, e.g.:

### Fixed
- `fix_queries --apply` no longer writes syntactically invalid code for
  N+1/fat_select prescriptions; unsafe fix types are now skipped and
  reported instead of applied.
-->

## Testing

<!-- What did you run, and what passed? e.g. `pytest`, `ruff check`, `mypy`, `mkdocs build --strict` -->

## Checklist

- [ ] Tests added/updated for the behavior change
- [ ] `ruff check src/ tests/` clean
- [ ] `ruff format src/ tests/ --check` clean
- [ ] `mypy src/query_doctor/` clean
- [ ] `mkdocs build --strict` passes (if docs changed)
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`
- [ ] No direct commits to `main` — this PR targets `main` from a `feat/*`/`fix/*`/`docs/*`/`chore/*` branch
