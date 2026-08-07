# ADR 0001 — Python, delivered as a composite action

**Status:** Accepted
**Date:** 2026-08-05

## Context

GitHub Actions has a native TypeScript/JavaScript ecosystem. Most published Actions are bundled JS,
and the tooling (`@actions/core`, `ncc`) assumes it. Choosing Python means going against the grain of
the ecosystem, so it needs justifying.

The Action, however, is not the whole system. The project also needs:

- a corpus miner against the GitHub API
- a mutation generator operating on evidence bundles
- a blind labeling CLI
- statistical reporting (Wilson score intervals, Cohen's κ)
- eventually, an ingest and query service for the Evidence Register

## Decision

**Python 3.12**, with the core shipped as a pip-installable CLI and the Action delivered as a
**composite action** that installs the package and invokes the CLI.

## Alternatives considered

**TypeScript, bundled JS action.** Native to the ecosystem, ~1s startup, no runtime dependency on the
runner. Rejected because the eval harness, miner, mutation generator, statistics, and Register are
all unavoidably Python. Writing the Action in TypeScript means **two implementations of the policy
parser**, since the harness must parse policy files to evaluate against them. That duplication is
the largest hidden cost available in this project and it buys nothing a user can observe.

**Docker container action.** Any language, hermetic. Rejected for v1 because a per-run build costs
60–90s, and avoiding that means publishing to GHCR, which is publishing machinery this project does
not need yet. Retained as a future option: same Python source, different delivery, not a rewrite.

## Consequences

- **Cost:** ~10–20s of `pip install` per run versus ~1s for a bundled JS action. Mitigated by pinning
  the version and using `actions/setup-python` cache. For a check that may also make a model call,
  this is noise.
- **Benefit:** the CLI is independently useful. `tickmark check --pr 123` runs locally, which makes
  development and eval trivial and lowers adoption friction for people who want to try before wiring
  CI.
- **Limitation to document:** composite actions require Python on the runner. All GitHub-hosted
  runners have it; self-hosted runners may not. The README must say so.
- The Register inherits FastAPI, so stage two introduces no new stack.
