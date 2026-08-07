# ADR 0002 — Deterministic-first evaluation, with a bounded judgment layer

**Status:** Accepted
**Date:** 2026-08-05

## Context

LLM inconsistency at compliance-checking tasks is a documented failure mode, not a hypothetical one.
Published work on checklist-based LLM auditing of CI workflows identifies three specific weaknesses:
anchoring on irrelevant signals, inconsistency across samples of the same input, and failure to
recognise novel patterns.

A compliance tool that returns a different verdict on the same unchanged pull request is worse than
no tool, because it destroys the property the tool exists to provide: evidence someone can rely on.

Temperature 0 does not solve this. Provider-side batching, mixture-of-experts routing, and hardware
variation all break bitwise reproducibility even at temperature 0. Claiming determinism on that basis
would be false.

## Decision

Split every control into **assertions**, each explicitly typed `deterministic` or `judgment` **in the
policy file itself**, and resolve as much as possible without a model.

Pipeline: collect → normalize → digest → scope → determine → gate → judge → quorum → cache → emit.

Determinism comes from four architectural properties rather than from sampling parameters:

1. **Deterministic-first.** Seven of ten assertions never invoke a model. For those, determinism is
   total, not statistical.
2. **Canonicalization.** Sorted keys, sorted lists, ISO-8601 UTC timestamps, stable numeric identities
   instead of display names, deterministically truncated diffs. Most observed non-determinism in LLM
   pipelines is input jitter, not sampling.
3. **Evidence scoping.** Each judgment assertion declares the fields it may see. The model cannot
   anchor on a signal it was never shown.
4. **Content-addressed cache.** Identical evidence digest replays the identical verdict, so
   user-visible behaviour is deterministic even where the model is not.

## Alternatives considered

**Single LLM call over the whole PR.** Simplest, and it is the baseline the eval measures against.
Rejected as the product: it inherits every documented weakness at once.

**Rules only, no model.** Fully deterministic and genuinely useful — this is what ships at Stage 1.
Rejected as the endpoint because the interesting controls (is the stated purpose intelligible, is the
documentation adequate) are irreducibly judgment calls, and pretending otherwise produces a linter.

**Majority-vote quorum resolving to a verdict.** Rejected in favour of surfacing disagreement as
`INDETERMINATE`. If the model cannot agree with itself, that is information, and hiding it behind a
majority vote converts a known uncertainty into a false certainty.

## Consequences

- Tickmark does not claim to eliminate LLM inconsistency. It **detects and reports** it. This is a
  weaker claim than "deterministic" and it is the one that survives scrutiny.
- The deterministic/judgment split is visible to users in their own policy file, so they can see which
  conclusions came from a query and which came from a model.
- The gate and cache also bound cost: a re-run on an unchanged PR costs zero model calls.
- Adding a control is not free. Every judgment assertion added multiplies eval labeling cost. This is
  the main force holding v1 to five controls.
