"""Client tests. The session is faked; nothing here touches the network."""

from tickmark.github.client import GitHubClient

from .conftest import FakeResponse


class RecordingSession:
    """Returns queued responses in order and counts calls."""

    headers: dict = {}

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0) if self.responses else FakeResponse(status=404)


def client_for(responses):
    session = RecordingSession(responses)
    return GitHubClient("token", session=session, max_retries=3), session


class TestPagination:
    def test_follows_next_link(self):
        pages = [
            FakeResponse([{"a": 1}], headers={"link": '<https://api.github.com/x?page=2>; rel="next"'}),
            FakeResponse([{"a": 2}]),
        ]
        client, session = client_for(pages)
        assert client.paginate("repos/o/r/pulls/1/commits") == [{"a": 1}, {"a": 2}]
        assert session.calls == 2

    def test_stops_without_next_link(self):
        client, session = client_for([FakeResponse([{"a": 1}])])
        assert client.paginate("x") == [{"a": 1}]
        assert session.calls == 1

    def test_unwraps_check_runs_envelope(self):
        client, _ = client_for([FakeResponse({"check_runs": [{"n": 1}]})])
        assert client.paginate("x") == [{"n": 1}]

    def test_bare_dict_returned_as_single_item(self):
        client, _ = client_for([FakeResponse({"id": 5})])
        assert client.paginate("x") == [{"id": 5}]

    def test_max_pages_caps_runaway_pagination(self):
        link = {"link": '<https://api.github.com/x?page=99>; rel="next"'}
        client, session = client_for([FakeResponse([{"a": 1}], headers=link) for _ in range(10)])
        client.paginate("x", max_pages=3)
        assert session.calls == 3


class TestRetries:
    def test_permission_403_is_not_retried(self):
        """A 403 without rate-limit signals is a real permission problem.
        Retrying it just burns time and makes failures slow."""
        client, session = client_for([FakeResponse(status=403, text="Resource not accessible")])
        payload, status = client.get_optional("x")
        assert payload is None
        assert status == 403
        assert session.calls == 1

    def test_rate_limited_403_is_retried(self):
        limited = FakeResponse(status=403, text="API rate limit exceeded",
                               headers={"retry-after": "0"})
        client, session = client_for([limited, FakeResponse({"ok": True})])
        assert client.get("x") == {"ok": True}
        assert session.calls == 2

    def test_500_is_retried(self):
        client, session = client_for([FakeResponse(status=500), FakeResponse({"ok": True})])
        assert client.get("x") == {"ok": True}
        assert session.calls == 2


class TestGetOptional:
    def test_success_returns_payload_and_status(self):
        client, _ = client_for([FakeResponse({"a": 1})])
        assert client.get_optional("x") == ({"a": 1}, 200)

    def test_404_returns_none_without_raising(self):
        """Absence is an operating condition for CODEOWNERS and branch protection."""
        client, _ = client_for([FakeResponse(status=404)])
        payload, status = client.get_optional("x")
        assert payload is None
        assert status == 404


class TestLinkHeaderParsing:
    def test_picks_next_not_last(self):
        header = (
            '<https://api.github.com/x?page=2>; rel="next", '
            '<https://api.github.com/x?page=9>; rel="last"'
        )
        assert GitHubClient._next_link(FakeResponse(headers={"link": header})).endswith("page=2")

    def test_absent_link_header(self):
        assert GitHubClient._next_link(FakeResponse()) is None

    def test_only_last_means_no_next(self):
        header = '<https://api.github.com/x?page=9>; rel="last"'
        assert GitHubClient._next_link(FakeResponse(headers={"link": header})) is None
