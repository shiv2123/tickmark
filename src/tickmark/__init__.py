"""Tickmark: change-management control evidence for pull requests."""

__version__ = "0.0.1"

# Bumped when the evidence bundle or record schema changes in a breaking way.
#
# 1.1 -- commits gained `sequence` and `parents`, checks gained `id`, and the
#        `derived` block replaced `last_production_commit_at` with honest
#        commit-order fields. See docs/technical-design.md section 1.
SCHEMA_VERSION = "1.1"

# Part of the evidence digest. Bump when collection or derivation logic changes,
# so cached verdicts computed under the old logic are correctly invalidated.
ENGINE_VERSION = "0.1.0"
