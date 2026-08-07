# ADR 0003 — Three-valued logic, and how false positives are contained

**Status:** Accepted
**Date:** 2026-08-05

## Context

A compliance tool that cries wolf gets disabled within a week. This is the dominant failure mode for
the category, and it is a product failure rather than a model failure: the tool is uninstalled long
before anyone evaluates whether its reasoning was any good.

Binary pass/fail forces every uncertain case into one of two wrong answers. Forcing uncertainty to
FAIL produces noise. Forcing it to PASS produces a tool that certifies nothing.

## Decision

**Four verdicts:** `PASS`, `FAIL`, `INDETERMINATE`, `NOT_APPLICABLE`.

Five containment mechanisms, in order of effect:

1. **Only deterministic assertions may hard-fail.** In v1, a judgment assertion that would fail emits
   `FAIL (advisory)`, visually distinct, and never governs the check-run conclusion. This
   structurally caps the blast radius of a model mistake.
2. **Citation required to fail.** The output schema requires `evidence_refs` to be non-empty for any
   FAIL. A model that cannot point at the evidence supporting a failure has its verdict coerced to
   `INDETERMINATE`. Cheap to implement, and the strongest single lever available.
3. **Scope predicates.** Controls do not fire on changes they never governed: docs-only edits,
   dependency bots, reverts, release automation. A large share of naive-tool false positives are not
   reasoning errors at all, they are scope errors, and they are removable before any reasoning
   happens.
4. **Waivers as recorded exceptions.** `tickmark: waive CM-3 — reason` from an authorized approver
   records a waiver *in the evidence record* with approver, reason, and timestamp. It does not
   suppress the finding.
5. **Ratchet modes.** `observe` (default) → `advise` → `enforce`. New installs never block anything.

## Alternatives considered

**Binary pass/fail.** Familiar, and matches how CI checks usually behave. Rejected: it converts every
uncertain judgment into a confident wrong answer, in a domain where confident wrong answers are the
whole risk.

**Silent suppression of known-noisy controls.** Common in linters (`# noqa`). Rejected because
suppressed findings are invisible, and an audit trail whose exceptions are invisible is not an audit
trail. An exception must be evidence, not absence of evidence.

**Blocking merges by default.** Rejected. It feels like the point of a control gate, and it is the
fastest possible route to being uninstalled. Blocking is available via `enforce`, opt-in, after a
team trusts the output.

## Consequences

- `INDETERMINATE` must be designed for in the UI. A control table where a third of rows say "unclear"
  is a bad experience, so the indeterminate rate is a reported eval metric and a design target.
- The waiver path means CM-5 (emergency change) carries real weight: it encodes the *only* legitimate
  route around a control.
- Advisory-by-default means early adopters get no enforcement value. Accepted: adoption first,
  enforcement once trusted.
