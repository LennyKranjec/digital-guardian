# ruff: noqa: S311  # deterministische Zufallsschleifen mit festem Seed, keine Kryptografie
"""Sicherer Ausdrucksparser: Korrektheit, Angriffsstrings, Monotonieprüfung, Round-Trip."""

import ast
import random
from pathlib import Path
from typing import Literal

import pytest

from waechter.triage import parser
from waechter.triage.parser import (
    Compare,
    Expr,
    ExpressionError,
    Logic,
    Not,
    Num,
    Var,
    evaluate,
    find_monotone_violation,
    names_under_not,
    parse,
    variables,
)

ENV = {"a": 2, "b": 0, "c": 3, "fever.present": 1, "diarrhea.grade": 2}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a >= 2", 1),
        ("a > 2", 0),
        ("a <= 2", 1),
        ("a < 2", 0),
        ("a == 2", 1),
        ("a != 2", 0),
        ("7", 7),
        ("b", 0),
        ("c", 3),
        ("fever.present", 1),
        ("diarrhea.grade >= 2 and fever.present", 1),
        ("diarrhea.grade >= 3 or fever.present", 1),
        ("diarrhea.grade >= 3 or b", 0),
        ("not b", 1),
        ("not a", 0),
        ("not not a", 1),
        ("a >= 1 or b >= 1 and c >= 9", 1),  # and bindet stärker als or
        ("(a >= 1 or b >= 1) and c >= 9", 0),
        ("((a >= 2))", 1),
        ("  a   >=\t2  ", 1),
        ("a >= 2 and b >= 0 and c >= 3", 1),
        ("not (a >= 3 or c >= 4)", 1),
    ],
)
def test_parser_evaluates_correctly(text: str, expected: int) -> None:
    assert evaluate(parse(text), ENV) == expected


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('echo x')",
        "__import__",
        "a.__class__",
        "a.__dict__",
        "a.b.c",
        "a.",
        ".a",
        "open('f')",
        "a(1)",
        "a()",
        "'text'",
        '"text"',
        "a; b",
        "a, b",
        "lambda: 1",
        "[1, 2]",
        "{1: 2}",
        "a[0]",
        "a if b else c",
        "a + 1",
        "a - 1",
        "a * 2",
        "a ** 2",
        "a // 2",
        "a & b",
        "a | b",
        "~a",
        "a = 1",
        "a := 1",
        "a >= 1 >= 0",
        "a >= ",
        ">= 1",
        "a >= 1)",
        "(a >= 1",
        "()",
        "",
        "   ",
        "not",
        "and",
        "a and",
        "a or or b",
        "a >= 99999",
        "a >= 1.5",
        "ä >= 1",
        "a >= 1 # kommentar",
        "a\n>= 1; import os",
        "x" * 500,
        "(" * 40 + "a" + ")" * 40,
        "not " * 40 + "a",
    ],
)
def test_attack_and_malformed_strings_raise(text: str) -> None:
    with pytest.raises(ExpressionError):
        parse(text)


def test_error_messages_do_not_echo_the_expression() -> None:
    marker = "geheim_marker"
    with pytest.raises(ExpressionError) as caught:
        parse(f"{marker}( 1 )")
    assert marker not in str(caught.value)


def test_attack_string_is_never_executed(tmp_path: Path) -> None:
    marker = tmp_path / "pwned"
    with pytest.raises(ExpressionError):
        parse(f"__import__('os').system('echo x > {marker.as_posix()}')")
    assert not marker.exists()


def test_unknown_name_is_an_error_at_evaluation() -> None:
    with pytest.raises(ExpressionError):
        evaluate(parse("nope >= 1"), {})


def test_module_uses_no_dynamic_execution() -> None:
    source = Path(parser.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned = {"eval", "exec", "compile", "__import__", "getattr", "open"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & banned
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported <= {"itertools", "re"}


def test_variables_and_names_under_not() -> None:
    expr = parse("a >= 1 and not (b >= 2 or a >= 3) and c")
    assert variables(expr) == ("a", "b", "c")
    assert names_under_not(expr) == {"a", "b"}
    assert names_under_not(parse("a >= 1 and b >= 2")) == frozenset()


@pytest.mark.parametrize(
    ("text", "monotone"),
    [
        ("a >= 1", True),
        ("a > 1 or b >= 2", True),
        ("a >= 1 and b >= 2", True),
        ("a >= 1 and (b >= 1 or c >= 2)", True),
        ("a <= 1", False),
        ("a < 2", False),
        ("a == 1", False),
        ("a != 1", False),
        ("not a >= 1", False),
        ("a >= 1 and not b >= 1", False),
        ("a >= 1 or b <= 0", False),
    ],
)
def test_monotone_check(text: str, monotone: bool) -> None:
    found = find_monotone_violation(parse(text), {"a": 3, "b": 3, "c": 3})
    assert (found is None) is monotone


def test_monotone_check_needs_domains_and_bounds_the_grid() -> None:
    with pytest.raises(ExpressionError):
        find_monotone_violation(parse("a >= 1"), {})
    with pytest.raises(ExpressionError):
        find_monotone_violation(parse("a >= 1 and b >= 1"), {"a": 1000, "b": 1000}, max_points=1000)


# ---- Round-Trip mit Zufallsausdrücken (fester Seed) -------------------------------------------
NAMES = ["a", "b", "c", "x.grade", "y.present"]


def _random_expr(rng: random.Random, depth: int) -> Expr:
    roll = rng.random()
    if depth <= 0 or roll < 0.25:
        leaf = rng.choice([*NAMES, ""])
        return Num(rng.randint(0, 4)) if leaf == "" else Var(leaf)
    if roll < 0.45:
        return Not(_random_expr(rng, depth - 1))
    if roll < 0.7:
        op = rng.choice(["<", "<=", ">", ">=", "==", "!="])
        return Compare(op, _random_expr(rng, 0), _random_expr(rng, 0))
    op2: Literal["and", "or"] = "and" if rng.random() < 0.5 else "or"
    return Logic(op2, _random_expr(rng, depth - 1), _random_expr(rng, depth - 1))


def _render(expr: Expr) -> str:
    if isinstance(expr, Num):
        return str(expr.value)
    if isinstance(expr, Var):
        return expr.name
    if isinstance(expr, Not):
        return f"not ({_render(expr.operand)})"
    return f"({_render(expr.left)} {expr.op} {_render(expr.right)})"


def _direct(expr: Expr, env: dict[str, int]) -> int:
    """Unabhängige Referenzauswertung direkt auf dem Baum (ohne den Parser)."""
    if isinstance(expr, Num):
        return expr.value
    if isinstance(expr, Var):
        return env[expr.name]
    if isinstance(expr, Not):
        return int(not _direct(expr.operand, env))
    if isinstance(expr, Logic):
        left, right = _direct(expr.left, env), _direct(expr.right, env)
        return (
            int(bool(left) and bool(right)) if expr.op == "and" else int(bool(left) or bool(right))
        )
    left, right = _direct(expr.left, env), _direct(expr.right, env)
    return int(
        {
            "<": left < right,
            "<=": left <= right,
            ">": left > right,
            ">=": left >= right,
            "==": left == right,
            "!=": left != right,
        }[expr.op]
    )


def test_roundtrip_of_random_expressions_matches_reference() -> None:
    rng = random.Random(20261016)
    checked = 0
    for _ in range(2500):
        tree = _random_expr(rng, 4)
        text = _render(tree)
        parsed = parse(text)
        for _ in range(3):
            env = {name: rng.randint(0, 4) for name in NAMES}
            assert evaluate(parsed, env) == _direct(tree, env)
            checked += 1
    assert checked == 7500


@pytest.mark.parametrize("char", [0xFF11, 0x0661, 0x00B2, 0x00A0, 0x2003])
def test_only_ascii_digits_and_whitespace_are_accepted(char: int) -> None:
    """Unicode-Ziffern (Vollbreite, arabisch-indisch, hochgestellt) und Leerraum ⇒ Fehler."""
    glyph = chr(char)
    for text in (f"a >= {glyph}", f"a >= 1{glyph}", f"a{glyph}>= 1"):
        with pytest.raises(ExpressionError):
            parse(text)
