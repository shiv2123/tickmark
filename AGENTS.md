# AGENTS.md — operating rules for AI assistants in this repository

> Read by Claude Code / Cowork and by Codex. Read this first, before any other file.

## What this is

Tickmark is a GitHub Action that evaluates a pull request against a declarative change-management
policy and emits structured, ITGC-style control evidence: what changed, which control applies, what
evidence supports the conclusion, and a verdict with reasoning.

**What it is not**, and these are load-bearing distinctions:

- Not a linter. It does not evaluate code quality.
- Not a code reviewer. It does not suggest changes.
- Not a generic "AI reviews your PR" tool. Those exist in abundance and this is not one.

The differentiator is **control evidence output**. If a proposed feature does not produce or improve
control evidence, it does not belong here.

## Read these before working

1. `docs/technical-design.md` — schemas, contracts, command surface. Tier 1 decisions.
2. `docs/adr/` — why things are the way they are, and what was rejected.
3. `CONTRIBUTING.md` — branch, commit, and PR conventions.
4. `eval/PROTOCOL.md` once it exists — binding, not advisory.

## Hard rules

### 1. Never generate evaluation labels

**This is the most important rule in the repository.**

The quantity being measured is agreement with *human* judgment. If a model produces the verdicts and
a model produces the ground truth, the measured false-positive rate is the agreement between two
model calls, it trends to zero by construction, and it measures nothing.

- Deterministic ground truth comes from the GitHub API.
- Mutation ground truth is true by construction.
- Judgment ground truth is hand-labeled by Shiv, blind, before any prompt tuning.

Do not offer to label. Do not pre-fill labels. Do not "suggest" labels for review. See ADR 0004.

### 2. Checks are pure functions

No network, no clock, no filesystem, no randomness inside a check. Input is the evidence bundle plus
validated params; output is fully determined. This is what makes deterministic assertions unit-testable
rather than statistically evaluable.

Precompute anything expensive into `bundle.derived` at collection time instead.

### 3. Evidence records are append-only

A re-run emits a new record with a new `record_id`. Never mutate an existing record. The Evidence
Register depends on this and audit evidence requires it.

### 4. Never widen a judgment assertion's evidence scope to make a case pass

If an assertion fails on a case you think it should pass, the fix is the guidance text, the control
wording, or accepting that the case is genuinely ambiguous. Adding fields to `evidence` so the model
can find a way to pass is overfitting to the corpus, and it silently invalidates the number.

### 5. Unknown means unknown

`INDETERMINATE` is a real verdict, not a failure to decide. Never resolve uncertainty by defaulting to
PASS or FAIL. A judgment assertion that cannot cite specific evidence for a FAIL is coerced to
INDETERMINATE, always.

### 6. Never silently degrade

If branch protection could not be read, if the token was read-only, if inference was skipped on a fork
PR, say so in `notices` and in the record. A weaker verdict that looks complete is worse than no
verdict.

### 7. Do not fabricate project history

Commits are dated when they happen. No backdating, no synthetic history, no manufactured evidence of
authorship. This project's entire value is that it is verifiable.

## Working conventions

- Conventional commits: `feat(scope):`, `fix(scope):`, `test:`, `docs:`, `refactor:`, `eval:`.
- One branch per unit of work, PR into `main`, description answers what changed, why this approach,
  and how it was verified.
- `make test` passes before merge. A bug fix requires a test that failed before the fix.
- A change that could move a published number re-runs the eval and updates the README **in the same
  PR**. A stale number in the README is a false claim.
- Schema changes require a `schema_version` bump and a migration note in the PR.
- Never commit `.env`, API keys, or eval cache. Checkpoints and labels **are** committed; they are the
  record.

## Scope discipline

v1 is five controls, ten assertions, three of which are judgment. That count is set by the labeling
budget, not by coverage ambition — every judgment assertion added multiplies the human cost of the
eval.

The "not in v1" list in the project spec is binding. If a change would add a control, integrate a
ticketing system, add a dashboard, support another forge, or sign records, it is out of scope for v1
regardless of how good the idea is.

## On AI assistance

This project is built with AI assistance and says so plainly in the README. The engineering judgment,
control definitions, eval protocol, and labels are human. The code largely is not. Do not obscure
this, and do not overstate it in either direction.
