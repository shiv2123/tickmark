#!/usr/bin/env bash
# Creates labels, milestones, and the Stage 0-4 issue set on the tickmark repo.
# Idempotent for labels and milestones. Refuses to run twice for issues unless forced.
#
#   ./scripts/bootstrap-github.sh
#
# Requires: gh CLI, authenticated (`gh auth login`), run from inside the repo.

set -euo pipefail

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo "Bootstrapping ${REPO}"
echo

# ---------------------------------------------------------------- guard

EXISTING="$(gh issue list --limit 1 --json number -q 'length')"
if [[ "${EXISTING}" != "0" && "${1:-}" != "--force" ]]; then
  echo "Issues already exist on ${REPO}. Re-running would create duplicates."
  echo "Pass --force if you're sure."
  exit 1
fi

# ---------------------------------------------------------------- labels

echo "Creating labels..."
create_label () { gh label create "$1" --color "$2" --description "$3" --force >/dev/null; }

create_label "stage-0"  "C5DEF5" "Skeleton: package, action, evidence collection"
create_label "stage-1"  "BFD4F2" "Deterministic engine"
create_label "stage-2"  "D4C5F9" "Eval harness, corpus, baseline"
create_label "stage-3"  "F9D0C4" "Judgment layer"
create_label "stage-4"  "FEF2C0" "Launch"
create_label "engine"   "0E8A16" "Evaluation engine and checks"
create_label "eval"     "5319E7" "Evaluation harness, corpus, metrics"
create_label "docs"     "0075CA" "Documentation"
create_label "bug"      "D73A4A" "Something is wrong"
create_label "design"   "FBCA04" "Needs a decision before implementation"
echo "  done"

# ------------------------------------------------------------ milestones

echo "Creating milestones..."
create_milestone () {
  gh api "repos/${REPO}/milestones" -f title="$1" -f description="$2" >/dev/null 2>&1 \
    || echo "  (exists) $1"
}

create_milestone "Stage 0 - Skeleton"        "Package, composite action, evidence collection, first PR comment"
create_milestone "Stage 1 - Deterministic"   "All deterministic assertions. Useful with zero API key."
create_milestone "Stage 2 - Eval + baseline" "Protocol, corpus, labeling UI, mutations, metrics, naive baseline"
create_milestone "Stage 3 - Judgment layer"  "Model client, scoping, citation requirement, quorum, cache"
create_milestone "Stage 4 - Launch"          "Held-out run, README with real numbers, marketplace, v0.1.0"
echo "  done"

# ---------------------------------------------------------------- issues

echo "Creating issues..."
mk () {
  local title="$1" milestone="$2" labels="$3" body="$4"
  gh issue create --title "${title}" --milestone "${milestone}" \
    --label "${labels}" --body "${body}" >/dev/null
  echo "  + ${title}"
}

M0="Stage 0 - Skeleton"
M1="Stage 1 - Deterministic"
M2="Stage 2 - Eval + baseline"
M3="Stage 3 - Judgment layer"
M4="Stage 4 - Launch"

# --- Stage 0
mk "Scaffold the package and composite action" "$M0" "stage-0" \
"Python package layout, \`action.yml\`, \`make test\`, CI running pytest on PRs.
Action installs the CLI and invokes it. No evaluation logic yet.

**Done when:** a workflow on a scratch repo runs the action and it exits 0."

mk "Evidence collector: PR metadata from the GitHub API" "$M0" "stage-0,engine" \
"Fetch PR, commits with trailers, changed files, reviews with timing, check runs, labels, linked
issues, branch protection. Handle pagination and secondary rate limits.

Reviews need the timeline API in some cases; the reviews endpoint alone does not always give the
commit a review was submitted against. See \`docs/technical-design.md\` §1."

mk "Canonical evidence bundle and digest" "$M0" "stage-0,engine" \
"Implement the normalization rules and \`derived\` block from \`docs/technical-design.md\` §1-2.

Sorted keys and arrays, ISO-8601 UTC, numeric identities not display names, deterministic diff
truncation. \`evidence_digest = sha256(bundle ‖ policy ‖ engine ‖ model_pin ‖ prompt_version)\`.

**Done when:** the same PR produces a byte-identical bundle across runs."

mk "Post a sticky PR comment" "$M0" "stage-0" \
"Find-or-update by hidden marker rather than appending. Degrade gracefully when the token is
read-only (fork PRs) by writing to the job summary instead."

# --- Stage 1
mk "Policy schema and parser" "$M1" "stage-1,engine" \
"\`apiVersion: tickmark/v1\`. JSON Schema validation on load with YAML line/column in errors.
Unknown top-level keys and unknown check names are hard errors, never silent skips.
See \`docs/technical-design.md\` §5."

mk "Scope predicates" "$M1" "stage-1,engine" \
"\`exempt_paths\`, \`exempt_authors\`, \`exempt_when\` (revert, all-files-exempt). Resolves to
\`NOT_APPLICABLE\`.

Per ADR 0003, most naive false positives are scope errors rather than reasoning errors, so this is
higher-value than it looks."

mk "CM-1.A1: work item reference present" "$M1" "stage-1,engine" \
"Search PR body, branch name, linked issues, and commit messages for \`work_item_pattern\`."

mk "CM-2.A1: independent approval count" "$M1" "stage-1,engine" \
"At least \`min_approvals\` approving reviews from users who are not the author and not a
\`Co-authored-by:\` trailer on any commit. Exclude bots.

Fixture tests required for each exclusion path separately."

mk "CM-2.A2: approval not stale" "$M1" "stage-1,engine" \
"Latest approving review must be at or after the last commit touching a production path.
An approval given before the code changed is not an approval of the code that merged."

mk "CM-3.A1: required checks passed" "$M1" "stage-1,engine" \
"All checks named in \`required_checks\` concluded success on the head SHA.
Distinguish 'check missing' from 'check failed' - they are different findings."

mk "CM-4.A2: changelog updated when required" "$M1" "stage-1,engine" \
"Changelog entry required when any production path changed."

mk "CM-5: emergency change path" "$M1" "stage-1,engine" \
"Conditional control, fires on emergency label or when CM-2/CM-3 failed.
A1 requires retrospective justification. A2 rejects undeclared bypass.
This encodes the only legitimate waiver route."

mk "Four-valued verdict model and control table rendering" "$M1" "stage-1" \
"PASS / FAIL / INDETERMINATE / NOT_APPLICABLE. Judgment failures render as advisory and never
govern the check-run conclusion in v1. See ADR 0003."

mk "Emit tickmark-evidence.json as a workflow artifact" "$M1" "stage-1" \
"Schema per \`docs/technical-design.md\` §3. Append-only: a re-run emits a new record with a new
\`record_id\` and never mutates an existing one. The Register depends on this."

mk "Fork PR handling" "$M1" "stage-1,engine" \
"Fork PRs get a read-only token and no secrets. Degrade to deterministic-only, mark it explicitly
in the record (\`inference: skipped_fork_context\`), write to the job summary instead of a comment.

Never silently emit a weaker verdict that looks complete. Do not check out fork code."

mk "Waiver parsing" "$M1" "stage-1" \
"\`tickmark: waive CM-3 - reason\` from a user in \`waiver_approvers\`. Records approver, reason,
timestamp in the evidence record. Does not suppress the finding."

# --- Stage 2
mk "Write and commit eval/PROTOCOL.md" "$M2" "stage-2,eval" \
"**Do this before labeling anything.** Sampling frame, seed, label definitions, metrics,
pre-registered target (FP below 10% with detection at or above 90%).

Git timestamping that the protocol predates the labels is the entire point. Everything else in
Stage 2 can slip; this cannot."

mk "Corpus miner" "$M2" "stage-2,eval" \
"Repo selection against the published criteria (branch protection with required reviews, required
status checks, CODEOWNERS, 6+ months history). Stratified random sample with a committed seed.

Expect secondary rate limits. Cache aggressively; mining should be re-runnable without re-fetching."

mk "Blind labeling UI" "$M2" "stage-2,eval" \
"Local server, keyboard-driven, one case per screen, renders only the fields the assertion is
scoped to see. Auto-saves each verdict immediately. Resumable.

**Must not be able to display engine output in labeling mode.** Enforce in the server, not by
convention. Include second-pass mode for the Cohen's kappa measurement."

mk "Mutation generator" "$M2" "stage-2,eval" \
"Eight mutation types per spec §6. Operates on the evidence bundle, never on GitHub.
Ground truth known by construction."

mk "Metrics module" "$M2" "stage-2,eval" \
"Wilson score intervals, Cohen's kappa, per-assertion breakdown.
FP reported judgment-only AND whole-system. Detection always reported alongside FP."

mk "Naive baseline implementation" "$M2" "stage-2,eval" \
"One model call, whole PR in the prompt, no scoping, no quorum, no citation requirement.
Committed and actually run. This is the 'before' number and it has to be earned, not asserted."

mk "Overnight eval runner" "$M2" "stage-2,eval" \
"Resumable, checkpointed after every call, disk-cached, \`--pace\` for thermal headroom.
Prints estimated wall time up front. Writes results plus a markdown summary on completion.
No caffeinate; sleep is controlled manually. See \`docs/technical-design.md\` §6."

mk "Label stratum A judgment assertions" "$M2" "stage-2,eval" \
"~80 PRs x 3 judgment assertions. Blind. Before any prompt tuning.
Roughly 2-3 hours. This is the one task that cannot be automated, because it is the thing
being measured."

# --- Stage 3
mk "Provider-agnostic model client" "$M3" "stage-3,engine" \
"OpenAI-compatible endpoint so Ollama, Gemini, OpenAI and Anthropic all work unchanged.
Temperature 0, JSON-schema-constrained output, model pinned by digest.
Retry with backoff; never lose checkpointed work when the backend dies."

mk "Judgment assertions CM-1.A2, CM-3.A2, CM-4.A1" "$M3" "stage-3,engine" \
"Evidence scoping enforced from the policy's \`evidence\` list. The model sees nothing else.
Guidance text comes verbatim from the policy file."

mk "Citation requirement" "$M3" "stage-3,engine" \
"Non-empty \`evidence_refs\` required for any FAIL verdict, else coerce to INDETERMINATE.
Cheapest and strongest false-positive lever available. See ADR 0003."

mk "Self-consistency quorum" "$M3" "stage-3,engine" \
"n=3. Non-unanimous resolves to INDETERMINATE rather than majority vote.
Record the individual votes in the evidence record."

mk "Content-addressed verdict cache" "$M3" "stage-3,engine" \
"Keyed on evidence digest plus prompt hash. Cache hit replays the verdict with zero model calls.
A \`synchronize\` event only re-evaluates assertions whose scoped evidence actually changed."

mk "Model size comparison: 8B vs 12B vs frontier" "$M3" "stage-3,eval,design" \
"Run the same eval across Qwen3 8B local, Gemma 3 12B local, and one hosted frontier model.
Ship the smallest model that holds detection at or above 90%.

Write ADR 0005 from the results, after measuring. This comparison is also the blog post."

mk "Tune against the dev set only" "$M3" "stage-3,eval" \
"Held-out set stays untouched. Iterate on a 15-PR smoke subset for speed; full dev runs overnight."

# --- Stage 4
mk "Held-out evaluation run" "$M4" "stage-4,eval" \
"Run 1 of 2. Publish the result whatever it is.
A published miss with an honest protocol beats a suspicious success."

mk "README with measured results" "$M4" "stage-4,docs" \
"Outline per spec §9. Must include: the note that temperature 0 is not bitwise reproducible across
providers, why detection is reported alongside FP, and the architecture-vs-prompting decomposition
of the improvement."

mk "Measure and publish cost per PR" "$M4" "stage-4,docs" \
"Named model, real number. Removes the most common objection to anything calling an LLM in CI."

mk "Marketplace listing and v0.1.0 tag" "$M4" "stage-4" \
"SOC 2 and compliance keywords for discovery. Apache-2.0."

echo
echo "Done. Next: https://github.com/${REPO}/issues"
