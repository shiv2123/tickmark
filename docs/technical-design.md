# Tickmark — Technical Design

**Status:** Tier 1 decisions. These are expensive to change later; everything else can be decided while coding.
**Date:** 2026-08-05
**Companion to:** `projects/tickmark-v1-spec.md`

Covers: evidence bundle schema · evidence record schema · check registry contract · policy validation ·
the command surface and overnight automation.

---

## 1. Evidence bundle

The canonical, normalized view of a pull request. Everything downstream depends on it: the digest
hashes it, the eval corpus stores it, mutations operate on it, the cache keys on it, and judgment
assertions read scoped subsets of it.

**Change this after the corpus is frozen and the corpus is invalid.** Get it right now.

### Normalization rules (these *are* the determinism guarantee)

1. Object keys sorted lexicographically at every level.
2. Arrays sorted by a declared stable key (`files` by path, `reviews` by `submitted_at` then `id`,
   `commits` by `authored_at` then `sha`).
3. Timestamps ISO-8601 UTC with `Z`, second precision. No local times, no relative times.
4. Identities are **numeric GitHub user IDs plus a role flag**, never display names or logins.
   Display names change and models reason about them.
5. Diffs truncated deterministically: files sorted by path, first `max_diff_lines_per_file` (default
   200) lines of each patch, with an explicit `truncated: true` marker.
6. Nothing volatile that is not control-relevant. No `updated_at` on the PR, no star counts, no
   ETags.
7. Serialized as JSON with `sort_keys=True, separators=(',', ':')`, UTF-8, no trailing newline,
   before hashing.

### Schema

```jsonc
{
  "schema_version": "1.1",
  "source": {
    "host": "github.com",
    "repo_id": 1324509884,
    "repo": "shiv2123/tickmark",
    "pr_number": 42,
    "head_sha": "a1b2c3d4...",
    "base_sha": "e5f6a7b8...",
    "merge_sha": null,                    // null while open
    "base_ref": "main",
    "is_fork": false,
    "collected_at": "2026-08-05T22:14:00Z" // NOT hashed; see §2 excluded_from_digest
  },

  "pr": {
    "title": "Add stale-approval check to CM-2",
    "body": "...",                         // verbatim, unmodified
    "body_length": 412,
    "state": "merged",
    "draft": false,
    "created_at": "2026-08-03T14:02:00Z",
    "merged_at": "2026-08-04T09:31:00Z",
    "author": { "id": 48875091, "type": "User", "is_bot": false },
    "labels": ["enhancement"],             // sorted
    "milestone": null
  },

  "commits": [                             // sorted by authored_at, then sha
    {
      "sha": "c0ffee1...",
      "sequence": 0,                       // position GitHub returned it in
      "parents": ["e5f6a7b8..."],          // NOT sorted; parent order is semantic
      "authored_at": "2026-08-03T13:50:00Z",
      "committed_at": "2026-08-03T13:50:00Z",
      "author_id": 48875091,
      "committer_id": 48875091,
      "co_author_ids": [1234567],          // parsed from Co-authored-by: trailers
      "message_subject": "feat(engine): add stale-approval check",
      "message_body": "...",
      "verified": true
    }
  ],

  "files": [                               // sorted by path
    {
      "path": "src/tickmark/checks/cm2.py",
      "status": "added",                   // added|modified|removed|renamed
      "previous_path": null,
      "additions": 84,
      "deletions": 0,
      "is_rename_only": false,             // computed: rename with zero net change
      "patch": "@@ -0,0 +1,84 @@\n...",
      "patch_truncated": false
    }
  ],

  "reviews": [                             // sorted by submitted_at, then id
    {
      "id": 998877,
      "reviewer_id": 7654321,
      "reviewer_is_bot": false,
      "state": "APPROVED",                 // APPROVED|CHANGES_REQUESTED|COMMENTED|DISMISSED
      "submitted_at": "2026-08-04T08:12:00Z",
      "dismissed_at": null,
      "commit_sha": "c0ffee1..."           // the SHA the review was submitted against
    }
  ],

  "checks": [                              // sorted by name, source, completed_at, id
    {
      "id": 5001,                          // re-runs repeat the name; the id does not
      "name": "test",
      "status": "completed",
      "conclusion": "success",             // success|failure|neutral|cancelled|skipped|timed_out
      "head_sha": "a1b2c3d4...",
      "completed_at": "2026-08-03T14:20:00Z"
    }
  ],

  "linked_issues": [                       // sorted by number
    {
      "number": 17,
      "title": "CM-2 should reject co-authored approvals",
      "body": "...",
      "state": "closed",
      "state_reason": "completed",         // completed|not_planned|reopened
      "link_source": "body_keyword"        // body_keyword|timeline|branch_name
    }
  ],

  "comments": [                            // issue comments only; sorted by created_at
    {
      "id": 5544332,
      "author_id": 48875091,
      "author_is_bot": false,
      "created_at": "2026-08-04T09:00:00Z",
      "body": "tickmark: waive CM-3 — generated protobuf, no tests apply"
    }
  ],

  "repo_config": {
    "default_branch": "main",
    "branch_protection": {
      "available": true,                   // false when the token lacks admin scope
      "required_approving_review_count": 1,
      "dismiss_stale_reviews": true,
      "required_status_checks": ["build", "test"]
    },
    "has_codeowners": true
  },

  "derived": {                             // computed once, so checks stay pure and cheap
    "is_revert": false,
    "author_and_co_author_ids": [48875091],
    "commit_shas_in_order": ["c0ffee1..."],// branch order, recovered from `sequence`
    "commit_order_verified": true,         // the parent chain checked out
    "head_commit_sha": "c0ffee1...",
    "last_commit_at": "2026-08-03T13:50:00Z",   // committer date
    "last_authored_at": "2026-08-03T13:50:00Z", // author date
    "production_paths_touched": ["src/tickmark/checks/cm2.py"],
    "test_paths_touched": ["tests/test_cm2.py"],
    "all_files_exempt": false,
    "work_item_refs": ["OPS-1421"]         // sorted, deduplicated
  }
}
```

### Field-level notes

- **`derived`** exists so check functions are pure predicates over precomputed facts rather than
  re-parsing diffs. It is part of the hashed bundle, which means derivation logic is versioned by
  `engine_version` — changing it correctly invalidates the cache.
- **`reviews[].commit_sha`** is what makes the stale-approval check possible. It requires the
  timeline API in some cases; the reviews endpoint alone is not always sufficient.
- **`branch_protection.available`** is explicit rather than implied by absence. A missing value
  because the token lacked scope is a different fact from a repo with no protection, and conflating
  them produces false findings.
- **`comments`** carries waivers. Review comments are deliberately excluded: too noisy, and a waiver
  should be a deliberate top-level act.
- **`commits[].sequence` and `commits[].parents`** exist because rule 2 sorts the array by
  `authored_at`, which destroys branch order — and branch order is what makes staleness answerable
  without trusting clocks. `sequence` carries the order; `parents` lets it be *verified* rather than
  believed. When the chain does not walk (force-push, absent parents), `derived.commit_order_verified`
  is false and any check depending on it reports INDETERMINATE.
- **`checks[].id`** because a re-run produces a second check run with the same name for the same SHA.
  Without it, "the current result for this check" has no answer, and the two entries tie in the sort.

### Schema history

**1.1** — added `commits[].sequence`, `commits[].parents`, `checks[].id`. Replaced
`derived.last_production_commit_at` with `commit_shas_in_order`, `commit_order_verified`,
`head_commit_sha`, `last_commit_at`, and `last_authored_at`. The old field took the production path
list, never applied it, and returned `max(authored_at)`: the name claimed a scoping that did not
happen, and author dates survive rebase. Array sorts now use the item's canonical form as a final
tiebreak, so ordering is a function of contents rather than of API response order. No migration path
— nothing consumed 1.0 outside this repository, and the eval corpus is not yet frozen.

---

## 2. The digest

```
evidence_digest = sha256(
    canonical_json(bundle minus excluded_from_digest)
  ‖ policy_digest
  ‖ engine_version
  ‖ model_pin            // "none" in deterministic-only mode
  ‖ prompt_version
)
```

**`excluded_from_digest`:** `source.collected_at` only. Everything else is control-relevant and must
change the digest when it changes.

`prompt_version` is in the digest deliberately. Editing a prompt during tuning *should* invalidate the
cache, or you would be measuring a stale prompt.

---

## 3. Evidence record (the published output)

This is the artifact users download, the Register ingests, and the eval compares against. It is
**append-only**: a re-run emits a new record with a new `record_id` and never mutates an existing one.

```jsonc
{
  "schema_version": "1.0",
  "record_id": "sha256:9f2a...",           // == evidence_digest
  "generated_at": "2026-08-05T22:14:03Z",

  "subject": {
    "host": "github.com", "repo": "shiv2123/tickmark", "repo_id": 1324509884,
    "pr_number": 42, "head_sha": "a1b2c3d4...", "merge_sha": null,
    "pr_url": "https://github.com/shiv2123/tickmark/pull/42"
  },

  "policy": {
    "name": "Standard Change Management",
    "revision": 3,
    "digest": "sha256:44bc...",
    "source_path": ".tickmark/policy.yml"
  },

  "engine": {
    "version": "0.1.0",
    "mode": "observe",                     // observe|advise|enforce
    "inference": "local",                  // local|hosted|skipped_no_key|skipped_fork_context
    "model_pin": "qwen3:8b-q4_K_M@sha256:1a2b...",
    "prompt_version": "3",
    "quorum_n": 3
  },

  "summary": {
    "pass": 3, "fail": 1, "indeterminate": 1, "not_applicable": 0,
    "overall": "fail"                      // worst non-NA verdict
  },

  "controls": [
    {
      "id": "CM-2",
      "title": "Segregation of Duties",
      "severity": "critical",
      "references": [
        { "framework": "SOX ITGC", "domain": "Change Management" },
        { "framework": "SOC 2", "criterion": "CC8.1" }
      ],
      "verdict": "fail",
      "assertions": [
        {
          "id": "A1",
          "type": "deterministic",
          "statement": "At least 1 approving review from a non-author, non-co-author.",
          "verdict": "fail",
          "check": "independent_approval_count",
          "observed": { "independent_approvals": 0, "total_approvals": 1,
                        "excluded_reason": "approver_is_co_author" },
          "evidence_refs": ["reviews[0]", "commits[2].co_author_ids"]
        },
        {
          "id": "A2",
          "type": "deterministic",
          "statement": "No commit landed after the commit the approval was submitted against.",
          "verdict": "pass",
          "check": "approval_not_stale",
          "observed": { "approved_sha": "c0ffee1...", "head_commit_sha": "c0ffee1...",
                        "commits_after_approval": 0, "commit_order_verified": true },
          "evidence_refs": ["reviews[0].commit_sha", "derived.commit_shas_in_order"]
        }
      ]
    },
    {
      "id": "CM-4",
      "verdict": "indeterminate",
      "assertions": [
        {
          "id": "A1",
          "type": "judgment",
          "statement": "The record conveys scope, risk, and how the change would be backed out.",
          "verdict": "indeterminate",
          "advisory": true,
          "evidence_scope": ["pr_title", "pr_body", "labels", "changed_file_paths"],
          "quorum": { "n": 3, "votes": ["pass", "fail", "pass"], "unanimous": false },
          "evidence_refs": [],
          "reasoning": "Scope is clear; no backout path is stated. Samples disagreed on whether the feature-flag mention is sufficient.",
          "model": "qwen3:8b-q4_K_M@sha256:1a2b..."
        }
      ]
    }
  ],

  "waivers": [
    {
      "control_id": "CM-3", "assertion_id": "A2",
      "approver_id": 7654321, "approved_at": "2026-08-04T09:00:00Z",
      "reason": "generated protobuf, no tests apply",
      "source_ref": "comments[0]"
    }
  ],

  "notices": [
    { "level": "warn", "code": "branch_protection_unavailable",
      "message": "Token lacks admin scope; branch protection was not read." }
  ]
}
```

### Rules that must not be violated

- **Append-only.** Never mutate a record. The Register depends on this.
- **`evidence_refs` uses JSON-pointer-ish paths into the bundle**, so a reader can trace any verdict
  back to the exact fact that produced it. This is the difference between evidence and an opinion.
- **A `fail` on a judgment assertion requires non-empty `evidence_refs`.** Enforced in code; a
  violation coerces to `indeterminate`. See ADR 0003.
- **`waivers` are recorded, never applied by deletion.** A waived control keeps its verdict; the
  waiver sits alongside it.
- **`notices`** surface degraded collection explicitly. Silent degradation is the failure mode that
  turns a compliance tool into a liability.

---

## 4. Check registry contract

Policy files reference checks by name. Names bind to registered pure functions.

```python
@check("independent_approval_count")
@params(exclude_co_authors=bool, exclude_bots=bool, min_approvals=int)
def independent_approval_count(bundle: Bundle, p: Params) -> CheckResult:
    """Returns CheckResult(verdict, observed: dict, evidence_refs: list[str])."""
```

Contract:

- **Pure.** No network, no clock, no filesystem, no randomness. Input is the bundle and params;
  output is fully determined. This is what makes deterministic assertions testable rather than
  evaluable (ADR 0004).
- **Every result carries `observed`** — the specific numbers behind the verdict. Never a bare
  boolean. `observed` is what renders in the comment and what makes a finding arguable.
- **Unknown check name is a hard load error**, never a skipped control. Silently ignoring an
  unrecognized check would let a policy claim coverage it does not have, which is the worst possible
  failure for this tool.
- **Params are validated at policy load**, not at evaluation. A typo fails fast with a line number.
- Checks may return `not_applicable`, which is distinct from `pass`.

---

## 5. Policy validation

JSON Schema at `src/tickmark/schemas/policy-v1.json`, validated on load.

- `apiVersion` must be `tickmark/v1`; unknown versions fail with an upgrade message.
- Unknown top-level keys are an **error**, not a warning. Typos in a compliance policy should not be
  silently tolerated.
- Every `check:` name must exist in the registry.
- Every judgment assertion must declare non-empty `evidence`, and every declared field must be a
  known bundle path.
- Errors report YAML line and column. A compliance person editing this file will make mistakes and
  deserves a real error message.
- `tickmark validate-policy` runs this standalone, so it can be its own CI step.

---

## 6. Command surface and overnight automation

Design goal: **one command per intention, resumable, never needs babysitting.**

```
make setup            # venv, deps, pull the pinned Ollama model, verify it responds
make test             # pytest. Must pass before merge.
make check PR=42      # run the engine against one real PR, print the comment locally

make mine             # build the corpus from the published selection criteria
make label            # blind labeling UI  (see below)
make mutate           # generate stratum B from frozen stratum A

make eval             # dev set, foreground, live progress
make eval-overnight   # everything, caffeinated, checkpointed, notifies on completion
make eval-holdout     # the held-out set. Refuses to run more than twice. (see below)

make report           # regenerate results tables and the README block from eval/results/
```

### `make eval-overnight`

```
python -m tickmark.eval run --all --resume --checkpoint-every 1 --pace 0.5
```

**No `caffeinate`.** Sleep is controlled deliberately in System Settings rather than by the runner,
because the machine is a 16GB M1 Pro laptop doing hours of sustained inference and the operator
should be the one deciding when it stays awake. Set *Lock Screen → Turn display off when inactive →
Never* while plugged in, run with the lid open on a cooling pad, and unset it afterwards.

- **`--pace <seconds>`** inserts a gap between calls. Default 0.5s. This costs wall-clock time and
  buys thermal headroom, which on a passively-stressed laptop chassis is the right trade. Raise it if
  the fans get unpleasant; the run is resumable either way so there is no penalty for stopping.
- **Checkpoints after every call** to `eval/.state/run-<id>.jsonl`. Kill it, sleep the laptop, close
  the lid — `--resume` continues from the exact call it stopped on.
- **Disk cache** at `eval/.cache/<digest>-<prompt_hash>.json`. Re-runs of unchanged work cost nothing.
  Cache is gitignored; checkpoints are not.
- **Progress** to `eval/.state/run-<id>.log`, one line per call. `tail -f` if curious.
- **On completion:** writes `eval/results/<date>-<arm>.json`, regenerates the markdown summary with
  Wilson intervals, and fires `osascript -e 'display notification'`.
- **Estimated wall time printed up front**, so you know before you start whether it's a two-hour or
  a nine-hour run.
- **Fails safe:** if Ollama dies mid-run, it checkpoints, waits, retries with backoff, and only gives
  up after a configurable ceiling. It never loses completed work.

### `make label`

Serves a single-file local page on `127.0.0.1`. One case per screen: PR title, body rendered as
markdown, file list, linked issues — only the fields the assertion is scoped to see.

- Keyboard only: `1` pass, `2` fail, `3` unclear, `u` undo, `?` show the guidance text.
- Auto-saves every verdict to `eval/labels/<stratum>.jsonl` immediately. Closing the tab loses
  nothing.
- Progress bar with a running estimate of time remaining.
- **Never displays the engine's verdict.** Enforced by the server refusing to load engine output in
  labeling mode, not by convention. ADR 0004 rule 3.
- **Second-pass mode** (`make label PASS=2`) reshuffles a random 20% for the Cohen's κ measurement
  and hides all first-pass labels.

### `make eval-holdout`

The held-out set may be evaluated **twice**: once for the baseline, once for the final. The command
enforces this rather than trusting discipline.

- Reads `eval/.holdout-runs.json`, which is committed to git.
- A third invocation refuses and prints the two prior run dates and their commit SHAs.
- Overriding requires `--i-am-breaking-the-protocol`, which writes a loud disclosure line into
  `eval/results/` that surfaces in the README.

Making the protocol violation *possible but permanently visible* is better than making it impossible.
A locked door invites working around it; a tripwire that writes to the published record does not.

---

## 7. Repository conventions (`AGENTS.md`)

The tickmark repo gets its own `AGENTS.md`, read by Claude and Codex at the start of every session,
covering:

- What the project is, and the three things it is explicitly not (linter, code reviewer, generic AI PR
  reviewer)
- **Never generate eval labels.** The single most important rule in the file, with the reason: the
  measured quantity is agreement with human judgment, so model-generated labels make the headline
  number circular. See ADR 0004.
- Checks are pure functions. No network, clock, filesystem, or randomness inside a check.
- Never mutate an evidence record; emit a new one.
- Never widen a judgment assertion's `evidence` scope to make a case pass. That is overfitting to the
  corpus.
- Conventional commits; branch per unit of work; `make test` before merge.
- If a change could move a published number, re-run the eval and update the README in the same PR.
- Schema changes require a `schema_version` bump and a migration note.

---

## 8. What is deliberately still undecided

Module layout, function signatures, internal naming, the exact comment markdown, retry/backoff
constants, and the CI matrix. All cheap to change, all better decided while writing the code than in
advance. See spec §Tier 3.
