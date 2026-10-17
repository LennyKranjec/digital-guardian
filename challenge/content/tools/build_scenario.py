"""Erzeugt challenge/content/scenario.yaml (synthetisch) und schreibt das Testorakel `expected` aus tools/oracle.py.

Aufruf:  python challenge/content/tools/build_scenario.py
Alle Werte sind frei erfunden (keine echten Personendaten). Verläufe sind deterministisch (keine Zufallszahlen).
Die Fragebogenzusammenstellung (Kern + Profil des Regimes) wird aus items.yaml/regimens.yaml abgeleitet.
Das Orakel bricht ab, wenn ein Verlauf von der Auslegung des Vertrags (Fenstergrenzen, Tagesbegriff) abhängt.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import oracle
import yaml

CONTENT = Path(__file__).resolve().parent.parent
ANCHOR = "2026-10-17T09:00:00+02:00"


class Flow(dict):
    """Mapping, das in YAML im Fluss-Stil (eine Zeile) ausgegeben wird."""


yaml.SafeDumper.add_representer(
    Flow, lambda d, data: d.represent_mapping("tag:yaml.org,2002:map", data, flow_style=True)
)


def questionnaire_keys(regimen_id: str) -> list[str]:
    items = yaml.safe_load((CONTENT / "items.yaml").read_text(encoding="utf-8"))["items"]
    regimens = yaml.safe_load((CONTENT / "regimens.yaml").read_text(encoding="utf-8"))["regimens"]
    profile = next(r for r in regimens if r["id"] == regimen_id)["symptom_keys"]
    keys: list[str] = []
    for it in items:
        if it.get("core") or it["symptom_key"] in profile:
            keys += [f"{it['symptom_key']}.{a['attribute']}" for a in it["attributes"]]
    return keys


def cyc(pattern: list[int | None]) -> list[int | None]:
    """Wiederholt `pattern` beliebig lang (Index i → pattern[i % len])."""
    return pattern * 40


def build_patient(
    spec: dict[str, Any],
    days: list[int],
    series: dict[str, list[int | None]],
    hours: dict[int, int] | None = None,
    channels: dict[int, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    keys = questionnaire_keys(spec["regimen_id"])
    unknown = set(series) - set(keys)
    assert not unknown, (
        f"{spec['pseudonym']}: Reihen für Schlüssel außerhalb des Fragebogens: {unknown}"
    )
    responses = []
    for i, d in enumerate(days):
        answers = Flow()
        for k in keys:
            answers[k] = series[k][i] if k in series else 0
        r: dict[str, Any] = {"day_offset": d, "hour": (hours or {}).get(d, spec.get("hour", 19))}
        ch, by = (channels or {}).get(d, ("web", "self"))
        r["channel"] = ch
        r["entered_by"] = by
        r["answers"] = answers
        responses.append(r)
    return {**{k: v for k, v in spec.items() if k != "hour"}, "responses": responses}


def at(days: list[int], values: dict[int, int | None], default: int = 0) -> list[int | None]:
    """Reihe über `days`: Wert je Tag aus `values`, sonst `default`."""
    return [values.get(d, default) for d in days]


def steps(days: list[int], start_one: int | None, start_two: int | None) -> list[int]:
    """Stufenverlauf 0 → 1 (ab Tag start_one) → 2 (ab Tag start_two)."""
    out = []
    for d in days:
        out.append(
            2
            if start_two is not None and d >= start_two
            else 1
            if start_one is not None and d >= start_one
            else 0
        )
    return out


def main() -> int:
    patients: list[dict[str, Any]] = []

    # --- SYN-0001 (Hauptdemo, Konto "patient"): FOLFOX, letzter Termin Tag -14, geplant Tag +1 ---------------------------
    d1 = [
        d for d in range(-20, 0) if d not in (-13, -12)
    ]  # Lücke: 2 fehlende Tage (-13, -12); letzte Antwort Tag -1
    n1 = len(d1)
    s1: dict[str, list[int | None]] = {
        "fatigue.severity": [min(1, x) for x in cyc([0, 1, 1, 1, 0, 1, 1, 1, 1, 0])[:n1]],
        "fatigue.interference": at(d1, {-19: 1, -14: 1, -11: 1, -6: 1}),
        "nausea.frequency": at(d1, {-19: 1, -14: 1, -11: 1, -5: 1}),
        "nausea.severity": at(d1, {-19: 1, -14: 1, -11: 1, -15: None, -5: 1}),
        "vomiting.frequency": at(d1, {-11: 1}),
        "pain.severity": at(d1, {-16: 1, -10: 1, -6: 1, -3: 1}),
        "pain.interference": at(d1, {-10: None, -3: None}),
        "mouth_sores.severity": at(d1, {-11: 1, -10: 1, -4: 1}),
        "mouth_sores.interference": at(d1, {-6: None}),
        # schleichender Anstieg der Neuropathie (Schwere 0 → 1 → 2) ⇒ R-TRD-01; Beeinträchtigung bleibt ≤ 1
        "peripheral_neuropathy.severity": steps(d1, -9, -6),
        "peripheral_neuropathy.interference": at(d1, {-6: 1, -5: 1, -4: 1, -3: 1, -2: 1, -1: 1}),
        # Durchfall steigt auf Schwere 3 an Tag -1 ⇒ R-SEV-01 (Vorwerte so, dass R-DLT-01/R-TRD-01 nicht zusätzlich auslösen)
        "diarrhea.severity": at(
            d1, {**dict.fromkeys(range(-14, -5), 1), **dict.fromkeys(range(-5, -1), 2), -1: 3}
        ),
        "diarrhea.frequency": at(d1, {-3: 1, -2: 1, -1: 1}),
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0001",
                "display_name": "patient",
                "birth_year": 1968,
                "sex": "female",
                "language": "cs",
                "diagnosis_text": "Kolorektální karcinom, adjuvantní léčba (syntetický příklad)",
                "diagnosis_code": "C18.7",
                "regimen_id": "FOLFOX",
                "cycle_start_offset": -14,
                "username": "patient",
                "hour": 19,
                "visits": [
                    {"day_offset": -28, "kind": "past"},
                    {"day_offset": -14, "kind": "past"},
                    {"day_offset": 1, "kind": "planned"},
                ],
            },
            d1,
            s1,
        )
    )

    # --- SYN-0002 grün: Pembrolizumab, mild und stabil, letzte Antwort heute 07:00 ------------------------------------------
    d2 = list(range(-20, 1))
    s2: dict[str, list[int | None]] = {
        "fatigue.severity": [min(1, x) for x in cyc([1, 1, 0, 1, 0, 1, 1, 0])[: len(d2)]],
        "fatigue.interference": cyc([0, 0, 1, 0, 0, 0, 0, 1])[: len(d2)],
        "diarrhea.frequency": cyc([0, 0, 0, 1, 0, 0, 0, 0, 0, 1])[: len(d2)],
        "rash.severity": at(d2, {-10: 1, -9: 1, -8: 1, -2: 1}),
        "decreased_appetite.severity": cyc([0, 0, 1, 0, 0, 0, 1, 0, 0])[: len(d2)],
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0002",
                "display_name": "patient2",
                "birth_year": 1957,
                "sex": "male",
                "language": "cs",
                "diagnosis_text": "Melanom, imunoterapie (syntetický příklad)",
                "diagnosis_code": "C43.9",
                "regimen_id": "PEMBROLIZUMAB",
                "cycle_start_offset": -10,
                "username": "patient2",  # Vertrag v1.1 G-14: E2E sendet hier Fieber = 1 (grün am Anker)
                "hour": 7,
                "visits": [
                    {"day_offset": -10, "kind": "past"},
                    {"day_offset": 11, "kind": "planned"},
                ],
            },
            d2,
            s2,
        )
    )

    # --- SYN-0003 gelb: Capecitabin, Hand-Fuß-Beschwerden 0 → 2 an Tag -2 ⇒ R-DLT-01 (Schwere 2 < Schwelle R-SEV-01) ------
    d3 = list(range(-20, 1))
    s3: dict[str, list[int | None]] = {
        "fatigue.severity": [min(1, x) for x in cyc([0, 1, 0, 1, 1, 0, 0])[: len(d3)]],
        "diarrhea.frequency": at(d3, {-15: 1, -14: 1, -9: 1}),
        "hand_foot.severity": at(d3, {-2: 2, -1: 2, 0: 2}),
        "hand_foot.interference": at(d3, {-1: 1, 0: 1}),
        "decreased_appetite.severity": at(d3, {-12: 1, -11: 1}),
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0003",
                "display_name": "SYN-0003",
                "birth_year": 1974,
                "sex": "female",
                "language": "cs",
                "diagnosis_text": "Kolorektální karcinom, perorální chemoterapie (syntetický příklad)",
                "diagnosis_code": "C20",
                "regimen_id": "CAPECITABINE",
                "cycle_start_offset": -8,
                "hour": 20,
                "visits": [
                    {"day_offset": -8, "kind": "past"},
                    {"day_offset": 13, "kind": "planned"},
                ],
            },
            d3,
            s3,
            hours={0: 7},
            channels={-6: ("phone", "nurse"), -5: ("phone", "nurse")},
        )
    )

    # --- SYN-0004 grau: FOLFOX, letzte Antwort Tag -5 (18:00) ⇒ R-MIS-01 (nur Ampel) -----------------------------------------
    d4 = list(range(-20, -4))
    s4: dict[str, list[int | None]] = {
        "fatigue.severity": [min(1, x) for x in cyc([1, 0, 1, 1, 0, 0, 1])[: len(d4)]],
        "nausea.frequency": at(d4, {-16: 1, -15: 1}),
        "peripheral_neuropathy.severity": at(
            d4, {-12: 1, -11: 1, -10: 1, -9: 1, -8: 1, -7: 1, -6: 1, -5: 1}
        ),
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0004",
                "display_name": "SYN-0004",
                "birth_year": 1962,
                "sex": "male",
                "language": "cs",
                "diagnosis_text": "Kolorektální karcinom, chemoterapie (syntetický příklad)",
                "diagnosis_code": "C18.2",
                "regimen_id": "FOLFOX",
                "cycle_start_offset": -12,
                "hour": 18,
                "visits": [
                    {"day_offset": -12, "kind": "past"},
                    {"day_offset": 2, "kind": "planned"},
                ],
            },
            d4,
            s4,
        )
    )

    # --- SYN-0005 rot (Fieber): Docetaxel, Fieber ja an Tag 0 ⇒ R-URG-01 ----------------------------------------------------
    d5 = list(range(-20, 1))
    s5: dict[str, list[int | None]] = {
        "fatigue.severity": [min(1, x) for x in cyc([1, 1, 0, 1, 0, 1, 1])[: len(d5)]],
        "mouth_sores.severity": at(d5, {-17: 1, -16: 1, -15: 1}),
        "peripheral_neuropathy.severity": at(
            d5, {-12: 1, -11: 1, -10: 1, -9: 1, -3: 1, -2: 1, -1: 1, 0: 1}
        ),
        "fever.presence": at(d5, {0: 1}),
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0005",
                "display_name": "SYN-0005",
                "birth_year": 1980,
                "sex": "female",
                "language": "en",
                "diagnosis_text": "Breast cancer, docetaxel (synthetic example)",
                "diagnosis_code": "C50.9",
                "regimen_id": "DOCETAXEL",
                "cycle_start_offset": -3,
                "hour": 20,
                "visits": [
                    {"day_offset": -3, "kind": "past"},
                    {"day_offset": 18, "kind": "planned"},
                ],
            },
            d5,
            s5,
            hours={0: 7},
        )
    )

    # --- SYN-0006 (T-20, C61, Enzalutamid; Hauptfall Prostata): schleichende Müdigkeit ⇒ R-TRD-01 gelb; Fieber ja an Tag 0 ⇒ R-URG-01 rot --
    d6 = list(range(-20, 1))
    s6: dict[str, list[int | None]] = {
        # Schwere der Müdigkeit steigt schleichend 0 → 1 (ab Tag -17) → 2 (ab Tag -13) ⇒ R-TRD-01; Beeinträchtigung bleibt niedrig
        "fatigue.severity": steps(d6, -17, -13),
        "fatigue.interference": at(d6, {-9: 1, -4: 1, -3: 1, -1: 1}),
        "nausea.frequency": at(d6, {-12: 1, -11: 1}),
        "decreased_appetite.severity": at(d6, {-8: 1, -7: 1, -6: 1}),
        "pain.severity": at(d6, {-16: 1, -15: 1, -3: 1}),
        "fever.presence": at(d6, {0: 1}),
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0006",
                "display_name": "patient6",
                "birth_year": 1951,
                "sex": "male",
                "language": "cs",
                "diagnosis_text": "Karcinom prostaty, hormonální léčba (syntetický příklad)",
                "diagnosis_code": "C61",
                "regimen_id": "ENZALUTAMIDE",
                "cycle_start_offset": -10,
                "hour": 19,
                "visits": [
                    {"day_offset": -10, "kind": "past"},
                    {"day_offset": 18, "kind": "planned"},
                ],
            },
            d6,
            s6,
            hours={0: 7},
        )
    )

    # --- SYN-0007 (T-20, C64, Pazopanib): Durchfall 0 → 2 an Tag -3 ⇒ R-DLT-01 gelb; Hand-Fuß 0 → 2 an Tag -1 ⇒ R-DLT-01 gelb -----------
    d7 = list(range(-20, 1))
    s7: dict[str, list[int | None]] = {
        "diarrhea.severity": at(d7, {-3: 2, -2: 2, -1: 1, 0: 1}),
        "diarrhea.frequency": at(d7, {-3: 1, -2: 1}),
        "hand_foot.severity": at(d7, {-1: 2, 0: 2}),
        "hand_foot.interference": at(d7, {0: 1}),
        "fatigue.severity": [min(1, x) for x in cyc([0, 1, 0, 0, 1, 1, 0, 1])[: len(d7)]],
        "decreased_appetite.severity": at(d7, {-6: 1, -5: 1, -4: 1}),
        "nausea.frequency": at(d7, {-3: 1, -2: 1}),
    }
    patients.append(
        build_patient(
            {
                "pseudonym": "SYN-0007",
                "display_name": "SYN-0007",
                "birth_year": 1959,
                "sex": "female",
                "language": "cs",
                "diagnosis_text": "Karcinom ledviny, cílená léčba (syntetický příklad)",
                "diagnosis_code": "C64",
                "regimen_id": "PAZOPANIB",
                "cycle_start_offset": -12,
                "hour": 19,
                "visits": [
                    {"day_offset": -12, "kind": "past"},
                    {"day_offset": 16, "kind": "planned"},
                ],
            },
            d7,
            s7,
            hours={0: 7},
        )
    )

    scenario: dict[str, Any] = {
        "version": "scenario-v1",
        "anchor": ANCHOR,
        "synthetic": True,
        "patients": patients,
    }
    rules = yaml.safe_load((CONTENT / "rules.yaml").read_text(encoding="utf-8"))
    oracle_scenario = {**scenario, "anchor": datetime.fromisoformat(ANCHOR)}
    for p in patients:
        p["expected"] = oracle.expected_block(oracle.oracle(rules, oracle_scenario, p))
    header = (
        "# scenario.yaml – SYNTHETISCHE Demo-Patient:innen (ScenarioFile, Vertrag v1). Owner: A1 (T-01).\n"
        "# Alle Personen, Werte und Termine sind frei erfunden; keine echten Personendaten. Erzeugt mit tools/build_scenario.py,\n"
        "# `expected` aus tools/oracle.py (unabhängig, exakte Bruchrechnung, auslegungsrobust).\n"
        "# Prüft Softwareverhalten (Regeln, Rauschbremse, Ampel), NICHT fachliche Güte. day_offset relativ zu anchor (APP_FROZEN_NOW).\n"
        "# Seed: nichts quittiert. R-MIS-01 erscheint nur in traffic_light_at_anchor, nie in alerts (Vertrag §3).\n"
        "# Dedupe: je (Regel, Symptom, Attribut) höchstens eine offene Meldung ⇒ erwartet wird nur der erste Auslösetag.\n"
        "# SYN-0001 = Hauptdemo (Konto `patient`): letzte Antwort Tag -1; Lücke Tage -13/-12; einzelne null-Antworten (übersprungen).\n"
        "# SYN-0006 (C61, Enzalutamid; Hauptfall Prostata) und SYN-0007 (C64, Pazopanib) seit T-20 (Vertrag v2.8); SYN-0001…0005 unverändert.\n"
    )
    text = yaml.safe_dump(scenario, allow_unicode=True, sort_keys=False, width=140)
    (CONTENT / "scenario.yaml").write_text(header + text, encoding="utf-8", newline="\n")
    print("scenario.yaml geschrieben:", len(patients), "Patient:innen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
