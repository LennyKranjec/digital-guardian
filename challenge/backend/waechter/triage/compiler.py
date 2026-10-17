"""Compiler: aus den Lehrerregeln eines Profils entstehen zwei exakte Entscheidungsbäume (§4).

Reines Python (keine neue Abhängigkeit). Je Komponente (Hook H3):

1. **Domänenkompression** (triage.md §7): ein Aggregat, das in allen Regeln nur direkt mit
   Konstanten verglichen wird, bekommt die Domäne `min(natürliches Maximum, k_max + 1)`; Werte
   darüber verhalten sich gleich. Wird ein Aggregat gegen ein anderes Aggregat verglichen, bleibt
   es ungekürzt. `max_product` (2 000 000) gilt für das komprimierte Gitter.
2. **Gitter** = kartesisches Produkt der (komprimierten) Aggregat-Domänen. Labels je Gitterpunkt
   aus dem Lehrer: `yellow = Level >= YELLOW`, `red = Level == RED`.
3. **Wachstum** je Ziel: Entropie-Gewinn, ganzzahlige Schwellen „x ≤ t“, bis zur Reinheit auf dem
   vollständigen Produktgitter. Deterministisch: bester Gewinn, Gleichstand ⇒ kleinere Merkmals-
   nummer (Aggregat-Reihenfolge des Profils), dann kleinere Schwelle. Zählungen kommen aus einer
   Summentabelle (SAT) der Labels, nicht aus Punktschleifen.
4. **Export** mit stabilen Blatt-IDs (Hash des Pfads) und Inhalts-Hash (`tree_version`).

Die Bäume werden nie von Simulator, Zufall oder Uhr beeinflusst: der Hash hängt nur von
Wissensbasis und Compiler-Version ab.
"""

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from operator import add
from typing import Any, Final

from waechter.triage import parser
from waechter.triage.kb import Level, ResolvedProfile, canonical_hash

COMPILER_VERSION: Final = "compiler-1"
MAX_PRODUCT: Final = 2_000_000
_EPSILON: Final = 1e-12


class CompilationError(ValueError):
    """Das Gitter überschreitet `max_product` oder die Wissensbasis lässt sich nicht kompilieren."""


# ---- Domänenkompression ---------------------------------------------------------------------
def _note(found: dict[str, int | None], name: str, constant: int) -> None:
    if name in found and found[name] is None:
        return
    found[name] = max(constant, found.get(name) or 0)


def _collect_constants(expr: parser.Expr, found: dict[str, int | None]) -> None:
    """Größte Vergleichskonstante je Aggregat; `None` = nicht kompressibel (Vergleich Name/Name)."""
    if isinstance(expr, parser.Compare):
        left, right = expr.left, expr.right
        if isinstance(left, parser.Var) and isinstance(right, parser.Num):
            _note(found, left.name, right.value)
        elif isinstance(left, parser.Num) and isinstance(right, parser.Var):
            _note(found, right.name, left.value)
        else:
            for child in (left, right):
                if isinstance(child, parser.Var):
                    found[child.name] = None
                else:
                    _collect_constants(child, found)
    elif isinstance(expr, parser.Var):
        _note(found, expr.name, 0)  # bloße Variable = Vergleich mit 0
    elif isinstance(expr, parser.Not):
        _collect_constants(expr.operand, found)
    elif isinstance(expr, parser.Logic):
        _collect_constants(expr.left, found)
        _collect_constants(expr.right, found)


def domain_caps(component: ResolvedProfile) -> dict[str, int]:
    """Domänenmaximum je Aggregat nach Kompression (Aggregat-Reihenfolge des Profils)."""
    found: dict[str, int | None] = {}
    for rule in (*component.red_rules, *component.yellow_rules):
        _collect_constants(rule.expr, found)
    caps: dict[str, int] = {}
    for aggregate in component.aggregates:
        k_max = found.get(aggregate.id, 0)
        natural = aggregate.max_value
        caps[aggregate.id] = natural if k_max is None else min(natural, k_max + 1)
    return caps


# ---- Gitter und Labels ---------------------------------------------------------------------
@dataclass(frozen=True)
class Grid:
    names: tuple[str, ...]
    maxima: tuple[int, ...]  # Domänenmaximum je Merkmal (Werte 0..maximum)
    sizes: tuple[int, ...]
    strides: tuple[int, ...]
    total: int


def make_grid(names: Sequence[str], maxima: Sequence[int]) -> Grid:
    sizes = tuple(m + 1 for m in maxima)
    strides = [1] * len(sizes)
    for axis in range(len(sizes) - 2, -1, -1):
        strides[axis] = strides[axis + 1] * sizes[axis + 1]
    total = math.prod(sizes)
    return Grid(tuple(names), tuple(maxima), sizes, tuple(strides), total)


def _expand(grid: Grid, positions: tuple[int, ...], table: Sequence[int]) -> bytes:
    """Funktion der Achsen `positions` (Zeilenmajor, `table`) auf das ganze Gitter ausdehnen."""
    if not positions:
        return bytes([table[0]]) * grid.total
    last = positions[-1]
    tail = math.prod(grid.sizes[last + 1 :])
    axis_set = set(positions)

    def rec(axis: int, base: int) -> bytes:
        size = grid.sizes[axis]
        if axis == last:
            return b"".join(bytes([table[base * size + v]]) * tail for v in range(size))
        if axis in axis_set:
            return b"".join(rec(axis + 1, base * size + v) for v in range(size))
        return rec(axis + 1, base) * size

    return rec(0, 0)


def truth_array(grid: Grid, expr: parser.Expr) -> bytes:
    """0/1-Array der Regel `expr` über das Gitter (Auswertung mit dem sicheren Parser)."""
    names = parser.variables(expr)
    positions = tuple(sorted(grid.names.index(n) for n in names))
    ordered = [grid.names[p] for p in positions]
    table = [
        int(parser.evaluate(expr, dict(zip(ordered, values, strict=True))) != 0)
        for values in itertools.product(*(range(grid.sizes[p]) for p in positions))
    ]
    return _expand(grid, positions, table)


def _or_all(grid: Grid, arrays: Sequence[bytes]) -> bytes:
    merged = 0
    for array in arrays:
        merged |= int.from_bytes(array, "big")
    return merged.to_bytes(grid.total, "big")


def teacher_arrays(component: ResolvedProfile, grid: Grid) -> tuple[bytes, bytes]:
    """`(yellow, red)`: Lehrer-Labels `>= YELLOW` bzw. `== RED` je Gitterpunkt (0/1)."""
    red = _or_all(grid, [truth_array(grid, r.expr) for r in component.red_rules])
    yellow_only = _or_all(grid, [truth_array(grid, r.expr) for r in component.yellow_rules])
    yellow = (int.from_bytes(red, "big") | int.from_bytes(yellow_only, "big")).to_bytes(
        grid.total, "big"
    )
    return yellow, red


def teacher_level_array(component: ResolvedProfile, grid: Grid) -> bytes:
    """Lehrerlevel (0/1/2) je Gitterpunkt."""
    yellow, red = teacher_arrays(component, grid)
    return bytes(y + r for y, r in zip(yellow, red, strict=True))


# ---- Baum ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Box:
    lo: tuple[int, ...]
    hi: tuple[int, ...]
    cls: int
    leaf_id: str


@dataclass(frozen=True)
class Tree:
    """Binärer Baum in Knoten-Arrays; `feature[n] == -1` ⇒ Blatt mit Klasse `value[n]`."""

    target: str
    feature: tuple[int, ...]
    threshold: tuple[int, ...]
    left: tuple[int, ...]
    right: tuple[int, ...]
    value: tuple[int, ...]
    leaf_id: tuple[str, ...]

    @property
    def leaves(self) -> int:
        return sum(1 for f in self.feature if f == -1)

    @property
    def depth(self) -> int:
        def walk(node: int) -> int:
            if self.feature[node] == -1:
                return 0
            return 1 + max(walk(self.left[node]), walk(self.right[node]))

        return walk(0)

    def predict(self, x: Sequence[int]) -> tuple[int, str]:
        """`(Klasse, Blatt-ID)` für den (komprimierten) Merkmalsvektor `x`."""
        node = 0
        while self.feature[node] != -1:
            node = (
                self.left[node]
                if x[self.feature[node]] <= self.threshold[node]
                else self.right[node]
            )
        return self.value[node], self.leaf_id[node]

    def boxes(self, maxima: Sequence[int]) -> list[Box]:
        """Blattboxen (ganzzahlig, auf die Domäne geklemmt); leere Boxen entfallen."""
        out: list[Box] = []

        def rec(node: int, lo: tuple[int, ...], hi: tuple[int, ...]) -> None:
            if self.feature[node] == -1:
                if all(a <= b for a, b in zip(lo, hi, strict=True)):
                    out.append(Box(lo, hi, self.value[node], self.leaf_id[node]))
                return
            f, t = self.feature[node], self.threshold[node]
            new_hi = (*hi[:f], min(hi[f], t), *hi[f + 1 :])
            rec(self.left[node], lo, new_hi)
            new_lo = (*lo[:f], max(lo[f], t + 1), *lo[f + 1 :])
            rec(self.right[node], new_lo, hi)

        rec(0, (0,) * len(maxima), tuple(maxima))
        return out

    def to_dict(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        for n in range(len(self.feature)):
            if self.feature[n] == -1:
                nodes.append({"leaf": self.value[n], "id": self.leaf_id[n]})
            else:
                nodes.append(
                    {
                        "f": self.feature[n],
                        "t": self.threshold[n],
                        "l": self.left[n],
                        "r": self.right[n],
                    }
                )
        return {"target": self.target, "nodes": nodes}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Tree":
        feature: list[int] = []
        threshold: list[int] = []
        left: list[int] = []
        right: list[int] = []
        value: list[int] = []
        leaf_id: list[str] = []
        for node in data["nodes"]:
            if "leaf" in node:
                feature.append(-1)
                threshold.append(0)
                left.append(-1)
                right.append(-1)
                value.append(int(node["leaf"]))
                leaf_id.append(str(node["id"]))
            else:
                feature.append(int(node["f"]))
                threshold.append(int(node["t"]))
                left.append(int(node["l"]))
                right.append(int(node["r"]))
                value.append(0)
                leaf_id.append("")
        return cls(
            str(data["target"]),
            tuple(feature),
            tuple(threshold),
            tuple(left),
            tuple(right),
            tuple(value),
            tuple(leaf_id),
        )


def _summed_area(labels: bytes, grid: Grid) -> list[int]:
    """Summentabelle über alle Achsen (Zählen von Positiven in beliebigen Boxen in O(2^k))."""
    sat = list(labels)
    for axis in range(len(grid.sizes)):
        size, stride = grid.sizes[axis], grid.strides[axis]
        block = size * stride
        for outer in range(0, grid.total, block):
            for i in range(1, size):
                start = outer + i * stride
                sat[start : start + stride] = map(
                    add, sat[start : start + stride], sat[start - stride : start]
                )
    return sat


def _box_count(sat: Sequence[int], grid: Grid, lo: Sequence[int], hi: Sequence[int]) -> int:
    dims = [i for i in range(len(lo)) if lo[i] > 0]
    base = sum(hi[i] * grid.strides[i] for i in range(len(hi)))
    total = 0
    for mask in range(1 << len(dims)):
        index, sign = base, 1
        for j, i in enumerate(dims):
            if mask >> j & 1:
                index += (lo[i] - 1 - hi[i]) * grid.strides[i]
                sign = -sign
        total += sign * sat[index]
    return total


def _entropy(positive: int, total: int) -> float:
    if positive in (0, total):
        return 0.0
    p = positive / total
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def grow_tree(target: str, labels: bytes, grid: Grid) -> Tree:
    """Entropie-Baum bis zur Reinheit auf dem vollständigen Produktgitter (deterministisch)."""
    sat = _summed_area(labels, grid)
    d = len(grid.sizes)
    feature: list[int] = []
    threshold: list[int] = []
    left: list[int] = []
    right: list[int] = []
    value: list[int] = []
    leaf_id: list[str] = []

    def new_node() -> int:
        feature.append(-1)
        threshold.append(0)
        left.append(-1)
        right.append(-1)
        value.append(0)
        leaf_id.append("")
        return len(feature) - 1

    def volume(lo: Sequence[int], hi: Sequence[int]) -> int:
        return math.prod(h - lw + 1 for lw, h in zip(lo, hi, strict=True))

    def grow(lo: tuple[int, ...], hi: tuple[int, ...], path: tuple[str, ...]) -> int:
        node = new_node()
        total = volume(lo, hi)
        positive = _box_count(sat, grid, lo, hi)
        if positive in (0, total):
            value[node] = 1 if positive else 0
            leaf_id[node] = canonical_hash([target, *path])[:12]
            return node
        parent = _entropy(positive, total)
        best: tuple[float, int, int] | None = None
        for f in range(d):
            for t in range(lo[f], hi[f]):
                left_hi = (*hi[:f], t, *hi[f + 1 :])
                left_total = volume(lo, left_hi)
                left_pos = _box_count(sat, grid, lo, left_hi)
                right_total, right_pos = total - left_total, positive - left_pos
                gain = (
                    parent
                    - left_total / total * _entropy(left_pos, left_total)
                    - right_total / total * _entropy(right_pos, right_total)
                )
                if best is None or gain > best[0] + _EPSILON:
                    best = (gain, f, t)
        if best is None:  # pragma: no cover - ein nicht reines Box hat immer eine Schwelle
            raise CompilationError("no split available")
        _, f, t = best
        feature[node], threshold[node] = f, t
        name = grid.names[f]
        left[node] = grow(lo, (*hi[:f], t, *hi[f + 1 :]), (*path, f"{name}<={t}"))
        right[node] = grow((*lo[:f], t + 1, *lo[f + 1 :]), hi, (*path, f"{name}>={t + 1}"))
        return node

    grow((0,) * d, tuple(grid.maxima), ())
    return Tree(
        target,
        tuple(feature),
        tuple(threshold),
        tuple(left),
        tuple(right),
        tuple(value),
        tuple(leaf_id),
    )


# ---- Kompilat einer Komponente --------------------------------------------------------
@dataclass(frozen=True, eq=False)
class CompiledComponent:
    component_id: str
    profile_hash: str
    features: tuple[str, ...]
    natural: tuple[int, ...]  # natürliche Domänenmaxima
    caps: tuple[int, ...]  # komprimierte Domänenmaxima (= Gitter)
    yellow: Tree
    red: Tree
    compiler_version: str
    hash: str  # Inhalts-Hash der Bäume und des Kopfs (tree_version)

    @property
    def grid_points(self) -> int:
        return math.prod(c + 1 for c in self.caps)

    @property
    def natural_points(self) -> int:
        return math.prod(n + 1 for n in self.natural)

    def vector(self, values: Mapping[str, int]) -> tuple[int, ...]:
        """Merkmalsvektor (Aggregatwerte, auf die komprimierte Domäne gekappt)."""
        return tuple(min(values[f], c) for f, c in zip(self.features, self.caps, strict=True))

    def classify(self, values: Mapping[str, int]) -> tuple[Level, str, str]:
        """`(Level, Gelb-Blatt-ID, Rot-Blatt-ID)` für Aggregatwerte (`red ⇒ yellow` ist geprüft)."""
        x = self.vector(values)
        yellow, yellow_leaf = self.yellow.predict(x)
        red, red_leaf = self.red.predict(x)
        level = Level.RED if red else Level.YELLOW if yellow else Level.GREEN
        return level, yellow_leaf, red_leaf

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": {
                "component_id": self.component_id,
                "profile_hash": self.profile_hash,
                "compiler_version": self.compiler_version,
                "features": list(self.features),
                "natural": list(self.natural),
                "caps": list(self.caps),
            },
            "yellow": self.yellow.to_dict(),
            "red": self.red.to_dict(),
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CompiledComponent":
        header = data["header"]
        return cls(
            component_id=str(header["component_id"]),
            profile_hash=str(header["profile_hash"]),
            features=tuple(header["features"]),
            natural=tuple(int(v) for v in header["natural"]),
            caps=tuple(int(v) for v in header["caps"]),
            yellow=Tree.from_dict(data["yellow"]),
            red=Tree.from_dict(data["red"]),
            compiler_version=str(header["compiler_version"]),
            hash=str(data["hash"]),
        )


def _content_hash(header: Mapping[str, Any], yellow: Tree, red: Tree) -> str:
    return canonical_hash({"header": header, "yellow": yellow.to_dict(), "red": red.to_dict()})


def compile_component(
    component: ResolvedProfile, *, max_product: int = MAX_PRODUCT
) -> CompiledComponent:
    """Kompiliert eine Komponente zu zwei exakten Bäumen (Hook H3).

    Wirft `CompilationError`, wenn das komprimierte Gitter `max_product` überschreitet (kein
    stilles Stichproben-V1, triage.md §9).
    """
    caps = domain_caps(component)
    names = tuple(a.id for a in component.aggregates)
    natural = tuple(a.max_value for a in component.aggregates)
    maxima = tuple(caps[n] for n in names)
    points = math.prod(m + 1 for m in maxima)
    if points > max_product:
        raise CompilationError(
            f"grid of {component.id} has {points} points after compression, above max_product "
            f"{max_product}; reduce the aggregates"
        )
    grid = make_grid(names, maxima)
    yellow_labels, red_labels = teacher_arrays(component, grid)
    yellow = grow_tree("yellow", yellow_labels, grid)
    red = grow_tree("red", red_labels, grid)
    header = {
        "component_id": component.id,
        "profile_hash": component.hash,
        "compiler_version": COMPILER_VERSION,
        "features": list(names),
        "natural": list(natural),
        "caps": list(maxima),
    }
    return CompiledComponent(
        component_id=component.id,
        profile_hash=component.hash,
        features=names,
        natural=natural,
        caps=maxima,
        yellow=yellow,
        red=red,
        compiler_version=COMPILER_VERSION,
        hash=_content_hash(header, yellow, red),
    )


# ---- Lesbare Regelkarte (render_rules) ------------------------------------------------
@dataclass(frozen=True)
class RenderedRule:
    level: str  # "RED" | "YELLOW"
    leaf_id: str
    conditions: tuple[tuple[str, str, int], ...]  # (Aggregat, ">=" | "<=", Wert)
    expression: str  # für den sicheren Parser
    text: Mapping[str, str]
    teacher_rule_ids: tuple[str, ...]


_JOIN = {"cs": " a ", "en": " and ", "de": " und "}


def _label(component: ResolvedProfile, name: str, lang: str) -> str:
    for aggregate in component.aggregates:
        if aggregate.id == name and aggregate.label:
            return aggregate.label.get(lang) or aggregate.label.get("en") or name
    return name


def _render_box(
    component: ResolvedProfile, compiled: CompiledComponent, box: Box, level: str
) -> RenderedRule:
    conditions: list[tuple[str, str, int]] = []
    for index, name in enumerate(compiled.features):
        if box.lo[index] > 0:
            conditions.append((name, ">=", box.lo[index]))
        if box.hi[index] < compiled.caps[index]:
            conditions.append((name, "<=", box.hi[index]))
    expression = " and ".join(f"{n} {op} {v}" for n, op, v in conditions) or "1 >= 0"
    text = {
        lang: _JOIN[lang].join(f"{_label(component, n, lang)} {op} {v}" for n, op, v in conditions)
        or {"cs": "vždy", "en": "always", "de": "immer"}[lang]
        for lang in ("cs", "en", "de")
    }
    corner = {name: box.lo[i] for i, name in enumerate(compiled.features)}
    rules = (
        component.red_rules if level == "RED" else (*component.red_rules, *component.yellow_rules)
    )
    fired = tuple(r.id for r in rules if parser.evaluate(r.expr, corner))
    return RenderedRule(level, box.leaf_id, tuple(conditions), expression, text, fired)


def render_rules(component: ResolvedProfile, compiled: CompiledComponent) -> list[RenderedRule]:
    """Vereinfachte Pfade (je Merkmal höchstens eine untere und eine obere Schranke), Rot zuerst.

    Rot = positive Blätter des Rot-Baums, Gelb = positive Blätter des Gelb-Baums (`>= YELLOW`). Die
    Lehrerregel-IDs eines Blatts stammen vom unteren Eckpunkt der Box (Regeln sind monoton: was dort
    gilt, gilt in der ganzen Box).
    """
    rendered: list[RenderedRule] = []
    for tree, level in ((compiled.red, "RED"), (compiled.yellow, "YELLOW")):
        for box in tree.boxes(compiled.caps):
            if box.cls == 1:
                rendered.append(_render_box(component, compiled, box, level))
    return rendered


def evaluate_rendered(rules: Sequence[RenderedRule], values: Mapping[str, int]) -> Level:
    """Wertet gerenderte Regeln mit dem sicheren Parser aus (Rot vor Gelb)."""
    for level_name, result in (("RED", Level.RED), ("YELLOW", Level.YELLOW)):
        for rule in rules:
            if rule.level == level_name and parser.evaluate(parser.parse(rule.expression), values):
                return result
    return Level.GREEN


# ---- Cache nach Wissensbasis ----------------------------------------------------------
_CACHE: dict[tuple[str, str], CompiledComponent] = {}


def compiled_for(
    component: ResolvedProfile,
    *,
    build: Callable[[ResolvedProfile], CompiledComponent] = compile_component,
) -> CompiledComponent:
    """Kompilat je (Profil-Hash, Compiler-Version), einmal je Prozess berechnet."""
    key = (component.hash, COMPILER_VERSION)
    cached = _CACHE.get(key)
    if cached is None:
        cached = build(component)
        _CACHE[key] = cached
    return cached
