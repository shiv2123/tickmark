"""Tickmark: change-management control evidence for pull requests."""

__version__ = "0.0.1"

# Bumped when the evidence bundle or record schema changes in a breaking way.
SCHEMA_VERSION = "1.0"

# Part of the evidence digest. Bump when collection or derivation logic changes,
# so cached verdicts computed under the old logic are correctly invalidated.
ENGINE_VERSION = "0.0.1"
