from tickmark.errors import Notice
from tickmark.evidence.canonical import canonicalize
from tickmark.evidence.derive import derive
from tickmark.github.client import GitHubClient
from tickmark.render.comment import MARKER, find_existing, render_evidence_preview, upsert

from .conftest import FakeResponse


def prepared(bundle):
    out = canonicalize(bundle)
    out["derived"] = derive(out)
    return out


class TestRendering:
    def test_starts_with_marker(self, bundle):
        body = render_evidence_preview(prepared(bundle), "sha256:abc", [])
        assert body.startswith(MARKER)

    def test_marker_is_invisible_html_comment(self):
        assert MARKER.startswith("<!--")
        assert MARKER.endswith("-->")

    def test_includes_digest(self, bundle):
        body = render_evidence_preview(prepared(bundle), "sha256:deadbeef", [])
        assert "sha256:deadbeef" in body

    def test_includes_work_item_reference(self, bundle):
        assert "OPS-1421" in render_evidence_preview(prepared(bundle), "d", [])

    def test_reports_no_work_items_explicitly(self, bundle):
        bundle["pr"]["body"] = ""
        bundle["pr"]["title"] = "a change"
        bundle["commits"][0]["message_subject"] = "a change"
        assert "none found" in render_evidence_preview(prepared(bundle), "d", [])

    def test_notices_are_surfaced_not_swallowed(self, bundle):
        """Silent degradation is the failure mode that turns a compliance tool
        into a liability (AGENTS.md rule 6)."""
        notice = Notice("warn", "branch_protection_unavailable", "token lacks admin scope")
        body = render_evidence_preview(prepared(bundle), "d", [notice])
        assert "branch_protection_unavailable" in body
        assert "token lacks admin scope" in body

    def test_no_notices_section_when_clean(self, bundle):
        assert "Notices" not in render_evidence_preview(prepared(bundle), "d", [])

    def test_states_when_branch_protection_unreadable(self, bundle):
        bundle["repo_config"]["branch_protection"]["available"] = False
        body = render_evidence_preview(prepared(bundle), "d", [])
        assert "Branch protection readable | no" in body


class TestFindExisting:
    def test_finds_comment_carrying_the_marker(self):
        class S:
            headers: dict = {}

            def request(self, method, url, **kwargs):
                return FakeResponse([{"id": 1, "body": "hi"}, {"id": 2, "body": MARKER + "\nx"}])

        assert find_existing(GitHubClient("t", session=S()), "o/r", 1) == 2

    def test_returns_none_when_absent(self):
        class S:
            headers: dict = {}

            def request(self, method, url, **kwargs):
                return FakeResponse([{"id": 1, "body": "unrelated"}])

        assert find_existing(GitHubClient("t", session=S()), "o/r", 1) is None


class TestUpsert:
    def test_updates_in_place_rather_than_appending(self):
        """A tool that posts a fresh comment per push trains people to mute it."""
        calls = []

        class S:
            headers: dict = {}

            def request(self, method, url, **kwargs):
                calls.append((method, url))
                if method == "GET":
                    return FakeResponse([{"id": 7, "body": MARKER}])
                return FakeResponse({"id": 7})

        posted, notice = upsert(GitHubClient("t", session=S()), "o/r", 1, "body")
        assert posted is True
        assert notice is None
        assert any(m == "PATCH" and u.endswith("/comments/7") for m, u in calls)

    def test_creates_when_none_exists(self):
        calls = []

        class S:
            headers: dict = {}

            def request(self, method, url, **kwargs):
                calls.append((method, url))
                return FakeResponse([] if method == "GET" else {"id": 1})

        posted, _ = upsert(GitHubClient("t", session=S()), "o/r", 1, "body")
        assert posted is True
        assert any(m == "POST" for m, _ in calls)

    def test_read_only_token_degrades_to_notice(self):
        """Expected on fork PRs. Must not crash the run."""

        class S:
            headers: dict = {}

            def request(self, method, url, **kwargs):
                if method == "GET":
                    return FakeResponse([])
                return FakeResponse(status=403, text="Resource not accessible by integration")

        posted, notice = upsert(GitHubClient("t", session=S()), "o/r", 1, "body")
        assert posted is False
        assert notice is not None
        assert notice.code == "comment_not_posted"
