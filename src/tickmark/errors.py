"""Exception types.

Collection degrades rather than crashes wherever a missing permission is a
legitimate operating condition (see AGENTS.md rule 6: never silently degrade,
but do not fail the run either). Degradation is recorded as a Notice.
"""

from __future__ import annotations

from dataclasses import dataclass


class TickmarkError(Exception):
    """Base for all Tickmark errors."""


class ConfigError(TickmarkError):
    """Bad or missing configuration."""


class GitHubError(TickmarkError):
    """Non-recoverable GitHub API failure."""

    def __init__(self, message: str, status: int | None = None, url: str | None = None):
        super().__init__(message)
        self.status = status
        self.url = url


class RateLimitError(GitHubError):
    """Primary or secondary rate limit hit and retries were exhausted."""


@dataclass(frozen=True)
class Notice:
    """A recorded degradation. Surfaces in the evidence record.

    level: "info" | "warn" | "error"
    """

    level: str
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}
