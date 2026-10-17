"""Gemeinsame Helfer der Triage-Tests (kein Testmodul): echte Wissensbasis, Zufallszustände.

Zufall läuft ausschließlich über `random.Random(seed)` mit festem Seed (keine Uhr, kein Datum).
"""

import copy
import functools
import random
from pathlib import Path
from typing import Any

import yaml

from waechter.triage.kb import (
    ANSWER_MAX,
    PRESENCE_MAX,
    Key,
    KnowledgeBase,
    ResolvedProfile,
    build_kb,
    load_kb,
)

CONTENT = Path(__file__).resolve().parents[1] / "content"


@functools.cache
def _yaml(name: str) -> Any:
    return yaml.safe_load((CONTENT / name).read_text(encoding="utf-8"))


def real_inputs() -> tuple[dict[str, Any], dict[str, list[str]], dict[str, list[str]]]:
    """`(triage_raw, attributes, regimens)` als frische Kopie (Tests dürfen mutieren)."""
    raw: dict[str, Any] = copy.deepcopy(_yaml("triage.yaml"))
    attributes = {
        item["symptom_key"]: [a["attribute"] for a in item["attributes"]]
        for item in _yaml("items.yaml")["items"]
    }
    regimens = {r["id"]: list(r["symptom_keys"]) for r in _yaml("regimens.yaml")["regimens"]}
    return raw, attributes, regimens


def build_from(raw: dict[str, Any]) -> KnowledgeBase:
    _, attributes, regimens = real_inputs()
    return build_kb(raw, attributes=attributes, regimens=regimens)


@functools.cache
def real_kb() -> KnowledgeBase:
    return load_kb(CONTENT)


def profile_ids() -> list[str]:
    return list(real_kb().profiles)


def random_value(rng: random.Random, attribute: str) -> int:
    """Antwortwert, zu niedrigen Werten geneigt (realistischere Zustände)."""
    if attribute == "presence":
        return rng.choices(range(PRESENCE_MAX + 1), weights=[3, 1])[0]
    return rng.choices(range(ANSWER_MAX + 1), weights=[6, 3, 2, 1, 1])[0]


def random_state(rng: random.Random, profile: ResolvedProfile) -> dict[Key, int]:
    """Zufällige Teilantworten über alle Felder des Profils (auch Folgefelder bei Gate = 0)."""
    answer_probability = rng.choice([0.1, 0.3, 0.5, 0.8, 1.0])
    state: dict[Key, int] = {}
    for symptom in profile.symptoms:
        for attribute in profile.items[symptom].attributes:
            if rng.random() < answer_probability:
                state[(symptom, attribute)] = random_value(rng, attribute)
    return state


def random_previous(rng: random.Random, profile: ResolvedProfile) -> dict[str, int] | None:
    if rng.random() < 0.4:
        return None
    return {
        s: rng.randint(0, profile.items[s].grade_max)
        for s in profile.symptoms
        if rng.random() < 0.7
    }
