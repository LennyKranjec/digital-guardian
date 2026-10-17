"""A3-Gegenproben zu T-09 (Besitz A3): Sicherheitsböden der Konfiguration lassen sich nicht über
unerreichbare Schwellen umgehen; Paralleländerung verschiedener Arten. Hilfen aus
`test_config_admin.py`; kein Netz.
"""

import copy
import json
from typing import Any

import pytest
from fastapi import FastAPI

from conftest import run_parallel
from test_config_admin import (
    BASE,
    alerts_of,
    client_for,
    current_report,
    current_rules,
    put_rules,
    submit,
    versions,
)


def red_unreachable(rules: dict[str, Any], value: Any) -> dict[str, Any]:
    changed = copy.deepcopy(rules)
    for rule in changed["rules"]:
        if rule["level"] == "red" and rule["enabled"] and "min_value" in rule["params"]:
            rule["params"]["min_value"] = value
    return changed


def test_a3_reachable_change_is_applied_and_visible_everywhere(
    seeded_app: FastAPI,
) -> None:
    """Kontrolle: eine gültige Änderung wirkt (schützt vor 'alles wird abgelehnt')."""
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    changed = copy.deepcopy(rules)
    next(r for r in changed["rules"] if r["id"] == "R-SEV-01")["params"]["min_value"] = 4
    assert put_rules(admin, version, changed, "A3").status_code == 200
    assert admin.get("/api/v1/meta").json()["waechter"]["content_versions"]["rules"] == "rules-v2"
    assert admin.get(f"{BASE}/config").json()["rules"]["version"] == "rules-v2"
    history = admin.get(f"{BASE}/config/history", params={"kind": "rules"}).json()
    assert [(h["version"], h["active"]) for h in history] == [
        ("rules-v2", True),
        ("rules-v1", False),
    ]


def test_a3_unreachable_red_threshold_is_rejected(seeded_app: FastAPI) -> None:
    version, rules = current_rules(seeded_app)
    response = put_rules(client_for(seeded_app, "admin"), version, red_unreachable(rules, 99))
    assert response.status_code == 422, response.text


def test_a3_patient_with_fever_still_gets_a_red_alert_after_any_accepted_change(
    seeded_app: FastAPI,
) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    accepted = put_rules(admin, version, red_unreachable(rules, 99)).status_code == 200
    submit(client_for(seeded_app, "patient2"), [("fever", "presence", 1)])
    reds = alerts_of(seeded_app, "SYN-0002", "R-URG-01")
    assert reds or not accepted  # entweder abgelehnt oder die Meldung entsteht trotzdem


@pytest.mark.parametrize(
    "literal",
    [
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_a3_non_finite_numbers_never_become_an_active_version(
    seeded_app: FastAPI, literal: str
) -> None:
    admin = client_for(seeded_app, "admin")
    version, rules = current_rules(seeded_app)
    raw = json.dumps({"expected_version": version, "rules": red_unreachable(rules, "@@")})
    raw = raw.replace('"@@"', literal)
    response = admin.put(
        f"{BASE}/config/rules",
        content=raw,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (400, 422), (response.status_code, response.text)
    assert versions(seeded_app, "rules") == ["rules-v1"]


def test_a3_rules_and_report_change_independently_in_parallel(
    seeded_app: FastAPI,
) -> None:
    rules_version, rules = current_rules(seeded_app)
    report_version, report = current_report(seeded_app)
    changed_rules = copy.deepcopy(rules)
    next(r for r in changed_rules["rules"] if r["id"] == "R-SEV-01")["params"]["min_value"] = 4
    admins = [client_for(seeded_app, "admin") for _ in range(8)]

    def action(i: int) -> Any:
        if i % 2 == 0:
            return (
                "rules",
                put_rules(admins[i], rules_version, changed_rules, f"r{i}"),
            )
        return (
            "report",
            admins[i].put(
                f"{BASE}/config/report",
                json={
                    "expected_version": report_version,
                    "report": report,
                    "change_note": f"p{i}",
                },
            ),
        )

    results = run_parallel(action, 8)
    for kind in ("rules", "report"):
        codes = sorted(r.status_code for k, r in results if k == kind)
        assert codes == [200, 409, 409, 409], (kind, codes)
        assert versions(seeded_app, kind) == [f"{kind}-v1", f"{kind}-v2"]
