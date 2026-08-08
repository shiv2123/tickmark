"""Path glob matching with correct `**` semantics.

`fnmatch` treats `*` as matching across separators, which makes `src/*` match
`src/a/b.py`. That is wrong for path scoping and would silently widen every
control's blast radius, so we compile our own.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile a path glob.

    ``**/`` matches zero or more leading segments, ``**`` matches anything,
    ``*`` matches within one segment, ``?`` matches one non-separator character.
    """
    i, n, out = 0, len(pattern), []
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(path: str, patterns: list[str]) -> bool:
    return any(compile_glob(p).match(path) for p in patterns)


def matching(paths: list[str], patterns: list[str]) -> list[str]:
    return sorted(p for p in paths if matches(p, patterns))
