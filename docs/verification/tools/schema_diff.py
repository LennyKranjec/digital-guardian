"""A3-Gegenprüfung (außerhalb der Repo-Abhängigkeiten): Differenzialtest des eigenen Schema-Prüfers.

Vergleicht `waechter.schema_check.validate` mit `jsonschema` (Draft 2020-12) über viele Ein-Punkt-Mutationen
der Fixture-Inhalte. Aufruf (Referenz-venv mit jsonschema, siehe docs/verification/PLAN.md):

    C:\rk\tools\a3-venv\Scripts\python.exe docs/verification/tools/schema_diff.py <schema.json> <content_dir> <challenge/backend>

Ausgabe: Zahl der Mutationen, Zahl der Abweichungen (Prüfer akzeptiert, jsonschema lehnt ab – oder umgekehrt).
Exitcode 1 bei Abweichung. Zufall ist fest (Seed 20261016), damit der Lauf reproduzierbar ist.
"""

import copy
import json
import random
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

FILES = {
    "items.yaml": "ItemsFile",
    "regimens.yaml": "RegimensFile",
    "ctcae.yaml": "CtcaeFile",
    "rules.yaml": "RulesFile",
    "report.yaml": "ReportFile",
    "scenario.yaml": "ScenarioFile",
}
BAD_VALUES: list[Any] = [None, "", "x", -1, 5, 99, 1.5, True, [], {}, "ZZ-NOPE", "2026-10-17"]


class _Loader(yaml.SafeLoader):
    pass


_Loader.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def paths(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = [prefix]
    if isinstance(node, dict):
        for k, v in node.items():
            out += paths(v, (*prefix, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += paths(v, (*prefix, i))
    return out


def get(node: Any, p: tuple[Any, ...]) -> Any:
    for k in p:
        node = node[k]
    return node


def mutate(doc: Any, rng: random.Random) -> Any:
    clone = copy.deepcopy(doc)
    p = rng.choice(paths(clone)[1:])
    parent, key = get(clone, p[:-1]), p[-1]
    kind = rng.choice(["delete", "replace", "replace", "extra", "append"])
    if kind == "delete" and isinstance(parent, dict):
        del parent[key]
    elif kind == "extra" and isinstance(get(clone, p), dict):
        get(clone, p)["_extra"] = 1
    elif kind == "append" and isinstance(get(clone, p), list):
        get(clone, p).append(rng.choice(BAD_VALUES))
    else:
        parent[key] = rng.choice(BAD_VALUES)
    return clone


def main() -> int:
    schema_path, content_dir, backend = (Path(a) for a in sys.argv[1:4])
    sys.path.insert(0, str(backend))
    from waechter import schema_check  # noqa: PLC0415

    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    rng = random.Random(20261016)
    total = diffs = 0
    for filename, definition in FILES.items():
        doc = yaml.load((content_dir / filename).read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506
        sub = {"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}
        ref = Draft202012Validator(sub, format_checker=FormatChecker())
        assert not list(ref.iter_errors(doc)), f"{filename}: Original ungültig (jsonschema)"
        assert not schema_check.validate(doc, schema["$defs"][definition], schema), filename
        for _ in range(400):
            mutated = mutate(doc, rng)
            ours = bool(schema_check.validate(mutated, schema["$defs"][definition], schema))
            theirs = bool(list(ref.iter_errors(mutated)))
            total += 1
            if ours != theirs:
                diffs += 1
                if diffs <= 8:
                    print(f"ABWEICHUNG {filename}: eigener Prüfer lehnt ab={ours}, jsonschema lehnt ab={theirs}")
                    print(json.dumps(mutated, ensure_ascii=False, default=str)[:300])
    print(f"Mutationen: {total}, Abweichungen: {diffs}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
