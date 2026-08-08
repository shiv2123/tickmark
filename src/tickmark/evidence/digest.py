"""Content addressing.

    evidence_digest = sha256(
        canonical_json(bundle minus excluded)
      || policy_digest || engine_version || model_pin || prompt_version
    )

Identical inputs replay an identical verdict, which is what makes user-visible
behaviour deterministic even where a model is not (ADR 0002). The model pin and
prompt version are included deliberately: changing either *should* invalidate
cached verdicts, or you would be reporting a stale result.
"""

from __future__ import annotations

import hashlib

from .canonical import canonical_json, strip_for_digest

SEPARATOR = "\x1f"  # ASCII unit separator; cannot appear in the JSON above


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def policy_digest(policy: dict | None) -> str:
    """Digest of the effective policy. `none` when running without one."""
    if not policy:
        return "none"
    return "sha256:" + sha256_of(canonical_json(policy))


def evidence_digest(
    bundle: dict,
    *,
    policy: dict | None = None,
    engine_version: str,
    model_pin: str = "none",
    prompt_version: str = "0",
) -> str:
    payload = SEPARATOR.join(
        [
            canonical_json(strip_for_digest(bundle)),
            policy_digest(policy),
            engine_version,
            model_pin,
            prompt_version,
        ]
    )
    return "sha256:" + sha256_of(payload)
