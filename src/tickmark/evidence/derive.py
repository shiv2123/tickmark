"""The `derived` block: precomputed facts so checks stay pure and cheap.

Checks must not re-parse diffs or walk commit histories (AGENTS.md rule 2).
Anything expensive or fiddly is computed once, here, and lives inside the hashed
bundle -- which means changing this logic correctly invalidates the cache via
ENGINE_VERSION.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .globs import matches, matching

REVERT_TITLE_RE = re.compile(r"^\s*revert\b", re.IGNORECASE)
REVERT_BODY_RE = re.compile(r"^\s*this reverts commit\s+[0-9a-f]{7,40}", re.IGNORECASE | re.MULTILINE)

DEFAULT_PRODUCTION_PATHS = ["src/**", "lib/**", "app/**", "migrations/**", "infra/**"]
DEFAULT_TEST_PATHS = [
    "test/**", "tests/**", "spec/**", "**/__tests__/**",
    "**/test_*.py", "**/*_test.py", "**/*_test.go",
    "**/*.test.ts", "**/*.test.tsx", "**/*.test.js",
    "**/*.spec.ts", "**/*.spec.tsx", "**/*.spec.js",
]
DEFAULT_EXEMPT_PATHS = ["docs/**", "*.md", "**/*.md", "LICENSE", ".github/ISSUE_TEMPLATE/**"]

# There is deliberately no default work-item pattern.
#
# A tempting default is something like r"[A-Z][A-Z0-9]+-\d+". It is wrong, and
# wrong in the most damaging direction available to this tool. That pattern
# matches OPS-1421, and it equally matches UTF-8, SHA-256, ISO-8601, RFC-2119,
# CVE-2024-1234, and CM-2. No regex can separate a ticket key from any other
# uppercase-hyphen-digit token, because they are structurally identical.
#
# The consequence is a false PASS on the control that establishes authorization:
# any pull request mentioning a character encoding would appear to reference an
# approved work item. A control that is satisfied by noise is worse than no
# control, because it launders an absence of evidence into a pass.
#
# So an unconfigured pattern yields no references, and CM-1.A1 resolves to
# NOT_APPLICABLE with a notice rather than guessing (AGENTS.md rules 5 and 6).
DEFAULT_WORK_ITEM_PATTERN: str | None = None


@dataclass
class ScopeConfig:
    """Path and pattern configuration. Supplied by the policy from Stage 1;
    defaults keep the collector usable standalone."""

    production_paths: list[str] = field(default_factory=lambda: list(DEFAULT_PRODUCTION_PATHS))
    test_paths: list[str] = field(default_factory=lambda: list(DEFAULT_TEST_PATHS))
    exempt_paths: list[str] = field(default_factory=lambda: list(DEFAULT_EXEMPT_PATHS))
    work_item_pattern: str | None = DEFAULT_WORK_ITEM_PATTERN


def _is_revert(pr: dict) -> bool:
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    return bool(REVERT_TITLE_RE.match(title) or REVERT_BODY_RE.search(body))


def _work_item_refs(bundle: dict, pattern: str | None) -> list[str]:
    """Work item identifiers found anywhere a reasonable person would put one.

    Returns [] when no pattern is configured. See the note on
    DEFAULT_WORK_ITEM_PATTERN for why there is no default.
    """
    if not pattern:
        return []
    try:
        regex = re.compile(pattern)
    except re.error:
        return []

    haystacks: list[str] = []
    pr = bundle.get("pr") or {}
    haystacks.append(pr.get("title") or "")
    haystacks.append(pr.get("body") or "")
    haystacks.append((bundle.get("source") or {}).get("base_ref") or "")
    for commit in bundle.get("commits") or []:
        haystacks.append(commit.get("message_subject") or "")
        haystacks.append(commit.get("message_body") or "")
    for issue in bundle.get("linked_issues") or []:
        haystacks.append(issue.get("title") or "")

    found: set[str] = set()
    for text in haystacks:
        found.update(regex.findall(text))
    return sorted(found)


# The exact shape canonicalization guarantees. An unparseable timestamp is
# passed through verbatim by design rather than dropped, which means a string
# max over the raw values could return "not a date" -- lexically above any real
# timestamp. Filtering to the canonical shape makes a mangled input yield None,
# so a check sees "unknown" and reports INDETERMINATE instead of nonsense.
CANONICAL_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _max_stamp(commits: list[dict], field: str) -> str | None:
    """Latest value of `field`, or None if none is usable.

    String max is chronological max only because every value is fixed-width
    ISO-8601 UTC. That invariant is enforced here, not assumed.
    """
    stamps = [c[field] for c in commits if CANONICAL_TS_RE.match(str(c.get(field) or ""))]
    return max(stamps) if stamps else None


def _commit_order(commits: list[dict]) -> tuple[list[str], bool]:
    """Commit SHAs in branch order, and whether that order was verifiable.

    Returns (shas, verified).

    Branch order is what makes staleness answerable: an approval is stale iff
    commits landed after the SHA it was submitted against. Comparing clocks
    instead is weaker, because git timestamps are supplied by the committer and
    survive rebase, amend, and cherry-pick.

    `sequence` carries the position GitHub returned. `parents` lets that claim be
    checked rather than trusted: in topological order every commit after the
    first names a parent that appeared earlier. When the walk fails -- parents
    absent, history rewritten by a force-push, an unusual merge shape -- the
    order is not trustworthy, and a check that depends on it must report
    INDETERMINATE rather than guess (AGENTS.md rule 5).
    """
    if not commits:
        return [], False

    ordered = sorted(
        commits, key=lambda c: (c.get("sequence") is None, c.get("sequence") or 0, c.get("sha") or "")
    )
    shas = [c["sha"] for c in ordered if c.get("sha")]

    if len(shas) != len(commits) or any(c.get("sequence") is None for c in commits):
        return shas, False

    seen: set[str] = set()
    verified = True
    for i, commit in enumerate(ordered):
        parents = commit.get("parents") or []
        # The first commit's parent is the base, which is outside the pull
        # request, so it links back by definition. Every later commit must name
        # a parent already seen. No parents at all means they could not be read,
        # which is unknown rather than verified.
        links_back = bool(parents) and (i == 0 or any(p in seen for p in parents))
        if not links_back:
            verified = False
        seen.add(commit["sha"])
    return shas, verified


def derive(bundle: dict, scope: ScopeConfig | None = None) -> dict:
    """Compute the derived block. Pure."""
    scope = scope or ScopeConfig()
    pr = bundle.get("pr") or {}
    files = bundle.get("files") or []
    paths = [f.get("path") for f in files if f.get("path")]

    # Identities GitHub resolved for us. Co-author trailers give emails, not ids;
    # resolving those to accounts is tracked as its own issue.
    identities: set[int] = set()
    author_id = (pr.get("author") or {}).get("id")
    if author_id is not None:
        identities.add(author_id)
    for commit in bundle.get("commits") or []:
        for key in ("author_id", "committer_id"):
            if commit.get(key) is not None:
                identities.add(commit[key])

    co_author_emails: set[str] = set()
    for commit in bundle.get("commits") or []:
        co_author_emails.update(commit.get("co_author_emails") or [])

    non_exempt = [p for p in paths if not matches(p, scope.exempt_paths)]

    commits = bundle.get("commits") or []
    commit_shas, order_verified = _commit_order(commits)

    return {
        "is_revert": _is_revert(pr),
        "author_and_co_author_ids": sorted(identities),
        "co_author_emails": sorted(co_author_emails),
        # Branch order, and whether it could be checked. The previous field here
        # was named last_production_commit_at, took the production path list,
        # never used it, and returned max(authored_at) over every commit. Three
        # separate ways to mislead: the name claimed a scoping that did not
        # happen, so a docs-only follow-up commit flipped a good approval to
        # stale; and author date is preserved by rebase, so a rebased branch
        # read as fresh. Names now say what the values are.
        "commit_shas_in_order": commit_shas,
        "commit_order_verified": order_verified,
        "head_commit_sha": commit_shas[-1] if commit_shas else None,
        "last_commit_at": _max_stamp(commits, "committed_at"),
        "last_authored_at": _max_stamp(commits, "authored_at"),
        "production_paths_touched": matching(paths, scope.production_paths),
        "test_paths_touched": matching(paths, scope.test_paths),
        "exempt_paths_touched": matching(paths, scope.exempt_paths),
        "all_files_exempt": len(paths) > 0 and len(non_exempt) == 0,
        "has_only_rename_changes": len(files) > 0 and all(f.get("is_rename_only") for f in files),
        "work_item_refs": _work_item_refs(bundle, scope.work_item_pattern),
        "work_item_pattern_configured": bool(scope.work_item_pattern),
        "file_count": len(files),
        "total_additions": sum(f.get("additions") or 0 for f in files),
        "total_deletions": sum(f.get("deletions") or 0 for f in files),
    }
