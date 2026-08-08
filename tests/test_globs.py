from tickmark.evidence.globs import matches, matching


def test_star_does_not_cross_separators():
    """The reason we do not use fnmatch: it would match here, wrongly widening scope."""
    assert matches("src/a.py", ["src/*"])
    assert not matches("src/deep/a.py", ["src/*"])


def test_double_star_crosses_separators():
    assert matches("src/deep/nested/a.py", ["src/**"])
    assert matches("src/a.py", ["src/**"])


def test_leading_double_star_matches_zero_segments():
    assert matches("test_thing.py", ["**/test_*.py"])
    assert matches("a/b/test_thing.py", ["**/test_*.py"])


def test_question_mark_is_single_non_separator():
    assert matches("a1.py", ["a?.py"])
    assert not matches("a/1.py", ["a?.py"])


def test_literal_dots_are_escaped():
    assert matches("README.md", ["README.md"])
    assert not matches("READMExmd", ["README.md"])


def test_matching_returns_sorted_subset():
    paths = ["src/z.py", "docs/a.md", "src/a.py"]
    assert matching(paths, ["src/**"]) == ["src/a.py", "src/z.py"]


def test_no_patterns_matches_nothing():
    assert not matches("src/a.py", [])
