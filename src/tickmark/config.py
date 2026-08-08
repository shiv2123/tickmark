"""Runtime configuration, resolved from CLI args, environment, and GitHub Actions context."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader. Does not override values already in the environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Config:
    repo: str
    pr_number: int
    token: str | None = None
    api_url: str = "https://api.github.com"
    policy_path: str = ".tickmark/policy.yml"
    max_diff_lines_per_file: int = 200

    # Populated from the Actions runtime when present.
    in_actions: bool = False
    is_fork_context: bool = False
    event_name: str | None = None

    notices: list = field(default_factory=list)

    @property
    def owner(self) -> str:
        return self.repo.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.repo.split("/", 1)[1]


def _detect_fork_context(event_path: str | None) -> bool:
    """True when the PR originates from a fork.

    Fork PRs get a read-only GITHUB_TOKEN and no access to secrets, so the run
    must degrade to deterministic-only and write to the job summary rather than
    a comment. See issue #15 and technical-design section 6.
    """
    if not event_path:
        return False
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    pr = payload.get("pull_request") or {}
    head_repo = (pr.get("head") or {}).get("repo") or {}
    base_repo = (pr.get("base") or {}).get("repo") or {}
    head_id, base_id = head_repo.get("id"), base_repo.get("id")
    if head_id is None or base_id is None:
        return bool(head_repo.get("fork"))
    return head_id != base_id


def _pr_number_from_event(event_path: str | None) -> int | None:
    if not event_path:
        return None
    try:
        payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pr = payload.get("pull_request") or {}
    number = pr.get("number")
    return int(number) if number is not None else None


def resolve(
    repo: str | None = None,
    pr_number: int | None = None,
    token: str | None = None,
    policy_path: str | None = None,
    dotenv: Path | None = None,
) -> Config:
    """Resolve config. Explicit arguments win over environment."""
    _load_dotenv(dotenv or Path.cwd() / ".env")

    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    event_path = os.environ.get("GITHUB_EVENT_PATH")

    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not repo or "/" not in repo:
        raise ConfigError(
            "Repository not set. Pass --repo owner/name or set GITHUB_REPOSITORY."
        )

    if pr_number is None:
        pr_number = _pr_number_from_event(event_path)
    if pr_number is None:
        raise ConfigError("Pull request number not set. Pass --pr N.")

    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ConfigError(
            "No GitHub token. Set GITHUB_TOKEN in .env, or pass --token. "
            "In Actions, pass ${{ secrets.GITHUB_TOKEN }}."
        )

    return Config(
        repo=repo,
        pr_number=int(pr_number),
        token=token,
        api_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        policy_path=policy_path or os.environ.get("TICKMARK_POLICY", ".tickmark/policy.yml"),
        in_actions=in_actions,
        is_fork_context=_detect_fork_context(event_path),
        event_name=os.environ.get("GITHUB_EVENT_NAME"),
    )
