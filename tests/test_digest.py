from tickmark.evidence.canonical import canonicalize
from tickmark.evidence.digest import evidence_digest, policy_digest


def digest(bundle, **kwargs):
    kwargs.setdefault("engine_version", "0.0.1")
    return evidence_digest(bundle, **kwargs)


class TestStability:
    def test_same_bundle_same_digest(self, bundle):
        assert digest(bundle) == digest(bundle)

    def test_collected_at_does_not_affect_digest(self, bundle):
        a = digest(bundle)
        bundle["source"]["collected_at"] = "2099-01-01T00:00:00Z"
        assert digest(bundle) == a

    def test_input_ordering_does_not_affect_digest(self, bundle):
        import copy

        shuffled = copy.deepcopy(bundle)
        shuffled["files"].reverse()
        assert digest(canonicalize(bundle)) == digest(canonicalize(shuffled))

    def test_format_is_prefixed_sha256(self, bundle):
        value = digest(bundle)
        assert value.startswith("sha256:")
        assert len(value) == len("sha256:") + 64


class TestSensitivity:
    def test_content_change_changes_digest(self, bundle):
        a = digest(bundle)
        bundle["pr"]["body"] = "different"
        assert digest(bundle) != a

    def test_engine_version_changes_digest(self, bundle):
        assert digest(bundle, engine_version="0.0.1") != digest(bundle, engine_version="0.0.2")

    def test_model_pin_changes_digest(self, bundle):
        """A different model must not reuse a cached verdict."""
        assert digest(bundle, model_pin="none") != digest(bundle, model_pin="qwen3:8b")

    def test_prompt_version_changes_digest(self, bundle):
        """Editing a prompt during tuning must invalidate the cache, or you are
        measuring a stale prompt."""
        assert digest(bundle, prompt_version="1") != digest(bundle, prompt_version="2")

    def test_policy_changes_digest(self, bundle):
        a = digest(bundle, policy={"controls": [{"id": "CM-1"}]})
        b = digest(bundle, policy={"controls": [{"id": "CM-2"}]})
        assert a != b


class TestPolicyDigest:
    def test_none_policy_is_literal_none(self):
        assert policy_digest(None) == "none"
        assert policy_digest({}) == "none"

    def test_key_order_does_not_matter(self):
        assert policy_digest({"a": 1, "b": 2}) == policy_digest({"b": 2, "a": 1})
