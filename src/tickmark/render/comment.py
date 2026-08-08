"""Sticky PR comment.

Find-or-update by hidden marker rather than appending. A compliance tool that
posts a fresh comment on every push trains people to mute it, and muted evidence
is no evidence.
"""

from __future__ import annotations

from ..constants import EVIDENCE_MARKER
from ..errors import GitHubError, Notice
from ..github.client import GitHubClient

MARKER = EVIDENCE_MARKER


def render_evidence_preview(bundle: dict, digest: str, notices: list[Notice]) -> str:
    """Stage 0 body: what was collected. Control verdicts arrive in Stage 1."""
    src = bundle.get("source") or {}
    pr = bundle.get("pr") or {}
    d = bundle.get("derived") or {}

    checks = bundle.get("checks") or []
    passed = sum(1 for c in checks if c.get("conclusion") == "success")
    approvals = sum(1 for r in bundle.get("reviews") or [] if r.get("state") == "APPROVED")

    # "not configured" and "none found" are different facts and must read
    # differently. Conflating them is how an absence of evidence gets laundered
    # into a pass.
    if not d.get("work_item_pattern_configured"):
        work_items = "_no pattern configured_"
    else:
        work_items = ", ".join(d.get("work_item_refs") or []) or "none found"

    lines = [
        MARKER,
        "### Tickmark — evidence collected",
        "",
        "_Control evaluation is not wired up yet. This is the evidence the engine sees._",
        "",
        "| Signal | Value |",
        "| --- | --- |",
        f"| Files changed | {d.get('file_count', 0)} (+{d.get('total_additions', 0)} / -{d.get('total_deletions', 0)}) |",
        f"| Production paths touched | {len(d.get('production_paths_touched') or [])} |",
        f"| Test paths touched | {len(d.get('test_paths_touched') or [])} |",
        f"| Commits | {len(bundle.get('commits') or [])} |",
        f"| Approving reviews | {approvals} |",
        f"| Checks reported | {len(checks)} ({passed} success) |",
        f"| Linked issues | {len(bundle.get('linked_issues') or [])} |",
        f"| Work item references | {work_items} |",
        f"| Revert | {'yes' if d.get('is_revert') else 'no'} |",
        f"| All files exempt | {'yes' if d.get('all_files_exempt') else 'no'} |",
        f"| Branch protection readable | {'yes' if ((bundle.get('repo_config') or {}).get('branch_protection') or {}).get('available') else 'no'} |",
        "",
    ]

    if notices:
        lines += ["<details><summary>Notices</summary>", ""]
        for n in notices:
            lines.append(f"- **{n.level}** `{n.code}` — {n.message}")
        lines += ["", "</details>", ""]

    lines += [
        "<details><summary>Provenance</summary>",
        "",
        f"- Evidence digest: `{digest}`",
        f"- Head SHA: `{src.get('head_sha')}`",
        f"- PR state: `{pr.get('state')}`",
        f"- Fork PR: `{src.get('is_fork')}`",
        "",
        "</details>",
    ]
    return "\n".join(lines)


def find_existing(client: GitHubClient, repo: str, pr_number: int) -> int | None:
    """Comment id of the existing Tickmark comment, if any."""
    try:
        comments = client.paginate(f"repos/{repo}/issues/{pr_number}/comments")
    except GitHubError:
        return None
    for comment in comments:
        if MARKER in (comment.get("body") or ""):
            return comment.get("id")
    return None


def upsert(
    client: GitHubClient, repo: str, pr_number: int, body: str
) -> tuple[bool, Notice | None]:
    """Create or update the sticky comment.

    Returns (posted, notice). A read-only token is an expected condition on fork
    PRs, not an error, so it degrades to a Notice and the caller falls back to
    the job summary.
    """
    existing = find_existing(client, repo, pr_number)
    try:
        if existing is not None:
            client.patch(f"repos/{repo}/issues/comments/{existing}", {"body": body})
        else:
            client.post(f"repos/{repo}/issues/{pr_number}/comments", {"body": body})
        return True, None
    except GitHubError as exc:
        if exc.status in (401, 403, 404):
            return False, Notice(
                "warn",
                "comment_not_posted",
                f"Could not post the PR comment (HTTP {exc.status}). Token is likely "
                "read-only, which is expected on fork pull requests. Results were "
                "written to the job summary instead.",
            )
        raise
