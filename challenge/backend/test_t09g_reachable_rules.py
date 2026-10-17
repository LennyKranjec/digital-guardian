"""T-09G: rote Regel zählt nur, wenn sie auf eine erfragte Kombination Symptom/Attribut zutrifft.

Ergänzt `test_a3_t09f.py` (A3): Tabellenfälle für `_reachable` und Ende-zu-Ende-Fälle über die API.
Fixture-Inhalt (`conftest`): Itemkatalog mit presence-/Skalen-Attributen.
"""

import copy
from typing import Any

import pytest
from fastapi import FastAPI

from test_config_admin import (
    alerts_of,
    assert_rejected,
    client_for,
    current_rules,
    put_rules,
    submit,
    versions,
)
from waechter.services import config_admin
from waechter.services.alerts import rule_applies

ASKED = [
    ("fever", "presence"),
    ("nausea", "frequency"),
    ("nausea", "severity"),
    ("fatigue", "severity"),
    ("fatigue", "interference"),
]


def rule(**changes: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "R-X",
        "level": "red",
        "kind": "threshold",
        "enabled": True,
        "symptom_keys": [],
        "attributes": [],
        "params": {"min_value": 1},
    }
    base.update(changes)
    return base


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, True),  # Regel für alles
        ({"symptom_keys": ["fever"], "attributes": ["presence"]}, True),
        ({"symptom_keys": ["fever"]}, True),  # nur Symptom: presence passt
        ({"attributes": ["interference"]}, True),  # Müdigkeit hat interference
        ({"symptom_keys": ["fever"], "attributes": ["interference"]}, False),
        ({"symptom_keys": ["fever"], "attributes": ["severity"]}, False),
        ({"symptom_keys": ["nausea"], "attributes": ["presence"]}, False),
        ({"symptom_keys": ["unbekannt"]}, False),
        ({"symptom_keys": ["fever"], "params": {"min_value": 2}}, False),  # presence nur 0/1
        ({"symptom_keys": ["fever"], "params": {"min_value": 1}}, True),
        ({"symptom_keys": ["nausea"], "params": {"min_value": 4}}, True),  # Skala 0-4
        ({"symptom_keys": ["nausea"], "params": {"min_value": 5}}, False),
        ({"symptom_keys": ["fever", "nausea"], "attributes": ["severity"]}, True),  # eines passt
        (
            {"kind": "trend", "symptom_keys": ["fever"], "params": {"target_value": 3}},
            False,
        ),
    ],
)
def test_reachable_needs_a_matching_asked_pair_inside_its_value_range(
    changes: dict[str, Any], expected: bool
) -> None:
    assert config_admin._reachable(rule(**changes), ASKED) is expected


def test_rule_applies_is_the_single_matching_function_for_engine_and_validation() -> None:
    assert rule_applies(rule(symptom_keys=["fever"]), "fever", "presence")
    assert not rule_applies(rule(symptom_keys=["fever"]), "nausea", "severity")
    assert rule_applies(rule(), "anything", "any")


def only_red(rules: dict[str, Any], keep: str, **changes: Any) -> dict[str, Any]:
    changed = copy.deepcopy(rules)
    for item in changed["rules"]:
        if item["level"] == "red" and item["id"] != keep:
            item["enabled"] = False
        if item["id"] == keep:
            item.update(changes)
    return changed


def test_the_rejection_is_a_no_red_rule_error_without_echoing_input(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    response = put_rules(admin, version, only_red(rules, "R-URG-01", attributes=["interference"]))
    assert_rejected(seeded_app, response, "no_red_rule")  # 422, nichts gespeichert, kein Audit
    assert "interference" not in response.text  # nie Werte der Eingabe


def test_a_red_rule_on_an_asked_combination_is_accepted_and_fires(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    changed = only_red(rules, "R-URG-01", symptom_keys=["fever"], attributes=["presence"])
    assert put_rules(admin, version, changed).status_code == 200
    submit(client_for(seeded_app, "patient2"), [("fever", "presence", 1)])
    assert alerts_of(seeded_app, "SYN-0002", "R-URG-01")
    assert versions(seeded_app, "rules") == ["rules-v1", "rules-v2"]
