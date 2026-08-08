import copy

from tickmark.evidence.canonical import (
    canonical_json,
    canonicalize,
    normalize_timestamp,
    strip_for_digest,
    truncate_patch,
)


class TestNormalizeTimestamp:
    def test_passes_through_canonical_form(self):
        assert normalize_timestamp("2026-08-03T14:02:00Z") == "2026-08-03T14:02:00Z"

    def test_converts_offset_to_utc(self):
        assert normalize_timestamp("2026-08-03T10:02:00-04:00") == "2026-08-03T14:02:00Z"

    def test_drops_subsecond_precision(self):
        assert normalize_timestamp("2026-08-03T14:02:00.123456Z") == "2026-08-03T14:02:00Z"

    def test_naive_input_is_assumed_utc(self):
        assert normalize_timestamp("2026-08-03T14:02:00") == "2026-08-03T14:02:00Z"

    def test_none_and_empty_pass_through(self):
        assert normalize_timestamp(None) is None
        assert normalize_timestamp("") is None

    def test_unparseable_is_returned_verbatim_not_dropped(self):
        assert normalize_timestamp("not a date") == "not a date"


class TestTruncatePatch:
    def test_short_patch_untouched(self):
        patch, truncated = truncate_patch("a\nb\nc", max_lines=10)
        assert patch == "a\nb\nc"
        assert truncated is False

    def test_long_patch_cut_and_flagged(self):
        patch, truncated = truncate_patch("\n".join(str(i) for i in range(50)), max_lines=10)
        assert patch.split("\n") == [str(i) for i in range(10)]
        assert truncated is True

    def test_truncation_is_deterministic(self):
        text = "\n".join(str(i) for i in range(500))
        assert truncate_patch(text, 200) == truncate_patch(text, 200)

    def test_none_patch(self):
        assert truncate_patch(None) == (None, False)


class TestCanonicalize:
    def test_does_not_mutate_input(self, bundle):
        before = copy.deepcopy(bundle)
        canonicalize(bundle)
        assert bundle == before

    def test_files_sorted_by_path(self, bundle):
        bundle["files"].reverse()
        out = canonicalize(bundle)
        assert [f["path"] for f in out["files"]] == sorted(f["path"] for f in out["files"])

    def test_input_order_does_not_change_output(self, bundle):
        shuffled = copy.deepcopy(bundle)
        shuffled["files"].reverse()
        shuffled["checks"] = list(reversed(shuffled["checks"]))
        assert canonical_json(canonicalize(bundle)) == canonical_json(canonicalize(shuffled))

    def test_labels_sorted(self, bundle):
        bundle["pr"]["labels"] = ["z", "a", "m"]
        assert canonicalize(bundle)["pr"]["labels"] == ["a", "m", "z"]

    def test_co_author_emails_deduplicated_and_sorted(self, bundle):
        bundle["commits"][0]["co_author_emails"] = ["z@x.com", "a@x.com", "z@x.com"]
        assert canonicalize(bundle)["commits"][0]["co_author_emails"] == ["a@x.com", "z@x.com"]

    def test_sorting_tolerates_null_keys(self, bundle):
        """Real payloads have null timestamps. Sorting must not raise."""
        bundle["reviews"].append(
            {
                "id": 1,
                "reviewer_id": 300,
                "reviewer_is_bot": False,
                "state": "PENDING",
                "submitted_at": None,
                "dismissed_at": None,
                "commit_sha": None,
            }
        )
        assert len(canonicalize(bundle)["reviews"]) == 2

    def test_timestamps_normalized_throughout(self, bundle):
        bundle["pr"]["created_at"] = "2026-08-03T10:02:00.9-04:00"
        bundle["reviews"][0]["submitted_at"] = "2026-08-04T08:12:00.5Z"
        out = canonicalize(bundle)
        assert out["pr"]["created_at"] == "2026-08-03T14:02:00Z"
        assert out["reviews"][0]["submitted_at"] == "2026-08-04T08:12:00Z"


class TestCanonicalJson:
    def test_keys_sorted_and_compact(self):
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_stable_across_equal_dicts_built_differently(self):
        first = {"a": 1}
        first["b"] = 2
        second = {"b": 2}
        second["a"] = 1
        assert canonical_json(first) == canonical_json(second)

    def test_unicode_preserved_not_escaped(self):
        assert canonical_json({"k": "café"}) == '{"k":"café"}'


class TestStripForDigest:
    def test_removes_collected_at(self, bundle):
        bundle["source"]["collected_at"] = "2026-08-05T22:14:00Z"
        assert "collected_at" not in strip_for_digest(bundle)["source"]

    def test_leaves_everything_else(self, bundle):
        out = strip_for_digest(bundle)
        assert out["source"]["head_sha"] == bundle["source"]["head_sha"]

    def test_does_not_mutate_input(self, bundle):
        bundle["source"]["collected_at"] = "2026-08-05T22:14:00Z"
        strip_for_digest(bundle)
        assert "collected_at" in bundle["source"]
