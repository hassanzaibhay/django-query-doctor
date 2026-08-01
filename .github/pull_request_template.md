## Summary
<!-- What does this PR do, and why? Link an issue if one exists. -->

## Type
<!-- Check the primary type. -->
- [ ] fix
- [ ] feat
- [ ] docs
- [ ] test
- [ ] refactor
- [ ] chore

## Breaking change?
- [ ] Yes -- requires a major version bump and a migration note in CHANGELOG
- [ ] No

## Changelog entry
<!--
Exact line(s) to add under `## [Unreleased]` in CHANGELOG.md, e.g.:
### Fixed
- Short description of the user-facing change.

Only user-facing changes get an entry: something a person who runs
`pip install django-query-doctor` could act on. Changes to this repository's
own development process (CI, hooks, PR templates, contributor docs) get none.
Write "none, not user-facing" here instead. See CONTRIBUTING.md#changelog.
-->

## Testing
<!-- What did you run, and what passed? e.g. `pytest`, `ruff check`, `mypy`, `mkdocs build --strict` -->

## Checklist
- [ ] Tests added/updated for the behavior change
- [ ] `ruff check src/ tests/ scripts/` clean
- [ ] `ruff format src/ tests/ scripts/ --check` clean
- [ ] `mypy src/query_doctor/ scripts/` clean
- [ ] `mkdocs build --strict` passes (if docs changed)
- [ ] `python -m scripts.docs_truth_sweep` clean
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` (user-facing changes only)
