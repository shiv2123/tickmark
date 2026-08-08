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
    """A configured pattern is required. See DEFAULT_WORK_ITEM_PATTERN for why."""

    OPS = ScopeConfig(work_item_pattern=r"(?:OPS|JIRA|CHG)-\d+")

    def test_no_pattern_configured_yields_nothing(self, bundle):
        assert derive(bundle)["work_item_refs"] == []
        assert derive(bundle)["work_item_pattern_configured"] is False

    def test_found_in_body_when_configured(self, bundle):
        assert "OPS-1421" in derive(bundle, self.OPS)["work_item_refs"]
        assert derive(bundle, self.OPS)["work_item_pattern_configured"] is True

    def test_found_in_commit_message(self, bundle):
        bundle["pr"]["body"] = ""
        bundle["commits"][0]["message_subject"] = "JIRA-99 do the thing"
        assert "JIRA-99" in derive(bundle, self.OPS)["work_item_refs"]

    def test_absent_when_nothing_matches(self, bundle):
        bundle["pr"]["body"] = "no reference here"
        bundle["pr"]["title"] = "a change"
        bundle["commits"][0]["message_subject"] = "a change"
        bundle["linked_issues"] = []
        assert derive(bundle, self.OPS)["work_item_refs"] == []

    def test_deduplicated_and_sorted(self, bundle):
        bundle["pr"]["body"] = "OPS-2 and OPS-1 and OPS-2"
        bundle["linked_issues"] = []
        assert derive(bundle, self.OPS)["work_item_refs"] == ["OPS-1", "OPS-2"]

    def test_invalid_pattern_returns_empty_rather_than_raising(self, bundle):
        assert derive(bundle, ScopeConfig(work_item_pattern="([unclosed"))["work_item_refs"] == []

    def test_permissive_pattern_matches_noise(self, bundle):
        """Regression guard for the bug that removed the default.

        A naive pattern cannot separate a ticket key from an encoding name, and
        a control satisfied by noise launders absence of evidence into a pass.
        """
        loose = ScopeConfig(work_item_pattern=r"(?:[A-Z][A-Z0-9]+-\d+)")
        bundle["pr"]["body"] = "encode as UTF-8 and hash with SHA-256"
        bundle["pr"]["title"] = "a change"
        bundle["commits"][0]["message_subject"] = "a change"
        bundle["linked_issues"] = []
        assert derive(bundle, loose)["work_item_refs"] == ["SHA-256", "UTF-8"]


class TestCounts:
    def test_totals(self, bundle):
        out = derive(bundle)
        assert out["file_count"] == 2
        assert out["total_additions"] == 124
        assert out["total_deletions"] == 0


class TestCommitTimestamps:
    """Author date and commit date are different facts and the difference is
    load-bearing for staleness. Author date survives rebase, amend, and
    cherry-pick; commit date does not. A branch rebased after an approval keeps
    its old author dates and would read as fresh."""

    def test_last_commit_at_uses_commit_date_not_author_date(self, bundle):
        bundle["commits"].append({
            **bundle["commits"][0],
            "sha": "d" * 40,
            "sequence": 1,
            "parents": ["c" * 40],
            "authored_at": "2026-08-01T09:00:00Z",   # written earlier
            "committed_at": "2026-08-04T10:00:00Z",  # rebased onto the branch later
        })
        out = derive(bundle)
        assert out["last_commit_at"] == "2026-08-04T10:00:00Z"
        assert out["last_authored_at"] == "2026-08-03T13:50:00Z"

    def test_unparseable_timestamp_yields_none_not_garbage(self, bundle):
        """Canonicalization passes an unparseable timestamp through verbatim.
        A raw string max would return it, since letters sort above digits, and a
        check would then compare against nonsense. None means unknown, and
        unknown must reach the check as unknown."""
        bundle["commits"][0]["committed_at"] = "not a date"
        assert derive(bundle)["last_commit_at"] is None

    def test_no_commits_yields_none(self, bundle):
        bundle["commits"] = []
        out = derive(bundle)
        assert out["last_commit_at"] is None
        assert out["head_commit_sha"] is None


class TestCommitOrder:
    """Branch order is what makes staleness answerable without trusting clocks.
    Canonicalization sorts commits by authored_at, so order has to survive in
    `sequence` and be checkable against `parents`."""

    def _append(self, bundle, sha, sequence, parents, authored_at):
        bundle["commits"].append({
            **bundle["commits"][0],
            "sha": sha, "sequence": sequence, "parents": parents,
            "authored_at": authored_at, "committed_at": authored_at,
        })

    def test_order_follows_sequence_not_array_position(self, bundle):
        self._append(bundle, "d" * 40, 1, ["c" * 40], "2026-08-04T10:00:00Z")
        bundle["commits"].reverse()
        out = derive(bundle)
        assert out["commit_shas_in_order"] == ["c" * 40, "d" * 40]
        assert out["head_commit_sha"] == "d" * 40

    def test_order_survives_a_commit_authored_out_of_order(self, bundle):
        """A cherry-picked commit carries an old author date. Sorting by
        authored_at would put it first; branch order says otherwise."""
        self._append(bundle, "d" * 40, 1, ["c" * 40], "2020-01-01T00:00:00Z")
        out = derive(bundle)
        assert out["commit_shas_in_order"] == ["c" * 40, "d" * 40]

    def test_chain_verifies_when_parents_link_up(self, bundle):
        self._append(bundle, "d" * 40, 1, ["c" * 40], "2026-08-04T10:00:00Z")
        assert derive(bundle)["commit_order_verified"] is True

    def test_merge_commit_verifies_via_first_parent(self, bundle):
        """Merging the base branch in gives a commit with two parents, one of
        which is outside the PR. One parent inside is enough."""
        self._append(bundle, "d" * 40, 1, ["c" * 40, "e" * 40], "2026-08-04T10:00:00Z")
        assert derive(bundle)["commit_order_verified"] is True

    def test_broken_chain_is_reported_not_hidden(self, bundle):
        """A parent that names nothing earlier means history was rewritten under
        us. Unverified must be visible so the check reports INDETERMINATE."""
        self._append(bundle, "d" * 40, 1, ["9" * 40], "2026-08-04T10:00:00Z")
        out = derive(bundle)
        assert out["commit_order_verified"] is False
        assert out["commit_shas_in_order"] == ["c" * 40, "d" * 40]

    def test_missing_parents_is_unverified(self, bundle):
        """An older bundle, or a collector that could not read parents. Absence
        of evidence must not read as a verified chain."""
        bundle["commits"][0]["parents"] = []
        assert derive(bundle)["commit_order_verified"] is False

    def test_missing_sequence_is_unverified(self, bundle):
        bundle["commits"][0].pop("sequence")
        assert derive(bundle)["commit_order_verified"] is False

    def test_empty_pr_is_unverified_not_vacuously_true(self, bundle):
        """Zero commits is not a verified order. It is no order at all."""
        bundle["commits"] = []
        out = derive(bundle)
        assert out["commit_order_verified"] is False
        assert out["commit_shas_in_order"] == []


class TestPurity:
    def test_derive_does_not_mutate(self, bundle):
        import copy

        before = copy.deepcopy(bundle)
        derive(bundle)
        assert bundle == before

    def test_repeated_calls_agree(self, bundle):
        assert derive(bundle) == derive(bundle)
