"""T-24 (A0): Proof of Concept „Module je Wirkstoffklasse“ und Diagnosemodule (Hooks H1/H2).

- Klassenprofile (`chemo`, `ici`, `hormonal`, `tki`) sind über `includes` als Module einbindbar.
- Diagnosemodule (`modules:`) ergeben je Blattprofil eine Variante `<Profil>+<Modul>`.
- Alles läuft über dieselbe Zusammenführung wie die Vererbung: nur verschärfend.
- Bestehende Profile, ihre Hashes und Bäume bleiben unverändert.
"""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from test_a3_t13 import (  # noqa: F401
    BASE,
    api,
    client_for,
    real_template,
)
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import content_dir, load_content
from waechter.models import Patient
from waechter.services import triage as triage_service
from waechter.triage.kb import TriageError, build_kb, load_kb, read_triage_yaml
from waechter.triage.runtime import runtime_for

SESSIONS = f"{BASE}/me/sessions"
REAL = Path(__file__).resolve().parents[1] / "content"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Echte Wissensbasis (Fixture-Welt hat keine triage.yaml)."""
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def _raw() -> Any:
    return copy.deepcopy(read_triage_yaml(content_dir()))


def _build(raw: Any) -> Any:
    content = load_content(content_dir())
    attributes = {
        item["symptom_key"]: [a["attribute"] for a in item["attributes"]]
        for item in content.items["items"]
    }
    regimens = {r["id"]: list(r["symptom_keys"]) for r in content.regimens["regimens"]}
    groups = [g["id"] for g in content.diagnoses["diagnoses"]] if content.diagnoses else None
    return build_kb(raw, attributes=attributes, regimens=regimens, diagnosis_groups=groups)


def test_existing_profiles_are_unchanged_by_modules() -> None:
    """Golden-Schutz: ohne `modules` und ohne Kombinationsprofil sind alle Profil-Hashes gleich."""
    kb = load_kb()
    raw = _raw()
    raw.pop("modules", None)
    raw["profiles"] = [p for p in raw["profiles"] if not p.get("includes")]
    plain = _build(raw)
    assert sorted(plain.profiles) == sorted(kb.profiles)
    for profile_id, profile in kb.profiles.items():
        assert plain.profiles[profile_id].hash == profile.hash, profile_id
    assert not plain.compositions


def test_class_module_profile_is_the_union_of_its_classes() -> None:
    kb = load_kb()
    combo = kb.profile("COMBO_ICI_TKI")
    by_id = {p["id"]: p for p in kb.raw["profiles"]}
    ici, tki = by_id["ici"], by_id["tki"]
    for symptom in [*ici.get("fixed_items", []), *tki.get("fixed_items", [])]:
        assert symptom in combo.fixed_items
    assert "shortness_of_breath" in combo.safety_items
    floors = {f.id for f in combo.floors}
    assert {"F_ICI_DIARRHEA", "F_ICI_DYSPNEA"} <= floors  # Böden bleiben erhalten
    assert combo.lineage == ("base", "ici", "COMBO_ICI_TKI", "tki")
    assert "COMBO_ICI_TKI" not in kb.profiles  # nicht Teil der Regime-Profile


def test_diagnosis_module_adds_its_questions_to_every_leaf_profile() -> None:
    kb = load_kb()
    assert kb.diagnosis_modules == {"LUNG": "mod-dx-lung"}
    for profile_id in kb.profiles:
        variant = kb.profile(f"{profile_id}+mod-dx-lung")
        assert "shortness_of_breath" in variant.safety_items
        assert "decreased_appetite" in variant.fixed_items
        assert "decreased_appetite" not in variant.rotation_pool  # fest gefragt ⇒ nicht rotiert
        assert set(kb.profile(profile_id).symptoms) <= set(variant.symptoms)
        assert variant.hash != kb.profile(profile_id).hash
    assert kb.variant_for("FOLFOX", "LUNG") == "FOLFOX+mod-dx-lung"
    assert kb.variant_for("FOLFOX", "COLORECTAL") == "FOLFOX"
    assert kb.variant_for("FOLFOX", None) == "FOLFOX"


def test_a_module_cannot_loosen_an_inherited_rule() -> None:
    raw = _raw()
    module = raw["modules"][0]
    module.setdefault("teacher", {}).setdefault("red", []).append(
        {
            "id": "R_CRIT_G3",  # Basisregel „kritisch ≥ 3“ auf ≥ 4 abschwächen
            "when": "max_critical >= 4",
            "text": {"cs": "x", "en": "x"},
            "assumption": "A-TRI-17",
            "status": "placeholder",
        }
    )
    with pytest.raises(TriageError, match="loosens an inherited rule"):
        _build(raw)


def test_includes_must_name_a_class_profile() -> None:
    raw = _raw()
    combo = next(p for p in raw["profiles"] if p["id"] == "COMBO_ICI_TKI")
    combo["includes"] = ["FOLFOX"]  # Blattprofil mit Regime ist kein Modul
    with pytest.raises(TriageError, match="not a class profile"):
        _build(raw)
    combo["includes"] = ["does-not-exist"]
    with pytest.raises(TriageError, match="unknown class profile"):
        _build(raw)


@pytest.mark.parametrize("profile_id", ["COMBO_ICI_TKI", "PEMBROLIZUMAB+mod-dx-lung"])
def test_composed_profiles_compile_and_verify_clean(profile_id: str) -> None:
    runtime = runtime_for(load_kb(), profile_id)
    report = runtime.report.to_dict()
    assert (report["under"], report["over"], report["monotone_violations"]) == (0, 0, 0)
    assert report["points"] > 0


def test_lung_patient_gets_the_variant_and_the_session_asks_dyspnea(
    api: tuple[FastAPI, Any],  # noqa: F811
) -> None:
    app, _ = api
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one()
        kb = triage_service.get_kb()
        assert kb is not None
        assert triage_service.profile_id_for(kb, session, patient.id) == "FOLFOX"
        patient.diagnosis_code = "C34.1"  # synthetisch: Lungenkarzinom
        session.commit()
        assert triage_service.profile_id_for(kb, session, patient.id) == "FOLFOX+mod-dx-lung"
    client = client_for(app, "patient")
    reply = client.post(SESSIONS, json={"client_session_id": str(uuid.uuid4())})
    assert reply.status_code in (200, 201), reply.text
    step = reply.json()
    asked: list[str] = []
    for _ in range(40):
        question = step.get("next")
        if not question:
            break
        asked.append(question["symptom_key"])
        reply = client.post(
            f"{SESSIONS}/{step['session_id']}/answers",
            json={
                "symptom_key": question["symptom_key"],
                "attribute": question["attribute"],
                "value": 0,
            },
        )
        assert reply.status_code == 200, reply.text
        step = reply.json()
    assert "shortness_of_breath" in asked  # Diagnose-Zusatzfrage in der adaptiven Sitzung
