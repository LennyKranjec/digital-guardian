# ruff: noqa: F401
"""A3-Gegenproben zu T-09F (Besitz A3): rote Regeln, die formal erreichbar sind, aber nie auslösen.

Hilfen aus `test_config_admin.py`; kein Netz.
"""

import copy
from typing import Any

import pytest
from fastapi import FastAPI

from test_config_admin import (
    BASE,
    alerts_of,
    client_for,
    current_rules,
    put_rules,
    submit,
    versions,
)


def only_red_rule(rules: dict[str, Any], rule_id: str, **changes: Any) -> dict[str, Any]:
    """Alle roten Regeln außer `rule_id` deaktivieren; `changes` auf `rule_id` anwenden."""
    changed = copy.deepcopy(rules)
    for rule in changed["rules"]:
        if rule["level"] == "red" and rule["id"] != rule_id:
            rule["enabled"] = False
        if rule["id"] == rule_id:
            rule.update(changes)
    return changed


def test_a3_control_fever_rule_alone_still_fires(seeded_app: FastAPI) -> None:
    """Kontrolle: nur R-URG-01 als rote Regel, unverändert ⇒ akzeptiert und löst aus."""
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    assert put_rules(admin, version, only_red_rule(rules, "R-URG-01")).status_code == 200
    submit(client_for(seeded_app, "patient2"), [("fever", "presence", 1)])
    assert alerts_of(seeded_app, "SYN-0002", "R-URG-01")


@pytest.mark.parametrize(
    "changes",
    [
        {"attributes": ["interference"]},  # Fieber hat kein Attribut "interference"
        {"attributes": ["severity"]},
        {"symptom_keys": ["nausea"], "attributes": ["presence"]},  # Übelkeit hat kein "presence"
    ],
)
def test_a3_red_rule_on_a_combination_without_answers_is_rejected(
    seeded_app: FastAPI, changes: dict[str, Any]
) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    response = put_rules(admin, version, only_red_rule(rules, "R-URG-01", **changes))
    assert response.status_code == 422, (response.status_code, response.text[:200])
    assert versions(seeded_app, "rules") == ["rules-v1"]


def test_a3_fever_still_turns_red_after_any_accepted_change(seeded_app: FastAPI) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    changed = only_red_rule(rules, "R-URG-01", attributes=["interference"])
    accepted = put_rules(admin, version, changed).status_code == 200
    submit(client_for(seeded_app, "patient2"), [("fever", "presence", 1)])
    assert alerts_of(seeded_app, "SYN-0002", "R-URG-01") or not accepted
