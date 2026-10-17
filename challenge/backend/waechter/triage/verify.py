"""Verifikation der kompilierten Bäume (Vertrag §4, Hook H4): V1, V3, V4 - ohne neue Abhängigkeit.

- **V1 Aggregat-Gitter (exhaustiv):** (a) Baumfarbe == Lehrerfarbe an jedem Punkt des komprimierten
  Produktgitters (Untertriage `under`, Obertriage `over`), ergänzt um AST-Auswertung an allen
  Blattecken und an Zufallspunkten mit festem Seed; (b) Blattbox-Monotonie (kein Blatt der Klasse 1
  unterhalb eines Blatts der Klasse 0), Boxen zerlegen das Gitter ohne Lücke; (c) Rot ⇒ Gelb.
  Zusätzlich auf dem **ungekürzten** Gitter: Lehrer(x) == Baum(min(x, Kappe)) an jedem Punkt - der
  Nachweis, dass die Domänenkompression korrekt ist (`uncompressed`).
- **V3 Einzelschritt-Nachbarn auf dem Rohgitter (Symptomgrade):** jedes Symptom um +1 darf das
  Endlevel (Baum **und** Schild) nie senken; ein niedrigerer Vorbericht darf es nie senken.
- **V4 Schild:** jeder Rohpunkt im Bereich eines Bodens erreicht mindestens dessen `min_level`.

Das Rohgitter wird, solange es höchstens `max_exhaustive` Punkte hat, vollständig und vektorisiert
(Bytes-Arrays mit C-Geschwindigkeit) geprüft, jeweils für den ersten Bericht (`previous = None`) und
einen Vorbericht mit lauter Nullen; sonst per Stichprobe mit festem Seed (`sampled_raw`). Eine
Stichprobe zusätzlich immer: `CompiledEngine` gegen die unabhängige Rohgitter-Auswertung.
"""

import itertools
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import reduce
from operator import add, lt, mul
from typing import Any, Final, Literal

from waechter.triage import parser
from waechter.triage.compiler import (
    CompiledComponent,
    Grid,
    _expand,
    make_grid,
    teacher_level_array,
)
from waechter.triage.engine import CompiledEngine, TeacherEngine
from waechter.triage.kb import ResolvedComposition, ResolvedProfile

SEED: Final = 20261017
MAX_EXHAUSTIVE_RAW: Final = 1_000_000
SAMPLE_POINTS: Final = 20_000
SAMPLE_STATES: Final = 4_000

type Scope = Literal["exhaustive_raw", "exhaustive_orbit", "sampled_raw"]


@dataclass(frozen=True)
class RawReport:
    points: int
    exhaustive: bool
    v3_violations: int
    v4_violations: int
    engine_mismatches: int


@dataclass(frozen=True)
class UncompressedReport:
    points: int
    under: int
    over: int


@dataclass(frozen=True)
class ComponentReport:
    component_id: str
    points: int
    under: int
    over: int
    monotone_violations: int
    red_not_yellow: int
    partition_gaps: int
    corner_mismatches: int
    sample_mismatches: int
    leaves: Mapping[str, int]
    depth: Mapping[str, int]
    uncompressed: UncompressedReport | None
    raw: RawReport

    @property
    def ok(self) -> bool:
        return (
            self.under == 0
            and self.over == 0
            and self.monotone_violations == 0
            and self.red_not_yellow == 0
            and self.partition_gaps == 0
            and self.corner_mismatches == 0
            and self.sample_mismatches == 0
            and (
                self.uncompressed is None
                or (self.uncompressed.under, self.uncompressed.over) == (0, 0)
            )
            and self.raw.v3_violations == 0
            and self.raw.v4_violations == 0
            and self.raw.engine_mismatches == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "points": self.points,
            "under": self.under,
            "over": self.over,
            "monotone_violations": self.monotone_violations,
            "leaves": dict(self.leaves),
            "depth": dict(self.depth),
            "raw_points": self.raw.points,
            "v3_violations": self.raw.v3_violations,
            "v4_violations": self.raw.v4_violations,
            "uncompressed_points": self.uncompressed.points if self.uncompressed else None,
        }


@dataclass(frozen=True)
class VerificationReport:
    components: tuple[ComponentReport, ...]
    verification_scope: Scope

    @property
    def points(self) -> int:
        return sum(c.points for c in self.components)

    @property
    def under(self) -> int:
        return sum(c.under for c in self.components)

    @property
    def over(self) -> int:
        return sum(c.over for c in self.components)

    @property
    def monotone_violations(self) -> int:
        return sum(
            c.monotone_violations + c.raw.v3_violations + c.raw.v4_violations
            for c in self.components
        )

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.components)

    def to_dict(self) -> dict[str, Any]:
        """Form für `/config/triage`: points, under, over, violations, scope, components."""
        return {
            "points": self.points,
            "under": self.under,
            "over": self.over,
            "monotone_violations": self.monotone_violations,
            "scope": self.verification_scope,
            "components": [c.to_dict() for c in self.components],
        }


class VerificationError(RuntimeError):
    """Verifikation ergab Abweichungen: der Start endet mit Fehler (kein stiller Rückfall)."""


# ---- V1: Gitter, Boxen, Monotonie ------------------------------------------------------------
def paint(boxes: Sequence[Any], grid: Grid, *, caps: Sequence[int] | None = None) -> bytes:
    """Klasse je Gitterpunkt aus den Blattboxen (Boxen im komprimierten Raum auf `grid` gedehnt)."""
    cells = bytearray(grid.total)
    last = len(grid.sizes) - 1
    for box in boxes:
        if box.cls != 1:
            continue
        lo = list(box.lo)
        hi = list(box.hi)
        if (
            caps is not None
        ):  # komprimierte Box auf das ungekürzte Gitter: oberer Rand läuft bis zum Maximum
            hi = [grid.maxima[i] if hi[i] == caps[i] else hi[i] for i in range(len(hi))]
        outer = [range(lo[i], hi[i] + 1) for i in range(last)]
        width = hi[last] - lo[last] + 1
        ones = b"\x01" * width
        for index in itertools.product(*outer):
            start = sum(i * s for i, s in zip(index, grid.strides, strict=False)) + lo[last]
            cells[start : start + width] = ones
    return bytes(cells)


def _volume(box: Any) -> int:
    return math.prod(h - lw + 1 for lw, h in zip(box.lo, box.hi, strict=True))


def monotone_violations(boxes: Sequence[Any]) -> int:
    """Paare (Blatt A Klasse 1, Blatt B Klasse 0) mit `A.lo <= B.hi` in jeder Komponente."""
    ones = [b for b in boxes if b.cls == 1]
    zeros = [b for b in boxes if b.cls == 0]
    return sum(
        1 for a in ones for z in zeros if all(lo <= hi for lo, hi in zip(a.lo, z.hi, strict=True))
    )


def _teacher_ast_level(component: ResolvedProfile, values: Mapping[str, int]) -> int:
    if any(parser.evaluate(r.expr, values) for r in component.red_rules):
        return 2
    return 1 if any(parser.evaluate(r.expr, values) for r in component.yellow_rules) else 0


def _tree_vs_teacher(component: ResolvedProfile, compiled: CompiledComponent) -> dict[str, int]:
    names, caps = compiled.features, compiled.caps
    grid = make_grid(names, caps)
    yellow_boxes = compiled.yellow.boxes(caps)
    red_boxes = compiled.red.boxes(caps)
    yellow_cells = paint(yellow_boxes, grid)
    red_cells = paint(red_boxes, grid)
    teacher = teacher_level_array(component, grid)
    under = over = red_not_yellow = 0
    for y, r, t in zip(yellow_cells, red_cells, teacher, strict=True):
        level = 2 if r else 1 if y else 0
        if level < t:
            under += 1
        elif level > t:
            over += 1
        if r and not y:
            red_not_yellow += 1
    gaps = sum(
        abs(grid.total - sum(_volume(b) for b in boxes)) for boxes in (yellow_boxes, red_boxes)
    )
    return {
        "points": grid.total,
        "under": under,
        "over": over,
        "red_not_yellow": red_not_yellow,
        "gaps": gaps,
        "monotone": monotone_violations(yellow_boxes) + monotone_violations(red_boxes),
    }


def _corner_and_sample_checks(
    component: ResolvedProfile, compiled: CompiledComponent, rng: random.Random
) -> tuple[int, int]:
    """AST-Auswertung (unabhängig von den Tabellen): alle Blattecken und Zufallspunkte."""
    names, caps = compiled.features, compiled.caps
    corners = 0
    for tree in (compiled.yellow, compiled.red):
        threshold = 1 if tree.target == "yellow" else 2
        for box in tree.boxes(caps):
            for edge in (box.lo, box.hi):
                level = _teacher_ast_level(component, dict(zip(names, edge, strict=True)))
                if (level >= threshold) != bool(box.cls):
                    corners += 1
    mismatches = 0
    for _ in range(SAMPLE_POINTS):
        point = tuple(rng.randint(0, cap) for cap in caps)
        level = _teacher_ast_level(component, dict(zip(names, point, strict=True)))
        tree_level = (
            2 if compiled.red.predict(point)[0] else 1 if compiled.yellow.predict(point)[0] else 0
        )
        mismatches += int(level != tree_level)
    return corners, mismatches


def _uncompressed(component: ResolvedProfile, compiled: CompiledComponent) -> UncompressedReport:
    """Lehrer(x) == Baum(min(x, Kappe)) an jedem Punkt des natürlichen Gitters."""
    grid = make_grid(compiled.features, compiled.natural)
    yellow_cells = paint(compiled.yellow.boxes(compiled.caps), grid, caps=compiled.caps)
    red_cells = paint(compiled.red.boxes(compiled.caps), grid, caps=compiled.caps)
    teacher = teacher_level_array(component, grid)
    under = over = 0
    for y, r, t in zip(yellow_cells, red_cells, teacher, strict=True):
        level = 2 if r else 1 if y else 0
        if level < t:
            under += 1
        elif level > t:
            over += 1
    return UncompressedReport(grid.total, under, over)


# ---- V3/V4: Rohgitter (Symptomgrade) -----------------------------------------------------------
def raw_grid(component: ResolvedProfile) -> Grid:
    symptoms = component.symptoms
    return make_grid(symptoms, [component.items[s].grade_max for s in symptoms])


def _grade_arrays(grid: Grid) -> dict[str, bytes]:
    return {
        name: _expand(grid, (axis,), list(range(grid.sizes[axis])))
        for axis, name in enumerate(grid.names)
    }


def _elementwise(function: Any, arrays: Sequence[bytes]) -> bytes:
    return reduce(lambda a, b: bytes(map(function, a, b)), arrays)


def _aggregate_array(
    component: ResolvedProfile,
    aggregate: Any,
    grades: Mapping[str, bytes],
    total: int,
    *,
    previous_zero: bool,
) -> bytes:
    """Aggregatwert je Rohpunkt, unabhängig von `aggregate_value` (zweite Implementierung)."""
    members = [grades[s] for s in aggregate.items]
    if not members:
        return bytes(total)
    if aggregate.kind == "max_over":
        return _elementwise(max, members) if len(members) > 1 else members[0]
    if aggregate.kind == "min_over":
        return _elementwise(min, members) if len(members) > 1 else members[0]
    if aggregate.kind == "count_ge":
        threshold = aggregate.threshold or 1
        flags = [bytes(1 if g >= threshold else 0 for g in m) for m in members]
        return _elementwise(add, flags) if len(flags) > 1 else flags[0]
    # trend_flag: erster Bericht ⇒ 0; Vorbericht lauter Nullen ⇒ irgendein Grad >= 1
    if not previous_zero:
        return bytes(total)
    top = _elementwise(max, members) if len(members) > 1 else members[0]
    return bytes(1 if g >= 1 else 0 for g in top)


def _floor_array(component: ResolvedProfile, grid: Grid, floor: Any) -> bytes:
    names = parser.variables(floor.expr)
    axes = sorted({grid.names.index(n.partition(".")[0]) for n in names})
    table = []
    for values in itertools.product(*(range(grid.sizes[a]) for a in axes)):
        env: dict[str, int] = {}
        for axis, value in zip(axes, values, strict=True):
            env[f"{grid.names[axis]}.grade"] = value
            env[f"{grid.names[axis]}.present"] = int(value >= 1)
        table.append(int(parser.evaluate(floor.expr, env) != 0))
    return _expand(grid, tuple(axes), table)


def _tree_cells(compiled: CompiledComponent) -> bytes:
    """Klasse (0/1/2) je Punkt des komprimierten Gitters."""
    grid = make_grid(compiled.features, compiled.caps)
    yellow = paint(compiled.yellow.boxes(compiled.caps), grid)
    red = paint(compiled.red.boxes(compiled.caps), grid)
    return bytes(2 if r else 1 if y else 0 for y, r in zip(yellow, red, strict=True))


def _raw_levels(
    component: ResolvedProfile,
    compiled: CompiledComponent,
    grid: Grid,
    grades: Mapping[str, bytes],
    tree_cells: bytes,
    *,
    previous_zero: bool,
) -> tuple[bytes, list[tuple[bytes, int]]]:
    """Endlevel je Rohpunkt (Baum, dann Schild) und die Böden als `(Wahrheitsarray, min_level)`."""
    caps = compiled.caps
    cap_strides = make_grid(compiled.features, caps).strides
    index: list[int] = [0] * grid.total
    by_id = {a.id: a for a in component.aggregates}
    for position, name in enumerate(compiled.features):
        values = _aggregate_array(
            component, by_id[name], grades, grid.total, previous_zero=previous_zero
        )
        cap, stride = caps[position], cap_strides[position]
        scaled = bytes(min(v, cap) for v in values)
        index = list(map(add, index, map(mul, scaled, itertools.repeat(stride))))
    levels = bytes(map(tree_cells.__getitem__, index))
    floors: list[tuple[bytes, int]] = []
    for floor in component.floors:
        truth = _floor_array(component, grid, floor)
        floors.append((truth, int(floor.level)))
        required = bytes(map(mul, truth, itertools.repeat(int(floor.level))))
        levels = bytes(map(max, levels, required))
    return levels, floors


def _neighbour_violations(levels: bytes, grid: Grid) -> int:
    """Einzelschritt +1 auf einem Symptom senkt das Endlevel nie."""
    violations = 0
    for axis in range(len(grid.sizes)):
        stride, size = grid.strides[axis], grid.sizes[axis]
        block = size * stride
        for outer in range(0, grid.total, block):
            for i in range(size - 1):
                low = levels[outer + i * stride : outer + (i + 1) * stride]
                high = levels[outer + (i + 1) * stride : outer + (i + 2) * stride]
                violations += sum(map(lt, high, low))
    return violations


def _engine_sample(
    component: ResolvedProfile,
    compiled: CompiledComponent,
    rng: random.Random,
    teacher: TeacherEngine,
    engine: CompiledEngine,
) -> tuple[int, int, int]:
    """Stichprobe (fester Seed): V3 mit Vorbericht und `CompiledEngine` == `TeacherEngine`."""
    symptoms = component.symptoms
    v3 = mismatches = 0
    for _ in range(SAMPLE_STATES):
        grades = {s: rng.randint(0, component.items[s].grade_max) for s in symptoms}
        previous: Mapping[str, int] | None = (
            None if rng.random() < 0.3 else {s: rng.randint(0, 3) for s in symptoms}
        )
        base = engine.level_from_grades(grades, previous).level
        mismatches += int(base != teacher.level_from_grades(grades, previous).level)
        for symptom in symptoms:
            if grades[symptom] < component.items[symptom].grade_max:
                higher = {**grades, symptom: grades[symptom] + 1}
                v3 += int(engine.level_from_grades(higher, previous).level < base)
            if previous is not None and previous.get(symptom, 0) > 0:
                lower = {**previous, symptom: previous[symptom] - 1}
                v3 += int(engine.level_from_grades(grades, lower).level < base)
    return v3, 0, mismatches


def _raw_verification(
    component: ResolvedProfile,
    compiled: CompiledComponent,
    rng: random.Random,
    max_exhaustive: int,
) -> RawReport:
    grid = raw_grid(component)
    teacher, engine = TeacherEngine(component), CompiledEngine(component, [compiled])
    sample_v3, _, mismatches = _engine_sample(component, compiled, rng, teacher, engine)
    if grid.total > max_exhaustive:
        return RawReport(SAMPLE_STATES, False, sample_v3, 0, mismatches)
    grades = _grade_arrays(grid)
    tree_cells = _tree_cells(compiled)
    v3 = sample_v3
    v4 = 0
    for previous_zero in (False, True):
        levels, floors = _raw_levels(
            component, compiled, grid, grades, tree_cells, previous_zero=previous_zero
        )
        v3 += _neighbour_violations(levels, grid)
        for truth, minimum in floors:
            v4 += sum(
                1 for flag, level in zip(truth, levels, strict=True) if flag and level < minimum
            )
    return RawReport(grid.total * 2, True, v3, v4, mismatches)


# ---- Einstieg ----------------------------------------------------------------------------------
def verify_component(
    component: ResolvedProfile,
    compiled: CompiledComponent,
    *,
    uncompressed: bool = False,
    max_exhaustive: int = MAX_EXHAUSTIVE_RAW,
    seed: int = SEED,
) -> ComponentReport:
    """Verifiziert eine kompilierte Komponente (V1, V3, V4); `uncompressed` ⇒ zusätzlich V1 roh."""
    rng = random.Random(seed)  # noqa: S311 - fester Seed, reproduzierbare Stichprobe
    v1 = _tree_vs_teacher(component, compiled)
    corners, samples = _corner_and_sample_checks(component, compiled, rng)
    return ComponentReport(
        component_id=component.id,
        points=v1["points"],
        under=v1["under"],
        over=v1["over"],
        monotone_violations=v1["monotone"],
        red_not_yellow=v1["red_not_yellow"],
        partition_gaps=v1["gaps"],
        corner_mismatches=corners,
        sample_mismatches=samples,
        leaves={"yellow": compiled.yellow.leaves, "red": compiled.red.leaves},
        depth={"yellow": compiled.yellow.depth, "red": compiled.red.depth},
        uncompressed=_uncompressed(component, compiled) if uncompressed else None,
        raw=_raw_verification(component, compiled, rng, max_exhaustive),
    )


def verify_composition(
    composition: ResolvedComposition,
    compiled: Sequence[CompiledComponent],
    *,
    uncompressed: bool = True,
    max_exhaustive: int = MAX_EXHAUSTIVE_RAW,
) -> VerificationReport:
    """Bericht mit `components[]` und `verification_scope` (H4).

    `exhaustive_raw` nur, wenn wirklich jeder Punkt geprüft wurde: V1 auf dem komprimierten **und**
    dem ungekürzten Gitter sowie das Rohgitter (V3/V4) vollständig; sonst `sampled_raw`.
    """
    by_id = {c.component_id: c for c in compiled}
    reports = tuple(
        verify_component(
            component,
            by_id[component.id],
            uncompressed=uncompressed,
            max_exhaustive=max_exhaustive,
        )
        for component in composition.components
    )
    complete = all(r.raw.exhaustive and r.uncompressed is not None for r in reports)
    scope: Scope = "exhaustive_raw" if complete else "sampled_raw"
    return VerificationReport(reports, scope)


def require_clean(report: VerificationReport) -> VerificationReport:
    """Wirft `VerificationError`, wenn die Verifikation nicht 0/0/0 ergibt."""
    if not report.ok:
        raise VerificationError(
            f"verification failed: under={report.under} over={report.over} "
            f"monotone_violations={report.monotone_violations}"
        )
    return report


__all__ = [
    "ComponentReport",
    "RawReport",
    "UncompressedReport",
    "VerificationError",
    "VerificationReport",
    "monotone_violations",
    "paint",
    "require_clean",
    "verify_component",
    "verify_composition",
]
