"""Canonicalization: the determinism guarantee.

Most observed non-determinism in LLM pipelines is input jitter, not sampling
(ADR 0002). The GitHub API returns files in varying order, timestamps carry
sub-second noise, and display names change. Removing that variance matters more
than any sampling parameter.

Rules, from technical-design section 1:
  1. Object keys sorted at every level
  2. Arrays sorted by a declared stable key
  3. Timestamps ISO-8601 UTC, second precision
  4. Identities are numeric ids, never display names
  5. Diffs truncated deterministically
  6. Nothing volatile that is not control-relevant
  7. Serialized with sorted keys and no incidental whitespace
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

DEFAULT_MAX_DIFF_LINES = 200

# Excluded from the digest because it changes on every run without changing
# anything a control cares about.
EXCLUDED_FROM_DIGEST = ("collected_at",)


def normalize_timestamp(value: Any) -> str | None:
    """ISO-8601 UTC, second precision, trailing Z. None passes through."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return str(value)
    dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def truncate_patch(patch: str | None, max_lines: int = DEFAULT_MAX_DIFF_LINES) -> tuple[str | None, bool]:
    """Keep the first `max_lines` lines. Returns (patch, was_truncated)."""
    if not patch:
        return patch, False
    lines = patch.split("\n")
    if len(lines) <= max_lines:
        return patch, False
    return "\n".join(lines[:max_lines]), True


def _sort_key(item: dict, keys: tuple[str, ...]) -> tuple:
    """Sort tuple that tolerates None without raising on mixed comparisons."""
    out: list = []
    for key in keys:
        value = item.get(key)
        out.append((value is None, "" if value is None else str(value)))
    return tuple(out)


def canonicalize(bundle: dict, *, max_diff_lines: int = DEFAULT_MAX_DIFF_LINES) -> dict:
    """Return a normalized copy. Does not mutate the input."""
    out = json.loads(json.dumps(bundle))  # deep copy, and rejects non-JSON values early

    # --- timestamps
    pr = out.get("pr") or {}
    for field in ("created_at", "merged_at"):
        if field in pr:
            pr[field] = normalize_timestamp(pr[field])

    for commit in out.get("commits") or []:
        for field in ("authored_at", "committed_at"):
            commit[field] = normalize_timestamp(commit.get(field))
        commit["co_author_emails"] = sorted(set(commit.get("co_author_emails") or []))

    for review in out.get("reviews") or []:
        for field in ("submitted_at", "dismissed_at"):
            review[field] = normalize_timestamp(review.get(field))

    for check in out.get("checks") or []:
        check["completed_at"] = normalize_timestamp(check.get("completed_at"))

    for comment in out.get("comments") or []:
        comment["created_at"] = normalize_timestamp(comment.get("created_at"))

    # --- diffs
    for f in out.get("files") or []:
        f["patch"], f["patch_truncated"] = truncate_patch(f.get("patch"), max_diff_lines)

    # --- array ordering
    out["commits"] = sorted(out.get("commits") or [], key=lambda c: _sort_key(c, ("authored_at", "sha")))
    out["files"] = sorted(out.get("files") or [], key=lambda f: _sort_key(f, ("path",)))
    out["reviews"] = sorted(out.get("reviews") or [], key=lambda r: _sort_key(r, ("submitted_at", "id")))
    out["checks"] = sorted(out.get("checks") or [], key=lambda c: _sort_key(c, ("name", "source")))
    out["comments"] = sorted(out.get("comments") or [], key=lambda c: _sort_key(c, ("created_at", "id")))
    out["linked_issues"] = sorted(out.get("linked_issues") or [], key=lambda i: _sort_key(i, ("number",)))

    if pr.get("labels"):
        pr["labels"] = sorted(pr["labels"])

    return out


def canonical_json(obj: Any) -> str:
    """Deterministic serialization. This exact form is what gets hashed."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def strip_for_digest(bundle: dict) -> dict:
    """Remove fields excluded from the digest."""
    out = json.loads(json.dumps(bundle))
    source = out.get("source") or {}
    for field in EXCLUDED_FROM_DIGEST:
        source.pop(field, None)
    return out
