# Tickmark

**Change-management control evidence for every pull request.**

An auditor's *tickmark* is the symbol placed beside a tested figure recording that it was verified
and how. This does the same thing for pull requests: it evaluates a PR against a declarative
change-management policy and emits structured, ITGC-style control evidence — what changed, which
control applies, what evidence supports the conclusion, and a verdict with reasoning.

Maps to **SOX ITGC change management** and **SOC 2 CC8.1**.

> **Status: early.** The evidence collector works; control evaluation is not wired up yet.
> Not usable yet. See the [milestones](https://github.com/shiv2123/tickmark/milestones) for where
> this is going.

## What it is not

- Not a linter. It does not evaluate code quality.
- Not a code reviewer. It does not suggest changes.
- Not a generic "AI reviews your PR" tool. Those exist in abundance.

The output is control evidence. That is the whole point.

## Design

Three things make this different from wrapping a model around a diff:

**Deterministic first.** Most controls are decided by a pure function over GitHub metadata, with no
model call at all. *Was there an approving review from someone who is not the author and not a
co-author* is a query, not a judgment. Only genuinely subjective assertions reach a model, and the
policy file marks which is which.

**Judgment is bounded.** Assertions that do call a model see only the evidence fields they declare,
return schema-constrained JSON, must cite specific evidence to fail, and run a self-consistency
quorum. Disagreement is reported as `INDETERMINATE` rather than resolved by majority vote.

**The output is measured.** A published false-positive rate against a frozen, hand-labeled corpus,
reported alongside a detection rate so it cannot be gamed by passing everything.

See [`docs/adr/`](docs/adr/) for the decisions and what was rejected, and
[`docs/technical-design.md`](docs/technical-design.md) for the schemas.

## Development

```bash
make setup
make test
make check PR=1
```

Local runs need a GitHub token in `.env` — see `.env.example`. Use a **classic** token; the Checks
API is not available to fine-grained tokens. In CI the action uses the scoped `GITHUB_TOKEN`
instead.

## How this was built

Built with AI assistance (Claude and Codex), and the workflow is part of the point. Every feature
started as a written spec with acceptance criteria; implementation ran in isolated passes against
it; CI enforced the tests.

The evaluation corpus labels are **not** model-generated. The quantity being measured is agreement
with human judgment, so model-generated labels would make the headline number circular. Deterministic
ground truth comes from the GitHub API, mutation ground truth is true by construction, and the
judgment assertions are hand-labeled, blind, before any prompt tuning.

## License

Apache-2.0
