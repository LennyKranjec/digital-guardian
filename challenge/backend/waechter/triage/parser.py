"""Sicherer Ausdrucksparser für Lehrerregeln, Böden und Eskalationsbedingungen (kein `eval`).

Grammatik (Tokenizer + rekursiver Abstieg):

    expr    := or_expr
    or_expr := and_expr ("or" and_expr)*
    and_expr:= not_expr ("and" not_expr)*
    not_expr:= "not" not_expr | compare
    compare := atom (("<" | "<=" | ">" | ">=" | "==" | "!=") atom)?
    atom    := NUMBER | NAME | "(" expr ")"

`NAME` ist ein Bezeichner oder `symptom.grade` / `symptom.present` (genau ein Punkt). Alle Werte
sind ganze Zahlen; Vergleiche und Logik liefern 0/1. Es gibt weder Aufrufe noch Attribute,
Zeichenketten oder Operatoren außer den oben genannten: alles andere ist ein
`ExpressionError`. Länge und Verschachtelungstiefe sind begrenzt. Fehlermeldungen nennen die
Position, nie den Ausdruckstext.
"""

import itertools
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final, Literal

MAX_LENGTH: Final = 400
MAX_DEPTH: Final = 32
MAX_NUMBER_DIGITS: Final = 4
KEYWORDS: Final = frozenset({"and", "or", "not"})


class ExpressionError(ValueError):
    """Ausdruck ist syntaktisch, strukturell oder semantisch unzulässig."""


type Expr = Num | Var | Not | Logic | Compare


@dataclass(frozen=True)
class Num:
    value: int


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Not:
    operand: Expr


@dataclass(frozen=True)
class Logic:
    op: Literal["and", "or"]
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Compare:
    op: str
    left: Expr
    right: Expr


_ASCII_SPACE = " \t\n\r\f\v"  # wie \s mit re.ASCII
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_TOKEN = re.compile(
    rf"\s*(?:(?P<num>[0-9]+)|(?P<name>{_IDENT}(?:\.{_IDENT})?)|(?P<op><=|>=|==|!=|<|>)|(?P<par>[()]))",
    re.ASCII,  # Zahlen und Namen nur ASCII; Unicode-Ziffern und -Leerraum sind Fehler (A3 F-02)
)


@dataclass(frozen=True)
class _Token:
    kind: str  # num | name | op | par | kw | end
    text: str
    pos: int


def _tokenize(text: str) -> list[_Token]:
    if len(text) > MAX_LENGTH:
        raise ExpressionError("expression too long")
    tokens: list[_Token] = []
    pos = 0
    while True:
        if not text[pos:].strip(_ASCII_SPACE):
            tokens.append(_Token("end", "", len(text)))
            return tokens
        match = _TOKEN.match(text, pos)
        if match is None:
            raise ExpressionError(f"illegal character at position {pos}")
        kind = match.lastgroup or ""
        value = match.group(kind)
        start = match.start(kind)
        if kind == "num" and len(value) > MAX_NUMBER_DIGITS:
            raise ExpressionError(f"number too long at position {start}")
        if kind == "name":
            if "__" in value:
                raise ExpressionError(f"reserved name at position {start}")
            if value in KEYWORDS:
                kind = "kw"
        tokens.append(_Token(kind, value, start))
        pos = match.end()


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self._tokens = tokens
        self._index = 0
        self._depth = 0

    def _peek(self) -> _Token:
        return self._tokens[self._index]

    def _next(self) -> _Token:
        token = self._tokens[self._index]
        if token.kind != "end":
            self._index += 1
        return token

    def _enter(self) -> None:
        self._depth += 1
        if self._depth > MAX_DEPTH:
            raise ExpressionError("expression nested too deeply")

    def parse(self) -> Expr:
        expr = self._or()
        end = self._peek()
        if end.kind != "end":
            raise ExpressionError(f"unexpected token at position {end.pos}")
        return expr

    def _is_keyword(self, word: str) -> bool:
        token = self._peek()
        return token.kind == "kw" and token.text == word

    def _or(self) -> Expr:
        left = self._and()
        while self._is_keyword("or"):
            self._next()
            left = Logic("or", left, self._and())
        return left

    def _and(self) -> Expr:
        left = self._not()
        while self._is_keyword("and"):
            self._next()
            left = Logic("and", left, self._not())
        return left

    def _not(self) -> Expr:
        if self._is_keyword("not"):
            self._next()
            self._enter()
            try:
                return Not(self._not())
            finally:
                self._depth -= 1
        return self._compare()

    def _compare(self) -> Expr:
        left = self._atom()
        token = self._peek()
        if token.kind == "op":
            self._next()
            return Compare(token.text, left, self._atom())
        return left

    def _atom(self) -> Expr:
        token = self._next()
        if token.kind == "num":
            return Num(int(token.text))
        if token.kind == "name":
            return Var(token.text)
        if token.kind == "par" and token.text == "(":
            self._enter()
            try:
                inner = self._or()
            finally:
                self._depth -= 1
            closing = self._next()
            if closing.kind != "par" or closing.text != ")":
                raise ExpressionError(f"expected ')' at position {closing.pos}")
            return inner
        raise ExpressionError(f"unexpected token at position {token.pos}")


def parse(text: str) -> Expr:
    """Parst `text` zu einem Ausdrucksbaum oder wirft `ExpressionError`."""
    return _Parser(_tokenize(text)).parse()


def evaluate(expr: Expr, env: Mapping[str, int]) -> int:
    """Wertet `expr` mit den Variablenwerten aus `env` aus (Ganzzahl; Wahrheitswerte 0/1)."""
    if isinstance(expr, Num):
        return expr.value
    if isinstance(expr, Var):
        try:
            return env[expr.name]
        except KeyError:
            raise ExpressionError("unknown name") from None
    if isinstance(expr, Not):
        return 0 if evaluate(expr.operand, env) else 1
    if isinstance(expr, Logic):
        left = evaluate(expr.left, env) != 0
        if expr.op == "and":
            return int(left and evaluate(expr.right, env) != 0)
        return int(left or evaluate(expr.right, env) != 0)
    a, b = evaluate(expr.left, env), evaluate(expr.right, env)
    results = {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}
    return int(results[expr.op])


def variables(expr: Expr) -> tuple[str, ...]:
    """Namen im Ausdruck in Reihenfolge des ersten Auftretens, ohne Duplikate."""
    found: dict[str, None] = {}

    def walk(node: Expr) -> None:
        if isinstance(node, Var):
            found.setdefault(node.name)
        elif isinstance(node, Not):
            walk(node.operand)
        elif isinstance(node, Logic | Compare):
            walk(node.left)
            walk(node.right)

    walk(expr)
    return tuple(found)


def names_under_not(expr: Expr) -> frozenset[str]:
    """Namen unterhalb eines `not` (für das Verbot von `not` auf Aggregaten)."""
    found: set[str] = set()

    def walk(node: Expr, negated: bool) -> None:
        if isinstance(node, Var):
            if negated:
                found.add(node.name)
        elif isinstance(node, Not):
            walk(node.operand, True)
        elif isinstance(node, Logic | Compare):
            walk(node.left, negated)
            walk(node.right, negated)

    walk(expr, False)
    return frozenset(found)


def grid_points(domains: Mapping[str, int], max_points: int) -> Iterator[dict[str, int]]:
    """Alle Punkte des Produktgitters `0..domain` je Name; `ExpressionError` bei Überschreitung."""
    names = sorted(domains)
    size = 1
    for name in names:
        size *= domains[name] + 1
        if size > max_points:
            raise ExpressionError("grid too large")
    for values in itertools.product(*(range(domains[n] + 1) for n in names)):
        yield dict(zip(names, values, strict=True))


def find_monotone_violation(
    expr: Expr, domains: Mapping[str, int], max_points: int = 200_000
) -> str | None:
    """Prüft „Wert + 1 senkt das Ergebnis nie“ an jedem Einzelschritt-Nachbarn des Gitters.

    `domains` gibt je Name den größten Wert (Gitter `0..domain`); ein Name ohne Eintrag ist ein
    Fehler. Liefert eine Beschreibung des ersten Verstoßes (Name, Schritt) oder `None`.
    """
    used = variables(expr)
    if any(name not in domains for name in used):
        raise ExpressionError("name without domain")
    sub = {name: domains[name] for name in used}
    for point in grid_points(sub, max_points):
        if evaluate(expr, point) == 0:
            continue
        for name in used:
            if point[name] < sub[name]:
                higher = dict(point)
                higher[name] += 1
                if evaluate(expr, higher) == 0:
                    return f"{name} {point[name]}->{higher[name]}"
    return None
