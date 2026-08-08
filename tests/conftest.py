"""Shared fixtures.

Every test runs offline. Nothing here touches the network, by design: the only
module allowed to do IO is `github.client`, and it is faked below.
"""

from __future__ import annotations

import copy

import pytest

BASE_BUNDLE = {
    "schema_version": "1.1",
    "source": {
        "host": "github.com",
        "repo_id": 1324509884,
        "repo": "shiv2123/tickmark",
        "pr_number": 42,
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "merge_sha": None,
        "base_ref": "main",
        "is_fork": False,
    },
    "pr": {
        "title": "feat(engine): add stale-approval check",
        "body": "Implements CM-2.A2.\n\nCloses #17\nRefs OPS-1421",
        "body_length": 48,
        "state": "merged",
        "draft": False,
        "created_at": "2026-08-03T14:02:00Z",
        "merged_at": "2026-08-04T09:31:00Z",
        "author": {"id": 100, "type": "User", "is_bot": False},
        "labels": ["enhancement"],
        "milestone": None,
    },
    "commits": [
        {
            "sha": "c" * 40,
            "sequence": 0,
            "parents": ["b" * 40],  # the base commit
            "authored_at": "2026-08-03T13:50:00Z",
            "committed_at": "2026-08-03T13:50:00Z",
            "author_id": 100,
            "committer_id": 100,
            "co_author_emails": [],
            "message_subject": "feat(engine): add stale-approval check",
            "message_body": "",
            "verified": True,
        }
    ],
    "files": [
        {
            "path": "src/tickmark/checks/cm2.py",
            "status": "added",
            "previous_path": None,
            "additions": 84,
            "deletions": 0,
            "is_rename_only": False,
            "patch": "@@ -0,0 +1,3 @@\n+a\n+b\n+c",
            "patch_truncated": False,
        },
        {
            "path": "tests/test_cm2.py",
            "status": "added",
            "previous_path": None,
            "additions": 40,
            "deletions": 0,
            "is_rename_only": False,
            "patch": "@@ -0,0 +1,2 @@\n+x\n+y",
            "patch_truncated": False,
        },
    ],
    "reviews": [
        {
            "id": 998877,
            "reviewer_id": 200,
            "reviewer_is_bot": False,
            "state": "APPROVED",
            "submitted_at": "2026-08-04T08:12:00Z",
            "dismissed_at": None,
            "commit_sha": "c" * 40,
        }
    ],
    "checks": [
        {
            "id": 5001,
            "name": "test",
            "source": "check_run",
            "status": "completed",
            "conclusion": "success",
            "head_sha": "a" * 40,
            "completed_at": "2026-08-03T14:20:00Z",
        }
    ],
    "linked_issues": [
        {
            "number": 17,
            "title": "CM-2 should reject co-authored approvals",
            "body": "...",
            "state": "closed",
            "state_reason": "completed",
            "link_source": "body_keyword",
        }
    ],
    "comments": [],
    "repo_config": {
        "default_branch": "main",
        "branch_protection": {
            "available": True,
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "required_status_checks": ["build", "test"],
        },
        "has_codeowners": True,
    },
}


@pytest.fixture
def bundle() -> dict:
    return copy.deepcopy(BASE_BUNDLE)


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status
        self.headers = headers or {}
        self.text = text

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    """Routes requests by (method, path-suffix) so tests stay readable."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.headers: dict = {}
        self.calls: list[tuple[str, str]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        for suffix, response in self.routes.items():
            if url.endswith(suffix):
                return response
        return FakeResponse(status=404, text="not found")


@pytest.fixture
def fake_session():
    return FakeSession
