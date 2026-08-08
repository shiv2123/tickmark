"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import ENGINE_VERSION, __version__
from .config import resolve
from .errors import ConfigError, TickmarkError
from .evidence.canonical import canonical_json, canonicalize
from .evidence.derive import derive
from .evidence.digest import evidence_digest
from .github.client import GitHubClient
from .github.collector import Collector
from .render import comment as comment_mod
from .render import summary as summary_mod


def _build_bundle(cfg) -> tuple[dict, str, list]:
    client = GitHubClient(cfg.token, api_url=cfg.api_url)
    collector = Collector(client, cfg)

    raw = collector.collect()
    bundle = canonicalize(raw, max_diff_lines=cfg.max_diff_lines_per_file)
    bundle["derived"] = derive(bundle)
    bundle["source"]["collected_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    digest = evidence_digest(
        bundle,
        policy=None,
        engine_version=ENGINE_VERSION,
        model_pin="none",
        prompt_version="0",
    )
    return bundle, digest, collector.notices


def cmd_collect(args: argparse.Namespace) -> int:
    cfg = resolve(repo=args.repo, pr_number=args.pr, token=args.token)
    bundle, digest, notices = _build_bundle(cfg)

    if args.output:
        Path(args.output).write_text(canonical_json(bundle) + "\n", encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(json.dumps(bundle, indent=2, sort_keys=True))

    print(f"\ndigest: {digest}", file=sys.stderr)
    for n in notices:
        print(f"[{n.level}] {n.code}: {n.message}", file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Collect, render, and post. Stage 0 posts an evidence preview."""
    cfg = resolve(repo=args.repo, pr_number=args.pr, token=args.token)
    bundle, digest, notices = _build_bundle(cfg)

    body = comment_mod.render_evidence_preview(bundle, digest, notices)

    if args.dry_run:
        print(body)
        return 0

    client = GitHubClient(cfg.token, api_url=cfg.api_url)
    posted, notice = comment_mod.upsert(client, cfg.repo, cfg.pr_number, body)
    if notice:
        notices.append(notice)
        print(f"[{notice.level}] {notice.code}: {notice.message}", file=sys.stderr)

    if not posted or cfg.in_actions:
        summary_mod.write(body)

    summary_mod.set_output("evidence_digest", digest)
    summary_mod.set_output("posted", "true" if posted else "false")

    if args.output:
        Path(args.output).write_text(canonical_json(bundle) + "\n", encoding="utf-8")

    print(f"digest: {digest}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tickmark",
        description="Change-management control evidence for pull requests.",
    )
    parser.add_argument("--version", action="version", version=f"tickmark {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", help="owner/name. Defaults to GITHUB_REPOSITORY.")
        p.add_argument("--pr", type=int, help="Pull request number.")
        p.add_argument("--token", help="Defaults to GITHUB_TOKEN.")
        p.add_argument("--output", help="Write the canonical bundle to this path.")

    p_collect = sub.add_parser("collect", help="Collect and print the evidence bundle.")
    common(p_collect)
    p_collect.set_defaults(func=cmd_collect)

    p_check = sub.add_parser("check", help="Collect, render, and post to the PR.")
    common(p_check)
    p_check.add_argument("--dry-run", action="store_true", help="Print the comment, post nothing.")
    p_check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except TickmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
