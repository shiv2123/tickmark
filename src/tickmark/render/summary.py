"""GitHub Actions job summary.

Always available, even on fork PRs with a read-only token, so it is the fallback
whenever the comment cannot be posted.
"""

from __future__ import annotations

import os
from pathlib import Path


def write(body: str) -> bool:
    """Append to $GITHUB_STEP_SUMMARY. Returns False when not running in Actions."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    try:
        with Path(path).open("a", encoding="utf-8") as fh:
            fh.write(body)
            fh.write("\n")
        return True
    except OSError:
        return False


def set_output(name: str, value: str) -> bool:
    """Set a GitHub Actions step output."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return False
    try:
        with Path(path).open("a", encoding="utf-8") as fh:
            if "\n" in value:
                delimiter = "__TICKMARK_EOF__"
                fh.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                fh.write(f"{name}={value}\n")
        return True
    except OSError:
        return False
