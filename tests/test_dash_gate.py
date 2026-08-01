"""Tests for the ASCII dash gate (FOLLOWUPS entry 41).

The gate was installed while the tree measured **zero** violations, which is
the cheapest moment to add one -- it ships green with no accompanying sweep.
That is also what makes it dangerous to trust: a gate that returns 0 on a
clean tree returns 0 whether or not it works. Every test here therefore feeds
it input that must fail, alongside input that must pass.
"""

from __future__ import annotations

from scripts.dash_gate import check_config, check_python

EM = "\u2014"
EN = "\u2013"


class TestPythonClassification:
    """Only COMMENT and docstring STRING tokens may be flagged."""

    def test_em_dash_in_a_comment_is_flagged(self) -> None:
        """A comment is prose and must use '--'."""
        source = f"x = 1  # a dash {EM} here\n"
        assert len(check_python("f.py", source)) == 1

    def test_en_dash_in_a_comment_is_flagged(self) -> None:
        """The rule covers U+2013 as well as U+2014."""
        source = f"x = 1  # a range 1{EN}5\n"
        assert len(check_python("f.py", source)) == 1

    def test_em_dash_in_a_module_docstring_is_flagged(self) -> None:
        """The module docstring is the first statement of a Module."""
        source = f'"""Title {EM} subtitle."""\nx = 1\n'
        assert len(check_python("f.py", source)) == 1

    def test_em_dash_in_a_function_docstring_is_flagged(self) -> None:
        """Function docstrings are in scope too."""
        source = f'def f():\n    """Do a thing {EM} carefully."""\n    return 1\n'
        assert len(check_python("f.py", source)) == 1

    def test_em_dash_in_a_class_docstring_is_flagged(self) -> None:
        """So are class docstrings."""
        source = f'class C:\n    """A thing {EM} of sorts."""\n'
        assert len(check_python("f.py", source)) == 1

    def test_multiline_docstring_body_is_flagged(self) -> None:
        """The dash may be on any line of the docstring, not just the first."""
        source = f'def f():\n    """Summary.\n\n    Detail {EM} more.\n    """\n    return 1\n'
        assert len(check_python("f.py", source)) == 1


class TestPythonExemptions:
    """Exemption 1, 2 and 3: the dash is data, not prose."""

    def test_program_output_is_not_flagged(self) -> None:
        """Exemption 1: a string that reaches a terminal or a written file."""
        source = f'print("""query-doctor {EM} Quick Start""")\n'
        assert check_python("f.py", source) == []

    def test_svg_title_argument_is_not_flagged(self) -> None:
        """Exemption 1 as it appears in examples/generate_svgs.py."""
        source = f'create_terminal_svg(title="query-doctor {EM} Test Usage")\n'
        assert check_python("f.py", source) == []

    def test_test_fixture_literal_is_not_flagged(self) -> None:
        """Exemption 2: an expected value is the thing under test."""
        source = f'fixed_line = "# TODO: index via Meta.indexes {EM} add one"\n'
        assert check_python("f.py", source) == []

    def test_regex_character_class_is_not_flagged(self) -> None:
        """Exemption 3: a functional literal matching real repo prose."""
        source = f'PATTERN = re.compile(r"[{EM}{EN}]")\n'
        assert check_python("f.py", source) == []

    def test_a_clean_file_produces_nothing(self) -> None:
        """Negative control for the whole classifier."""
        source = '"""Title -- subtitle."""\n\n\ndef f():\n    # plain -- comment\n    return 1\n'
        assert check_python("f.py", source) == []


class TestConfigClassification:
    """Config files have no token kinds, so they use an explicit allowlist."""

    def test_dash_in_config_is_flagged(self) -> None:
        """An unlisted dash in a config file fails."""
        assert len(check_config("some.toml", f"name = 'a {EM} b'\n")) == 1

    def test_allowlisted_line_is_not_flagged(self) -> None:
        """The two known program-output lines are exempt, by exact content."""
        line = "  Detects N+1s, duplicates, missing indexes, and more \u2014 with exact"
        assert check_config("mkdocs.yml", line + "\n") == []

    def test_allowlist_is_keyed_on_the_whole_line(self) -> None:
        """A different dash on the same file's other lines still fails.

        Keying on the exact line means the exemption cannot silently widen to
        cover new prose added beside it.
        """
        assert len(check_config("mkdocs.yml", f"site_name: a {EM} b\n")) == 1

    def test_clean_config_produces_nothing(self) -> None:
        """Negative control for the config path."""
        assert check_config("some.toml", "name = 'a -- b'\n") == []


class TestTreeIsClean:
    """The tracked tree must stay at zero, which is the gate's whole point."""

    def test_gate_returns_zero_on_the_real_tree(self) -> None:
        """Positive control lives in the classes above, not here."""
        from scripts.dash_gate import main

        assert main() == 0
