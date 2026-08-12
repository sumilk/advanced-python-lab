"""Grading suite for the Lintly capstone.

    uv run learn.py projects test lintly
"""
from __future__ import annotations

import textwrap

import pytest

from conftest import load

pytestmark = pytest.mark.project

lintly = load("lintly")


def lint(source, **kwargs):
    return lintly.lint(textwrap.dedent(source).strip("\n"), **kwargs)


def codes(findings):
    return [f.code for f in findings]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class TestRegistry:
    def test_builtin_rules_are_registered(self):
        expected = {"L101", "L102", "L103", "L104", "L105", "L106", "L107"}
        assert expected <= set(lintly.Rule.registry), sorted(lintly.Rule.registry)

    def test_registry_is_ordered_by_code(self):
        listed = list(lintly.Rule.registry)
        assert listed == sorted(listed)

    def test_subclassing_registers(self):
        class Novel(lintly.Rule):
            code = "L900"
            message = "novel"

            def check(self, tree, context):
                return []

        try:
            assert lintly.Rule.registry["L900"] is Novel
        finally:
            lintly.Rule.registry.pop("L900", None)

    def test_missing_code_or_message(self):
        with pytest.raises(TypeError):
            class NoCode(lintly.Rule):
                message = "x"

        with pytest.raises(TypeError):
            class NoMessage(lintly.Rule):
                code = "L901"

        lintly.Rule.registry.pop("L901", None)

    def test_duplicate_code(self):
        with pytest.raises(ValueError):
            class Clash(lintly.Rule):
                code = "L101"
                message = "clash"

    def test_abstract_opts_out_and_does_not_inherit(self):
        class Intermediate(lintly.Rule):
            abstract = True

        assert not any(r is Intermediate for r in lintly.Rule.registry.values())

        class Concrete(Intermediate):
            code = "L902"
            message = "concrete"

            def check(self, tree, context):
                return []

        try:
            assert lintly.Rule.registry["L902"] is Concrete, (
                "`abstract` must not be inherited by subclasses"
            )
        finally:
            lintly.Rule.registry.pop("L902", None)


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------
class TestFinding:
    def test_str_format(self):
        f = lintly.Finding("L101", 3, 4, "mutable default for 'items'", "app.py")
        assert str(f) == "app.py:3:4: L101 mutable default for 'items'"

    def test_sorting(self):
        a = lintly.Finding("L102", 1, 0, "x", "a.py")
        b = lintly.Finding("L101", 2, 0, "x", "a.py")
        c = lintly.Finding("L101", 2, 5, "x", "a.py")
        d = lintly.Finding("L101", 1, 0, "x", "b.py")
        assert sorted([d, c, b, a]) == [a, b, c, d]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
class TestRules:
    def test_l101_mutable_defaults(self):
        found = lint("""
            def a(x, items=[]): pass
            def b(x, opts={}): pass
            def c(x, s=set()): pass
            def d(x, made=list()): pass
            def e(x, fine=None): pass
            def f(x, *, kw=[]): pass
        """, select=["L101"])
        assert len(found) == 5, [str(f) for f in found]
        assert "items" in found[0].message
        assert found[0].line == 1

    def test_l102_bare_except(self):
        found = lint("""
            try:
                pass
            except ValueError:
                pass
            try:
                pass
            except:
                pass
        """, select=["L102"])
        assert len(found) == 1
        assert found[0].line == 7, found[0]

    def test_l103_complexity(self):
        source = """
            def simple():
                return 1

            def hairy(x):
                if x and x > 1:
                    for i in x:
                        if i:
                            while i:
                                i -= 1
                try:
                    pass
                except ValueError:
                    pass
                return [i for i in x if i]
        """
        assert lint(source, select=["L103"]) == []
        found = lint(source, select=["L103"], config={"max_complexity": 3})
        assert len(found) == 1
        assert "hairy" in found[0].message

    def test_l104_shadowed_builtins(self):
        found = lint("""
            list = [1]
            def f(dict, ok):
                type = 1
                return dict
        """, select=["L104"])
        names = {f.message.split("'")[1] for f in found}
        assert names == {"list", "dict", "type"}, names

    def test_l105_missing_docstring(self):
        found = lint('''
            def documented():
                """Yes."""

            def undocumented():
                pass

            def _private():
                pass

            class Documented:
                """Yes."""

            class Undocumented:
                pass
        ''', select=["L105"])
        reported = {f.message.split("'")[1] for f in found}
        assert reported == {"undocumented", "Undocumented"}, reported

    def test_l106_singleton_comparison(self):
        found = lint("""
            if x == None: pass
            if x is None: pass
            if x != True: pass
            if x == 3: pass
            if x == False: pass
        """, select=["L106"])
        assert len(found) == 3, [str(f) for f in found]
        assert {f.line for f in found} == {1, 3, 5}

    def test_l107_unused_imports(self):
        found = lint("""
            import os
            import sys
            import json.decoder
            from pathlib import Path, PurePath

            print(sys.argv, Path("."), json.decoder)
        """, select=["L107"])
        unused = {f.message.split("'")[1] for f in found}
        assert unused == {"os", "PurePath"}, unused

    def test_l107_counts_attribute_roots_as_usage(self):
        found = lint("""
            import os.path
            print(os.path.join("a"))
        """, select=["L107"])
        assert found == [], [str(f) for f in found]


# ---------------------------------------------------------------------------
# lint()
# ---------------------------------------------------------------------------
class TestLint:
    def test_results_are_sorted(self):
        found = lint("""
            def b(x=[]): pass

            try:
                pass
            except:
                pass
        """)
        lines = [f.line for f in found]
        assert lines == sorted(lines), [str(f) for f in found]

    def test_select_and_ignore(self):
        source = """
            import os

            def f(x=[]):
                try:
                    pass
                except:
                    pass
        """
        assert set(codes(lint(source, select=["L101"]))) == {"L101"}
        got = set(codes(lint(source, ignore=["L101", "L105", "L107"])))
        assert "L101" not in got and "L102" in got

    def test_select_beats_ignore(self):
        source = "def f(x=[]): pass"
        found = lint(source, select=["L101"], ignore=["L101"])
        assert codes(found) == ["L101"], "select should take precedence"

    def test_filename_is_carried(self):
        found = lint("def f(x=[]): pass", filename="app.py", select=["L101"])
        assert found[0].filename == "app.py"
        assert str(found[0]).startswith("app.py:1:")

    def test_config_reaches_rules(self):
        source = """
            def f(x):
                if x:
                    return 1
                return 2
        """
        assert lint(source, select=["L103"]) == []
        assert len(lint(source, select=["L103"], config={"max_complexity": 1})) == 1

    def test_syntax_error_becomes_a_finding(self):
        found = lint("def broken(:\n    pass\n")
        assert len(found) == 1
        assert found[0].code == "E999"
        assert "SyntaxError" in found[0].message

    def test_clean_source(self):
        found = lint('''
            """Module docstring."""
            import sys


            def main(argv=None):
                """Run."""
                if argv is None:
                    argv = sys.argv
                return len(argv)
        ''')
        assert found == [], [str(f) for f in found]


# ---------------------------------------------------------------------------
# noqa
# ---------------------------------------------------------------------------
class TestNoqa:
    def test_bare_noqa_suppresses_the_line(self):
        found = lint("def f(x=[]): pass  # noqa", select=["L101"])
        assert found == []

    def test_targeted_noqa(self):
        source = "def f(x=[]): pass  # noqa: L102"
        assert codes(lint(source, select=["L101"])) == ["L101"], (
            "a noqa naming a different code must not suppress this one"
        )
        assert lint("def f(x=[]): pass  # noqa: L101", select=["L101"]) == []

    def test_multiple_codes(self):
        source = """
            def f(x=[]): pass  # noqa: L101, L105
        """
        assert lint(source, select=["L101", "L105"]) == []

    def test_noqa_is_line_scoped(self):
        source = """
            def a(x=[]): pass  # noqa
            def b(x=[]): pass
        """
        found = lint(source, select=["L101"])
        assert len(found) == 1 and found[0].line == 2


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
class TestSummary:
    def test_counts_ordered_by_frequency(self):
        findings = [
            lintly.Finding("L102", 1, 0, "x"),
            lintly.Finding("L101", 2, 0, "x"),
            lintly.Finding("L101", 3, 0, "x"),
            lintly.Finding("L103", 4, 0, "x"),
        ]
        assert lintly.summary(findings) == {"L101": 2, "L102": 1, "L103": 1}

    def test_empty(self):
        assert lintly.summary([]) == {}
