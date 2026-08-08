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


def _last_production_commit_at(bundle: dict, production_paths: list[str]) -> str | None:
    """Timestamp of the newest commit, used as the staleness reference point.

    Per-file commit attribution would need one API call per commit, which is not
    worth it: any commit in the PR after an approval makes that approval stale in
    the sense the control cares about. Narrowing to production paths only is
    tracked separately.
    """
    stamps = [c.get("authored_at") for c in bundle.get("commits") or [] if c.get("authored_at")]
    return max(stamps) if stamps else None


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

    return {
        "is_revert": _is_revert(pr),
        "author_and_co_author_ids": sorted(identities),
        "co_author_emails": sorted(co_author_emails),
        "last_production_commit_at": _last_production_commit_at(bundle, scope.production_paths),
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
