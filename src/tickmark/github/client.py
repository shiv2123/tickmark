"""Thin GitHub REST client: pagination, rate limits, retries, and soft failures.

Deliberately small. This is the only module that touches the network, which keeps
every other module testable offline (AGENTS.md rule 2).
"""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from ..errors import GitHubError, RateLimitError

USER_AGENT = "tickmark/0.0.1 (+https://github.com/shiv2123/tickmark)"

# Statuses worth retrying. 403 is included because GitHub returns it for
# secondary rate limits, which are transient.
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}


class GitHubClient:
    def __init__(
        self,
        token: str,
        api_url: str = "https://api.github.com",
        *,
        max_retries: int = 5,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": USER_AGENT,
            }
        )

    # ---------------------------------------------------------------- internals

    def _sleep_for(self, response: requests.Response, attempt: int) -> float:
        """How long to wait before retrying, honouring GitHub's own guidance."""
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # Primary rate limit: wait until the window resets.
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining == "0" and reset:
            try:
                wait = float(reset) - time.time()
                if wait > 0:
                    return min(wait + 1.0, 900.0)
            except ValueError:
                pass

        # Otherwise exponential backoff with jitter.
        return min(2.0**attempt, 60.0) + random.uniform(0, 1.0)

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        if not url.startswith("http"):
            url = f"{self.api_url}/{url.lstrip('/')}"

        last: requests.Response | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                if attempt == self.max_retries - 1:
                    raise GitHubError(f"Network failure calling {url}: {exc}", url=url) from exc
                time.sleep(min(2.0**attempt, 30.0))
                continue

            if response.status_code not in RETRY_STATUSES:
                return response

            # A 403 that is not a rate limit is a real permission problem, and
            # retrying it just wastes time.
            if response.status_code == 403 and not self._is_rate_limited(response):
                return response

            last = response
            if attempt < self.max_retries - 1:
                time.sleep(self._sleep_for(response, attempt))

        raise RateLimitError(
            f"Exhausted {self.max_retries} retries for {url} "
            f"(last status {last.status_code if last else 'unknown'})",
            status=last.status_code if last else None,
            url=url,
        )

    @staticmethod
    def _is_rate_limited(response: requests.Response) -> bool:
        if response.headers.get("x-ratelimit-remaining") == "0":
            return True
        if "retry-after" in response.headers:
            return True
        body = (response.text or "").lower()
        return "rate limit" in body or "secondary" in body

    # ------------------------------------------------------------------- public

    def get(self, path: str, **params: Any) -> Any:
        """GET one resource. Raises on failure."""
        response = self._request("GET", path, params=params or None)
        if not response.ok:
            raise GitHubError(
                f"GET {path} returned {response.status_code}: {response.text[:200]}",
                status=response.status_code,
                url=path,
            )
        return response.json()

    def get_optional(self, path: str, **params: Any) -> tuple[Any | None, int]:
        """GET a resource that may legitimately be unavailable.

        Returns (payload_or_None, status_code). Used for branch protection and
        CODEOWNERS, where 403 or 404 is an operating condition rather than a
        failure. The caller records a Notice.
        """
        response = self._request("GET", path, params=params or None)
        if response.ok:
            return response.json(), response.status_code
        return None, response.status_code

    def paginate(self, path: str, *, per_page: int = 100, max_pages: int = 50, **params: Any) -> list:
        """Follow Link headers and concatenate results."""
        out: list = []
        params = {**params, "per_page": per_page}
        url: str | None = path
        pages = 0

        while url and pages < max_pages:
            response = self._request("GET", url, params=params if pages == 0 else None)
            if not response.ok:
                raise GitHubError(
                    f"GET {url} returned {response.status_code}: {response.text[:200]}",
                    status=response.status_code,
                    url=url,
                )
            payload = response.json()
            if isinstance(payload, dict):
                # Some endpoints wrap results, e.g. check-runs.
                for key in ("check_runs", "items", "statuses", "workflow_runs"):
                    if key in payload:
                        payload = payload[key]
                        break
                else:
                    return [payload]
            out.extend(payload)
            url = self._next_link(response)
            pages += 1

        return out

    @staticmethod
    def _next_link(response: requests.Response) -> str | None:
        link = response.headers.get("link")
        if not link:
            return None
        for part in link.split(","):
            section = part.split(";")
            if len(section) < 2:
                continue
            if 'rel="next"' in section[1].replace(" ", "").replace("'", '"'):
                return section[0].strip().strip("<>")
        return None

    @staticmethod
    def page_of(url: str) -> int:
        qs = parse_qs(urlparse(url).query)
        return int(qs.get("page", ["1"])[0])

    # ------------------------------------------------------------------ writes

    def post(self, path: str, json_body: dict) -> Any:
        response = self._request("POST", path, json=json_body)
        if not response.ok:
            raise GitHubError(
                f"POST {path} returned {response.status_code}: {response.text[:200]}",
                status=response.status_code,
                url=path,
            )
        return response.json()

    def patch(self, path: str, json_body: dict) -> Any:
        response = self._request("PATCH", path, json=json_body)
        if not response.ok:
            raise GitHubError(
                f"PATCH {path} returned {response.status_code}: {response.text[:200]}",
                status=response.status_code,
                url=path,
            )
        return response.json()
