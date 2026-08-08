"""Collector tests. No network: the session is faked in conftest."""

from tickmark.config import Config
from tickmark.github.client import GitHubClient
from tickmark.github.collector import CO_AUTHOR_RE, Collector, _actor, _co_author_names
from tickmark.render.comment import MARKER

from .conftest import FakeResponse


def make_collector(routes, session_cls):
    session = session_cls(routes)
    client = GitHubClient("t", session=session)
    cfg = Config(repo="o/r", pr_number=42, token="t")
    return Collector(client, cfg), session


class TestCoAuthorParsing:
    def test_standard_trailer(self):
        assert _co_author_names("x\n\nCo-authored-by: Ann <ann@x.com>") == ["ann@x.com"]

    def test_case_insensitive(self):
        assert _co_author_names("co-AUTHORED-by: A <a@x.com>") == ["a@x.com"]

    def test_multiple_trailers(self):
        message = "x\n\nCo-authored-by: A <a@x.com>\nCo-authored-by: B <b@x.com>"
        assert _co_author_names(message) == ["a@x.com", "b@x.com"]

    def test_emails_lowercased_for_comparison(self):
        assert _co_author_names("Co-authored-by: A <MiXeD@X.com>") == ["mixed@x.com"]

    def test_not_matched_mid_line(self):
        """Only a real trailer counts, not a mention inside prose."""
        assert _co_author_names("see Co-authored-by: A <a@x.com> above") == []

    def test_absent(self):
        assert _co_author_names("just a message") == []
        assert _co_author_names("") == []

    def test_regex_requires_angle_brackets(self):
        assert CO_AUTHOR_RE.search("Co-authored-by: A a@x.com") is None


class TestActor:
    def test_bot_by_type(self):
        assert _actor({"id": 1, "type": "Bot", "login": "x"})["is_bot"] is True

    def test_bot_by_login_suffix(self):
        assert _actor({"id": 1, "type": "User", "login": "dependabot[bot]"})["is_bot"] is True

    def test_human(self):
        assert _actor({"id": 1, "type": "User", "login": "shiv2123"})["is_bot"] is False

    def test_missing_user_does_not_raise(self):
        assert _actor(None)["id"] is None

    def test_login_is_not_retained(self):
        """Display names must never reach the bundle: they change, and models
        reason about them (ADR 0002)."""
        assert "login" not in _actor({"id": 1, "type": "User", "login": "shiv2123"})


class TestForkDetection:
    def test_different_repo_ids_is_fork(self):
        pr = {"head": {"repo": {"id": 2}}, "base": {"repo": {"id": 1}}}
        assert Collector._is_fork(pr) is True

    def test_same_repo_id_is_not_fork(self):
        pr = {"head": {"repo": {"id": 1}}, "base": {"repo": {"id": 1}}}
        assert Collector._is_fork(pr) is False

    def test_deleted_head_repo_falls_back_to_fork_flag(self):
        pr = {"head": {"repo": None}, "base": {"repo": {"id": 1}}}
        assert Collector._is_fork(pr) is False


class TestBranchProtection:
    def test_unavailable_is_explicit_not_absent(self, fake_session):
        """A 403 because the token lacks admin scope is a different fact from a
        repo with no protection. Conflating them produces false findings."""
        collector, _ = make_collector(
            {"/protection": FakeResponse(status=403, text="forbidden")}, fake_session
        )
        result = collector._collect_protection("repos/o/r", "main")
        assert result["available"] is False
        assert any(n.code == "branch_protection_unavailable" for n in collector.notices)

    def test_available_is_parsed(self, fake_session):
        payload = {
            "required_pull_request_reviews": {
                "required_approving_review_count": 2,
                "dismiss_stale_reviews": True,
            },
            "required_status_checks": {"contexts": ["test", "build"]},
        }
        collector, _ = make_collector({"/protection": FakeResponse(payload)}, fake_session)
        result = collector._collect_protection("repos/o/r", "main")
        assert result["available"] is True
        assert result["required_approving_review_count"] == 2
        assert result["required_status_checks"] == ["build", "test"]
        assert collector.notices == []

    def test_no_default_branch_returns_unavailable(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        assert collector._collect_protection("repos/o/r", None)["available"] is False


class TestChecks:
    def test_reads_both_check_runs_and_commit_statuses(self, fake_session):
        """Plenty of repos still report CI through the Statuses API. A control
        that only reads check runs would wrongly conclude no CI ran."""
        routes = {
            "/check-runs": FakeResponse({"check_runs": [
                {"name": "test", "status": "completed", "conclusion": "success",
                 "head_sha": "a", "completed_at": "2026-08-03T14:20:00Z"}
            ]}),
            "/status": FakeResponse({"statuses": [
                {"context": "legacy-ci", "state": "success", "updated_at": "2026-08-03T14:21:00Z"}
            ]}),
        }
        collector, _ = make_collector(routes, fake_session)
        checks = collector._collect_checks("repos/o/r", "a" * 40)
        sources = {c["source"] for c in checks}
        assert sources == {"check_run", "commit_status"}

    def test_missing_checks_api_records_a_notice(self, fake_session):
        routes = {
            "/check-runs": FakeResponse(status=403, text="forbidden"),
            "/status": FakeResponse({"statuses": []}),
        }
        collector, _ = make_collector(routes, fake_session)
        collector._collect_checks("repos/o/r", "a" * 40)
        assert any(n.code == "check_runs_unavailable" for n in collector.notices)

    def test_no_head_sha_returns_empty(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        assert collector._collect_checks("repos/o/r", None) == []

    def test_check_run_id_is_collected(self, fake_session):
        """A re-run produces a second check run with the same name for the same
        SHA. Without the id there is no way to say which one is current, and the
        required-checks control would be choosing between them arbitrarily."""
        routes = {
            "/check-runs": FakeResponse({"check_runs": [
                {"id": 111, "name": "test", "status": "completed", "conclusion": "failure",
                 "head_sha": "a", "completed_at": "2026-08-03T14:20:00Z"},
                {"id": 222, "name": "test", "status": "completed", "conclusion": "success",
                 "head_sha": "a", "completed_at": "2026-08-03T15:00:00Z"},
            ]}),
            "/status": FakeResponse({"statuses": []}),
        }
        collector, _ = make_collector(routes, fake_session)
        checks = collector._collect_checks("repos/o/r", "a" * 40)
        assert [c["id"] for c in checks] == [111, 222]


class TestCommitShaping:
    def test_sequence_records_the_api_position(self, fake_session):
        """Canonicalization re-sorts commits by authored_at, so branch order has
        to be carried explicitly or it is lost."""
        collector, _ = make_collector({}, fake_session)
        assert collector._shape_commit({"sha": "a", "commit": {}}, 3)["sequence"] == 3

    def test_parents_collected_in_order(self, fake_session):
        """First parent is the branch merged onto. Order is meaning, not noise."""
        collector, _ = make_collector({}, fake_session)
        shaped = collector._shape_commit(
            {"sha": "m", "commit": {}, "parents": [{"sha": "first"}, {"sha": "second"}]}, 0
        )
        assert shaped["parents"] == ["first", "second"]

    def test_missing_parents_is_empty_list_not_absent_key(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        assert collector._shape_commit({"sha": "a", "commit": {}}, 0)["parents"] == []

    def test_author_and_commit_dates_both_retained(self, fake_session):
        """They differ after a rebase, and staleness depends on which one is
        read. Collecting only one would decide that silently."""
        collector, _ = make_collector({}, fake_session)
        shaped = collector._shape_commit({
            "sha": "a",
            "commit": {
                "author": {"date": "2026-08-01T00:00:00Z"},
                "committer": {"date": "2026-08-04T00:00:00Z"},
            },
        }, 0)
        assert shaped["authored_at"] == "2026-08-01T00:00:00Z"
        assert shaped["committed_at"] == "2026-08-04T00:00:00Z"


class TestLinkedIssues:
    def test_closing_keyword_detected(self, fake_session):
        routes = {"/issues/17": FakeResponse(
            {"title": "t", "body": "b", "state": "closed", "state_reason": "completed"}
        )}
        collector, _ = make_collector(routes, fake_session)
        pr = {"body": "Closes #17", "head": {"ref": "feat/x"}}
        issues = collector._collect_linked_issues("repos/o/r", pr, [])
        assert [i["number"] for i in issues] == [17]
        assert issues[0]["link_source"] == "body_keyword"

    def test_pull_request_reference_is_excluded(self, fake_session):
        """#N may be a PR. Counting it as an authorizing work item would be wrong."""
        routes = {"/issues/17": FakeResponse(
            {"title": "t", "body": "b", "state": "closed", "pull_request": {"url": "..."}}
        )}
        collector, _ = make_collector(routes, fake_session)
        pr = {"body": "Closes #17", "head": {"ref": "x"}}
        assert collector._collect_linked_issues("repos/o/r", pr, []) == []

    def test_self_reference_excluded(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        pr = {"body": "see #42", "head": {"ref": "x"}}
        assert collector._collect_linked_issues("repos/o/r", pr, []) == []

    def test_unreadable_issue_records_notice_and_continues(self, fake_session):
        collector, _ = make_collector({"/issues/17": FakeResponse(status=404)}, fake_session)
        pr = {"body": "Closes #17", "head": {"ref": "x"}}
        assert collector._collect_linked_issues("repos/o/r", pr, []) == []
        assert any(n.code == "linked_issue_unreadable" for n in collector.notices)


class TestCommentCollection:
    """Regression guard for self-reference.

    Tickmark's comment carries an evidence digest. Collecting it puts the tool's
    own prior output into its input, so the bundle changes on every run and the
    digest never stabilises on an unchanged PR. That is precisely the failure
    this project exists to prevent, and it shipped in Stage 0.
    """

    def test_own_comment_is_excluded(self, fake_session):
        routes = {
            "/comments": FakeResponse([
                {"id": 1, "user": {"id": 10, "type": "User"}, "created_at": "t",
                 "body": "a human comment"},
                {"id": 2, "user": {"id": 41898282, "type": "Bot"}, "created_at": "t",
                 "body": MARKER + "\nEvidence digest: `sha256:abc`"},
            ])
        }
        collector, _ = make_collector(routes, fake_session)
        comments = collector._collect_comments("repos/o/r", 42)
        assert [c["id"] for c in comments] == [1]

    def test_exclusion_is_recorded_not_silent(self, fake_session):
        routes = {"/comments": FakeResponse([
            {"id": 2, "user": {"id": 1, "type": "Bot"}, "created_at": "t", "body": MARKER}
        ])}
        collector, _ = make_collector(routes, fake_session)
        collector._collect_comments("repos/o/r", 42)
        assert any(n.code == "self_comment_excluded" for n in collector.notices)

    def test_other_bot_comments_are_kept(self, fake_session):
        """Only Tickmark's own output is self-reference. Other bots are evidence."""
        routes = {"/comments": FakeResponse([
            {"id": 3, "user": {"id": 5, "type": "Bot"}, "created_at": "t",
             "body": "Codecov report: 91%"}
        ])}
        collector, _ = make_collector(routes, fake_session)
        assert [c["id"] for c in collector._collect_comments("repos/o/r", 42)] == [3]

    def test_no_notice_when_nothing_excluded(self, fake_session):
        routes = {"/comments": FakeResponse([
            {"id": 1, "user": {"id": 10, "type": "User"}, "created_at": "t", "body": "hi"}
        ])}
        collector, _ = make_collector(routes, fake_session)
        collector._collect_comments("repos/o/r", 42)
        assert collector.notices == []


class TestShaping:
    def test_pr_merged_state_is_distinct_from_closed(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        assert collector._shape_pr({"merged": True, "state": "closed"})["state"] == "merged"
        assert collector._shape_pr({"merged": False, "state": "closed"})["state"] == "closed"

    def test_rename_only_requires_zero_net_change(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        pure = collector._shape_file(
            {"filename": "a", "status": "renamed", "additions": 0, "deletions": 0}
        )
        edited = collector._shape_file(
            {"filename": "a", "status": "renamed", "additions": 5, "deletions": 1}
        )
        assert pure["is_rename_only"] is True
        assert edited["is_rename_only"] is False

    def test_review_keeps_commit_sha_for_staleness(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        shaped = collector._shape_review(
            {"id": 1, "user": {"id": 2, "type": "User"}, "state": "APPROVED",
             "submitted_at": "2026-08-04T08:12:00Z", "commit_id": "abc"}
        )
        assert shaped["commit_sha"] == "abc"

    def test_null_body_becomes_empty_string(self, fake_session):
        collector, _ = make_collector({}, fake_session)
        assert collector._shape_pr({"body": None})["body"] == ""


class TestCommentMarker:
    def test_marker_is_html_comment_so_it_renders_invisibly(self):
        assert MARKER.startswith("<!--") and MARKER.endswith("-->")
