"""Constants shared across modules that must not import each other."""

# Hidden marker identifying Tickmark's own PR comment.
#
# Used in two places, and the second one matters more than it looks:
#   1. render.comment  -- to find and update the sticky comment in place
#   2. github.collector -- to EXCLUDE that comment from the evidence bundle
#
# Without (2) the tool's output pollutes its own input: the comment contains an
# evidence digest, so collecting it changes the bundle, which changes the digest,
# which changes the comment. The digest would never stabilise on an unchanged
# pull request, which destroys the property the whole design exists to provide.
EVIDENCE_MARKER = "<!-- tickmark:evidence:v1 -->"
