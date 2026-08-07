# ADR 0004 — Evaluation protocol and ground-truth sourcing

**Status:** Accepted
**Date:** 2026-08-05

## Context

The central claim this project can make is a measured false-positive rate. That claim is worth
nothing unless the measurement is resistant to the obvious ways of fooling oneself, most of which are
unintentional: tuning against the test set, adding easy cases after seeing results, reporting a
favourable metric in isolation, or treating a point estimate as precise.

There is also a specific trap available here. A tool that returns PASS for everything scores a perfect
0% false-positive rate.

## Decision

### Ground truth is tiered by how it is obtained

| Tier | Source | Human cost |
| --- | --- | --- |
| Deterministic assertions | The GitHub API | none |
| Mutation cases | True by construction | none |
| Judgment assertions (3 of 10) | Hand-labeled, blind | ~2–3 hours total |

### Deterministic assertions are unit-tested, not evaluated

If the engine computes a value from the GitHub API and ground truth is also derived from the GitHub
API, measuring one against the other is close to tautological. Folding those cases into a headline
false-positive rate dilutes it with cases that were never at risk of being wrong.

So deterministic assertions get pytest with hand-built fixtures for the genuinely tricky cases
(dismissed reviews, bot approvals, `Co-authored-by:` trailers, approvals predating the final commit,
force-pushes after approval). Judgment assertions get the eval harness.

### Three strata

- **A — mined real PRs** from public repos with genuine change-management practice. Stratified random
  sample, committed seed. Measures **false positives**.
- **B — mutation corpus.** Real compliant PRs with the evidence bundle mutated to break exactly one
  assertion. Measures **detection**. Zero labeling.
- **C — adversarial near-misses**, ~20 hand-built cases with written rationales.

### Nine protocol rules

1. Pre-register `eval/PROTOCOL.md` before labeling anything. Git timestamps the ordering.
2. Freeze the corpus before tuning; later additions go to a disclosed `v2` set.
3. Blind labeling, enforced in code — the CLI never shows the engine's verdict.
4. Label before tuning.
5. 60/40 dev/held-out split. **The held-out set is touched exactly twice**, and both runs are
   published.
6. Re-label a random 20% after 7+ days and report Cohen's κ.
7. Wilson 95% intervals on every rate, never point estimates.
8. The baseline is a real committed implementation that is actually run, not a described strawman.
9. Publish corpus, protocol, results, and a `make eval` that reproduces.

### Reporting

Report false-positive rate **two ways**: judgment-only (the honest measure of the model layer) and
whole-system (what a user experiences). Report **detection rate alongside FP, always** — publishing FP
alone is the classic dodge and it is the first thing a sharp reader probes.

Decompose the baseline-to-final improvement between *architecture* (routing controls away from the
model) and *prompting* (scoping, citation, quorum). Most of the gain is architectural, which is the
actual contribution and should be stated rather than hidden inside a delta.

## Alternatives considered

**Model-generated labels.** Rejected outright. If a model produces the verdicts and a model produces
the ground truth, the measured rate is the agreement between two model calls. It trends to zero by
construction and measures nothing. The quantity being measured *is* agreement with human judgment.

**Synthetic corpus only.** Cheap and ground truth is free. Rejected as the headline: artificial
negatives do not measure real-world false positives, which is the entire claim.

**Private real-world corpus.** Authentic, and unpublishable, so the number would be uncheckable. That
inverts the project's one advantage.

## Consequences

- The three-judgment-assertion count is set by the labeling budget, not by coverage ambition. Adding
  controls has a direct, measurable cost.
- The pre-registered target is set before measuring: **FP below 10% with detection at or above 90% on
  every assertion.** A published miss with an honest protocol is worth more than a suspicious success.
- Anyone can reproduce the number. That is the point.
