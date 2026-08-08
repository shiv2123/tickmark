from tickmark.evidence.derive import ScopeConfig, derive


class TestRevertDetection:
    def test_title_prefix(self, bundle):
        bundle["pr"]["title"] = 'Revert "feat: add thing"'
        assert derive(bundle)["is_revert"] is True

    def test_body_marker(self, bundle):
        bundle["pr"]["body"] = "This reverts commit abc1234."
        assert derive(bundle)["is_revert"] is True

    def test_ordinary_pr_is_not_a_revert(self, bundle):
        assert derive(bundle)["is_revert"] is False

    def test_word_reverted_in_prose_does_not_trigger(self, bundle):
        bundle["pr"]["title"] = "Fix the thing we reverted last week"
        assert derive(bundle)["is_revert"] is False


class TestPathClassification:
    def test_production_and_test_paths_separated(self, bundle):
        out = derive(bundle)
        assert out["production_paths_touched"] == ["src/tickmark/checks/cm2.py"]
        assert out["test_paths_touched"] == ["tests/test_cm2.py"]

    def test_all_files_exempt_when_docs_only(self, bundle):
        bundle["files"] = [
            {"path": "README.md", "status": "modified", "additions": 1, "deletions": 0,
             "is_rename_only": False, "patch": None, "patch_truncated": False, "previous_path": None}
        ]
        assert derive(bundle)["all_files_exempt"] is True

    def test_all_files_exempt_false_when_any_file_is_not(self, bundle):
        assert derive(bundle)["all_files_exempt"] is False

    def test_empty_pr_is_not_all_exempt(self, bundle):
        """Zero files must not read as 'everything is exempt'."""
        bundle["files"] = []
        assert derive(bundle)["all_files_exempt"] is False

    def test_rename_only_detected(self, bundle):
        for f in bundle["files"]:
            f["is_rename_only"] = True
        assert derive(bundle)["has_only_rename_changes"] is True

    def test_custom_scope_config_is_honoured(self, bundle):
        scope = ScopeConfig(production_paths=["tests/**"], test_paths=[])
        assert derive(bundle, scope)["production_paths_touched"] == ["tests/test_cm2.py"]


class TestIdentities:
    def test_author_included(self, bundle):
        assert 100 in derive(bundle)["author_and_co_author_ids"]

    def test_commit_committer_included(self, bundle):
        bundle["commits"][0]["committer_id"] = 999
        assert 999 in derive(bundle)["author_and_co_author_ids"]

    def test_reviewer_not_included(self, bundle):
        """Reviewer 200 is independent and must not be folded into authorship."""
        assert 200 not in derive(bundle)["author_and_co_author_ids"]

    def test_co_author_emails_collected(self, bundle):
        bundle["commits"][0]["co_author_emails"] = ["b@x.com", "a@x.com"]
        assert derive(bundle)["co_author_emails"] == ["a@x.com", "b@x.com"]

    def test_null_ids_do_not_appear(self, bundle):
        bundle["commits"][0]["author_id"] = None
        assert None not in derive(bundle)["author_and_co_author_ids"]


class TestWorkItemRefs:
    def test_found_in_body(self, bundle):
        assert "OPS-1421" in derive(bundle)["work_item_refs"]

    def test_found_in_commit_message(self, bundle):
        bundle["pr"]["body"] = ""
        bundle["commits"][0]["message_subject"] = "JIRA-99 do the thing"
        assert "JIRA-99" in derive(bundle)["work_item_refs"]

    def test_absent_when_nothing_matches(self, bundle):
        bundle["pr"]["body"] = "no reference here"
        bundle["pr"]["title"] = "a change"
        bundle["commits"][0]["message_subject"] = "a change"
        assert derive(bundle)["work_item_refs"] == []

    def test_deduplicated_and_sorted(self, bundle):
        bundle["pr"]["body"] = "OPS-2 and OPS-1 and OPS-2"
        assert derive(bundle)["work_item_refs"] == ["OPS-1", "OPS-2"]

    def test_invalid_pattern_returns_empty_rather_than_raising(self, bundle):
        assert derive(bundle, ScopeConfig(work_item_pattern="([unclosed"))["work_item_refs"] == []


class TestCounts:
    def test_totals(self, bundle):
        out = derive(bundle)
        assert out["file_count"] == 2
        assert out["total_additions"] == 124
        assert out["total_deletions"] == 0

    def test_last_production_commit_is_the_newest(self, bundle):
        bundle["commits"].append({**bundle["commits"][0], "sha": "d" * 40,
                                  "authored_at": "2026-08-04T10:00:00Z"})
        assert derive(bundle)["last_production_commit_at"] == "2026-08-04T10:00:00Z"


class TestPurity:
    def test_derive_does_not_mutate(self, bundle):
        import copy

        before = copy.deepcopy(bundle)
        derive(bundle)
        assert bundle == before

    def test_repeated_calls_agree(self, bundle):
        assert derive(bundle) == derive(bundle)
