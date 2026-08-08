"""Assemble the raw evidence bundle from the GitHub API.

Fetches, shapes, and records degradations. Does NOT normalize or derive:
that is `evidence.canonical` and `evidence.derive`, which are pure and
therefore testable without the network.
"""

from __future__ import annotations

import re
from typing import Any

from .. import SCHEMA_VERSION
from ..config import Config
from ..errors import Notice
from .client import GitHubClient

# "Co-authored-by: Name <email>" -- git trailer, case-insensitive, own line.
CO_AUTHOR_RE = re.compile(r"^\s*co-authored-by:\s*(.+?)\s*<(.+?)>\s*$", re.IGNORECASE | re.MULTILINE)

# GitHub closing keywords, plus bare "#123" references.
CLOSING_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.IGNORECASE
)
BARE_REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")

CODEOWNERS_PATHS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")


def _actor(user: dict | None) -> dict:
    """Identity as a stable numeric id plus a bot flag. Never a display name."""
    if not user:
        return {"id": None, "type": "Unknown", "is_bot": False}
    return {
        "id": user.get("id"),
        "type": user.get("type", "User"),
        "is_bot": user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]"),
    }


def _split_message(message: str) -> tuple[str, str]:
    subject, _, body = (message or "").partition("\n")
    return subject.strip(), body.strip()


def _co_author_names(message: str) -> list[str]:
    return [m.group(2).strip().lower() for m in CO_AUTHOR_RE.finditer(message or "")]


class Collector:
    def __init__(self, client: GitHubClient, config: Config):
        self.client = client
        self.config = config
        self.notices: list[Notice] = []

    def _notice(self, level: str, code: str, message: str) -> None:
        self.notices.append(Notice(level, code, message))

    # ------------------------------------------------------------------ collect

    def collect(self) -> dict[str, Any]:
        owner, name = self.config.owner, self.config.name
        n = self.config.pr_number
        base = f"repos/{owner}/{name}"

        repo = self.client.get(base)
        pr = self.client.get(f"{base}/pulls/{n}")

        commits = self.client.paginate(f"{base}/pulls/{n}/commits")
        files = self.client.paginate(f"{base}/pulls/{n}/files")
        reviews = self.client.paginate(f"{base}/pulls/{n}/reviews")
        comments = self.client.paginate(f"{base}/issues/{n}/comments")

        head_sha = (pr.get("head") or {}).get("sha")
        checks = self._collect_checks(base, head_sha)
        protection = self._collect_protection(base, repo.get("default_branch"))
        has_codeowners = self._has_codeowners(base)
        linked = self._collect_linked_issues(base, pr, commits)

        return {
            "schema_version": SCHEMA_VERSION,
            "source": {
                "host": "github.com",
                "repo_id": repo.get("id"),
                "repo": f"{owner}/{name}",
                "pr_number": n,
                "head_sha": head_sha,
                "base_sha": (pr.get("base") or {}).get("sha"),
                "merge_sha": pr.get("merge_commit_sha") if pr.get("merged") else None,
                "base_ref": (pr.get("base") or {}).get("ref"),
                "is_fork": self._is_fork(pr),
            },
            "pr": self._shape_pr(pr),
            "commits": [self._shape_commit(c) for c in commits],
            "files": [self._shape_file(f) for f in files],
            "reviews": [self._shape_review(r) for r in reviews],
            "checks": checks,
            "linked_issues": linked,
            "comments": [self._shape_comment(c) for c in comments],
            "repo_config": {
                "default_branch": repo.get("default_branch"),
                "branch_protection": protection,
                "has_codeowners": has_codeowners,
            },
        }

    # ------------------------------------------------------------------ shaping

    @staticmethod
    def _is_fork(pr: dict) -> bool:
        head = (pr.get("head") or {}).get("repo") or {}
        base = (pr.get("base") or {}).get("repo") or {}
        if head.get("id") is None or base.get("id") is None:
            return bool(head.get("fork"))
        return head["id"] != base["id"]

    def _shape_pr(self, pr: dict) -> dict:
        body = pr.get("body") or ""
        state = "merged" if pr.get("merged") else pr.get("state", "open")
        return {
            "title": pr.get("title") or "",
            "body": body,
            "body_length": len(body),
            "state": state,
            "draft": bool(pr.get("draft")),
            "created_at": pr.get("created_at"),
            "merged_at": pr.get("merged_at"),
            "author": _actor(pr.get("user")),
            "labels": [lbl.get("name") for lbl in (pr.get("labels") or []) if lbl.get("name")],
            "milestone": (pr.get("milestone") or {}).get("title"),
        }

    def _shape_commit(self, c: dict) -> dict:
        commit = c.get("commit") or {}
        message = commit.get("message") or ""
        subject, body = _split_message(message)
        return {
            "sha": c.get("sha"),
            "authored_at": (commit.get("author") or {}).get("date"),
            "committed_at": (commit.get("committer") or {}).get("date"),
            "author_id": (c.get("author") or {}).get("id"),
            "committer_id": (c.get("committer") or {}).get("id"),
            "co_author_emails": _co_author_names(message),
            "message_subject": subject,
            "message_body": body,
            "verified": bool((commit.get("verification") or {}).get("verified")),
        }

    def _shape_file(self, f: dict) -> dict:
        additions = f.get("additions", 0)
        deletions = f.get("deletions", 0)
        status = f.get("status")
        patch = f.get("patch")
        return {
            "path": f.get("filename"),
            "status": status,
            "previous_path": f.get("previous_filename"),
            "additions": additions,
            "deletions": deletions,
            "is_rename_only": status == "renamed" and additions == 0 and deletions == 0,
            "patch": patch,
            "patch_truncated": False,  # set during canonicalization
        }

    def _shape_review(self, r: dict) -> dict:
        return {
            "id": r.get("id"),
            "reviewer_id": (r.get("user") or {}).get("id"),
            "reviewer_is_bot": _actor(r.get("user"))["is_bot"],
            "state": r.get("state"),
            "submitted_at": r.get("submitted_at"),
            "dismissed_at": None,  # DISMISSED state carries the signal we need
            "commit_sha": r.get("commit_id"),
        }

    def _shape_comment(self, c: dict) -> dict:
        return {
            "id": c.get("id"),
            "author_id": (c.get("user") or {}).get("id"),
            "author_is_bot": _actor(c.get("user"))["is_bot"],
            "created_at": c.get("created_at"),
            "body": c.get("body") or "",
        }

    # -------------------------------------------------------------- sub-fetches

    def _collect_checks(self, base: str, head_sha: str | None) -> list[dict]:
        """Check runs plus legacy commit statuses.

        Both are needed: modern CI reports check runs, but plenty of repos still
        report through the Statuses API, and a control that only looks at one
        will wrongly conclude no CI ran.
        """
        if not head_sha:
            return []

        out: list[dict] = []

        runs, status = self.client.get_optional(f"{base}/commits/{head_sha}/check-runs")
        if runs is None:
            self._notice(
                "warn",
                "check_runs_unavailable",
                f"Could not read check runs (HTTP {status}). Fine-grained tokens cannot "
                "access the Checks API; use a classic token locally.",
            )
        else:
            for run in runs.get("check_runs", []):
                out.append(
                    {
                        "name": run.get("name"),
                        "source": "check_run",
                        "status": run.get("status"),
                        "conclusion": run.get("conclusion"),
                        "head_sha": run.get("head_sha") or head_sha,
                        "completed_at": run.get("completed_at"),
                    }
                )

        combined, status = self.client.get_optional(f"{base}/commits/{head_sha}/status")
        if combined is None:
            self._notice(
                "info",
                "commit_statuses_unavailable",
                f"Could not read commit statuses (HTTP {status}).",
            )
        else:
            for st in combined.get("statuses", []):
                out.append(
                    {
                        "name": st.get("context"),
                        "source": "commit_status",
                        "status": "completed",
                        "conclusion": "success" if st.get("state") == "success" else st.get("state"),
                        "head_sha": head_sha,
                        "completed_at": st.get("updated_at"),
                    }
                )

        return out

    def _collect_protection(self, base: str, default_branch: str | None) -> dict:
        """Branch protection. Requires admin scope, so absence is expected.

        `available: false` is recorded explicitly. A missing value because the
        token lacked scope is a different fact from a repo with no protection,
        and conflating them produces confident false findings.
        """
        unavailable = {
            "available": False,
            "required_approving_review_count": None,
            "dismiss_stale_reviews": None,
            "required_status_checks": [],
        }
        if not default_branch:
            return unavailable

        payload, status = self.client.get_optional(f"{base}/branches/{default_branch}/protection")
        if payload is None:
            self._notice(
                "warn",
                "branch_protection_unavailable",
                f"Could not read branch protection (HTTP {status}). Token likely lacks "
                "admin scope. Controls relying on it will report NOT_APPLICABLE.",
            )
            return unavailable

        reviews = payload.get("required_pull_request_reviews") or {}
        checks = payload.get("required_status_checks") or {}
        return {
            "available": True,
            "required_approving_review_count": reviews.get("required_approving_review_count"),
            "dismiss_stale_reviews": reviews.get("dismiss_stale_reviews"),
            "required_status_checks": sorted(checks.get("contexts") or []),
        }

    def _has_codeowners(self, base: str) -> bool:
        for path in CODEOWNERS_PATHS:
            payload, _ = self.client.get_optional(f"{base}/contents/{path}")
            if payload is not None:
                return True
        return False

    def _collect_linked_issues(self, base: str, pr: dict, commits: list[dict]) -> list[dict]:
        """Issues referenced by closing keyword, bare reference, or branch name."""
        body = pr.get("body") or ""
        branch = (pr.get("head") or {}).get("ref") or ""

        found: dict[int, str] = {}
        for match in CLOSING_RE.finditer(body):
            found.setdefault(int(match.group(1)), "body_keyword")
        for match in BARE_REF_RE.finditer(body):
            found.setdefault(int(match.group(1)), "body_reference")
        for match in BARE_REF_RE.finditer(branch):
            found.setdefault(int(match.group(1)), "branch_name")
        for commit in commits:
            message = (commit.get("commit") or {}).get("message") or ""
            for match in CLOSING_RE.finditer(message):
                found.setdefault(int(match.group(1)), "commit_message")

        out: list[dict] = []
        for number in sorted(found):
            if number == self.config.pr_number:
                continue
            payload, status = self.client.get_optional(f"{base}/issues/{number}")
            if payload is None:
                self._notice(
                    "info",
                    "linked_issue_unreadable",
                    f"Referenced #{number} could not be read (HTTP {status}).",
                )
                continue
            if "pull_request" in payload:
                continue  # a PR reference, not an issue
            out.append(
                {
                    "number": number,
                    "title": payload.get("title") or "",
                    "body": payload.get("body") or "",
                    "state": payload.get("state"),
                    "state_reason": payload.get("state_reason"),
                    "link_source": found[number],
                }
            )
        return out
