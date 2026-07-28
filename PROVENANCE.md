# Provenance

One row per merged pull request: **PR number → head SHA → squash commit**, with the
release step it belongs to and the date the squash landed.

Squash-merging destroys the mapping between what was reviewed and what was merged.
The squash commit's tree matches the branch tip, but its SHA does not, and its
parent is `main` rather than the branch. Once the branch ref is deleted, nothing in
a clone connects the two. This file is that connection, written at merge time
rather than reconstructed later.

It exists because it was needed and absent: four complete rows lived only in a
review conversation while the branches that would have backed them were being
deleted.

This file is deliberately outside every prose gate, for the same reason
`FOLLOWUPS.md` is: it records dated facts by design, and the `dated_status` rule in
`scripts/claims_check.py` rejects dated assertions about current status. Verify
before adding a repo-root file of this kind -- `claims.json` `gated_files` is an
explicit list (`README.md`, `CONTRIBUTING.md`, `UPGRADING.md`, `docs/**/*.md`) with
no repo-root glob, and `scripts/docs_truth_sweep.py:160` discovers
`docs/**/*.md` plus `README.md` only.

## Deleting a remote branch is safe. Deleting this record is not.

GitHub retains every pull request's head commit indefinitely at `refs/pull/<n>/head`,
independent of whether the branch that produced it still exists. Deleting a merged
branch therefore loses nothing; losing the PR *number* does, because the number is
the only key into that ref.

Retrieval, repeatable by anyone with fetch access:

```
git fetch origin refs/pull/<n>/head
git rev-parse FETCH_HEAD
```

Verified live rather than assumed, on a branch that no longer exists. At the time of
writing, `git ls-remote origin refs/heads/fix/discover-analyzers-cache` returns
nothing, and:

```
$ git fetch origin refs/pull/25/head
 * branch            refs/pull/25/head -> FETCH_HEAD
$ git rev-parse FETCH_HEAD
ca0a3bb9d10fc7a7e3d71ebd1749157b5e57ad0f
```

which is exactly the head SHA recorded for #25 below. The same fetch resolves
`refs/pull/23/head` to `cb460a188f8d7ce8e4eb51d9db0f304d8feab953`, likewise long
after that branch was deleted.

## Rows

| PR | head SHA | squash commit | step | squash date (UTC) | signature |
|---|---|---|---|---|---|
| [#22](https://github.com/hassanzaibhay/django-query-doctor/pull/22) | `7c7d687907ddfbc6909193c64d663a5ce32e2186` | `f3cb415dd04a7234137cbc61822848ff43ad4bd5` | S6 | 2026-07-25T14:04:54Z | verified, valid |
| [#23](https://github.com/hassanzaibhay/django-query-doctor/pull/23) | `cb460a188f8d7ce8e4eb51d9db0f304d8feab953` | `a95840c66cb9e393c9ed3914861c18fedf1b886b` | S7 | 2026-07-27T04:17:35Z | verified, valid |
| [#24](https://github.com/hassanzaibhay/django-query-doctor/pull/24) | `4be252ff46f091cf079d29154f19679dadb9db31` | `83ea816f0fd529e2c37217819d7133a4cdaf6cab` | S7 records | 2026-07-27T14:35:29Z | verified, valid |
| [#25](https://github.com/hassanzaibhay/django-query-doctor/pull/25) | `ca0a3bb9d10fc7a7e3d71ebd1749157b5e57ad0f` | `7cc3c3760a156891252bd0338b40610c6fae5ae4` | S7b | 2026-07-28T08:59:11Z | verified, valid |

Head SHAs re-fetched through `refs/pull/<n>/head` when this file was written, not
copied from a conversation. Signature column from:

```
gh api repos/hassanzaibhay/django-query-doctor/commits/<sha> --jq .commit.verification.verified
gh api repos/hassanzaibhay/django-query-doctor/commits/<sha> --jq .commit.verification.reason
```

All four returned `true` / `valid`. The #25 row was reported as
signature-unverified during review because the reviewer's API budget was exhausted
mid-check; re-run here it verifies. That distinction matters: a rate limit is a
property of the caller, never of the commit, and the row would have been wrong to
leave marked incomplete.

## Rows not yet recorded

PRs **#14-#21** predate this file. Backfilling them is **S14's scope**, not any
earlier step's -- each row costs at least one `refs/pull/<n>/head` fetch plus two
API calls, and spending that budget outside the step that owns external-surface
work would starve the work that step exists to do. The heads remain retrievable by
the method above whenever S14 gets to them; nothing is decaying in the meantime.

## Operational notes

Recorded because each of these could have caused real damage rather than
inconvenience.

1. **`gh pr checks --watch` printing `no checks reported on the '<branch>' branch`
   is not `no checks required`.** It means the workflow has not registered yet.
   Read as a green light, it merges unreviewed-by-CI code. On #25 the first
   invocation returned exactly that string and the second, moments later, watched
   22 checks to completion. Always re-invoke before concluding a PR has no checks.

2. **A `gh` call that fails client-side may have succeeded server-side.** Both #24
   and #25 hit `dial tcp 20.207.73.85:443: connectex: A connection attempt failed`
   on `gh pr create` / `gh pr merge`. A blind retry after such a failure is how a
   repository reaches a state nobody can explain. Confirm actual state first --
   `gh pr view <n> --json number,state,mergeCommit,headRefOid` -- and retry only
   against that answer. Both PRs were confirmed single-merged this way.

3. **Under PowerShell, use `gh ... --body-file`, never `--body "<multiline>"`.** A
   here-string splits across native-command arguments; `gh pr merge 25 --squash
   --subject ... --body $body` failed with `accepts at most 1 arg(s), received 7`.

4. **The `fix/discover-analyzers-cache` remote branch disappeared without an
   explicit delete.** Recorded as unexplained rather than attributed:
   `gh api repos/hassanzaibhay/django-query-doctor --jq .delete_branch_on_merge`
   returns `false`, no `gh pr merge` invocation passed `--delete-branch`, and
   `records/s7-followups` survived the same merge flow one PR earlier. Whatever the
   cause, it is the case this file was written for -- the branch is gone and the
   head is still retrievable at `refs/pull/25/head`.
