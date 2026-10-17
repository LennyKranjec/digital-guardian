# ruff: noqa: F401
"""A3-Gegenproben zu T-07 (Besitz A3): Policy-Filter gegen Umformulierungen, Wiederholung nach
fehlgeschlagenem Live-Versuch. Hilfen aus `test_summary.py`; kein Netz.
"""

from typing import Any

import pytest
from fastapi import FastAPI

from test_summary import BASE, Gateway, configure_openai, pid, staff
from waechter.llm import adapters
from waechter.llm.verifier import verify

FACTS = {
    "resp-1": "Letzte Antwort 2026-10-16: Fieber ja, Durchfall Stufe 2.",
    "alert-1": "Offene rote Meldung R-URG-01: Fieber ja seit 2026-10-16.",
    "obs-2": "Übelkeit: erster Wert 1, letzter Wert 3 (steigend).",
}

#: Gültige Kontrollsätze (müssen bleiben) - schützen den Test vor "alles wird verworfen".
VALID = [
    "Fieber ja am 2026-10-16. [alert-1]",
    "Durchfall Stufe 2. [resp-1]",
    "Übelkeit: letzter Wert 3. [obs-2]",
]
#: Verletzungen der Policy (Therapieänderung, Ursache, Diagnose-Vermutung, Beruhigung, Handlung),
#: bewusst ohne die Wörter der Verbotsliste, ohne Zahlen, mit gültigem Beleg.
PARAPHRASES = [
    "Die Dosis sollte reduziert werden. [resp-1]",
    "The dose should be lowered. [resp-1]",
    "Die Chemotherapie sollte pausiert werden. [alert-1]",
    "Therapy should be paused. [alert-1]",
    "Die Übelkeit ist eine Nebenwirkung von Cisplatin. [obs-2]",
    "Das Fieber kommt von der Chemotherapie. [alert-1]",
    "Fever results from the chemotherapy. [alert-1]",
    "Die Patientin hat vermutlich eine Infektion. [alert-1]",
    "The patient probably has an infection. [alert-1]",
    "Ein Arztbesuch ist nicht nötig. [resp-1]",
    "No visit is necessary. [resp-1]",
    "Bitte ruft die Patientin sofort an. [alert-1]",
]
WRONG = [
    "Durchfall Stufe 3. [resp-1]",  # falsche Zahl
    "Fieber ja am 2026-10-15. [alert-1]",  # falsches Datum
    "Fieber ja. [alert-9]",  # erfundener Beleg
    "Fieber ja.",  # ohne Beleg
]


@pytest.mark.parametrize("sentence", VALID)
def test_a3_valid_sentences_are_kept(sentence: str) -> None:
    assert verify(sentence, FACTS).dropped == 0


@pytest.mark.parametrize("sentence", WRONG)
def test_a3_wrong_numbers_dates_and_references_are_dropped(sentence: str) -> None:
    assert verify(sentence, FACTS).dropped == 1


@pytest.mark.parametrize("sentence", PARAPHRASES)
def test_a3_paraphrased_policy_violations_are_dropped(sentence: str) -> None:
    assert verify(sentence, FACTS).dropped == 1


def test_a3_paraphrased_policy_violation_never_reaches_the_clinician(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    seen = doctor.get(f"{BASE}/patients/{p}/summary").json()["sentences"]
    alert = next(r for s in seen for r in s["refs"] if r.startswith("alert-"))
    configure_openai(monkeypatch)
    monkeypatch.setattr(
        adapters,
        "_urlopen",
        Gateway(
            f"Es gibt eine rote Meldung [{alert}]. Die Dosis sollte reduziert werden [{alert}]."
        ),
    )
    data = doctor.post(f"{BASE}/patients/{p}/summary").json()
    texts = [s["text"] for s in data["sentences"]]
    assert "Die Dosis sollte reduziert werden." not in texts
    assert any("rote Meldung" in t for t in texts)  # Kontrolle: gültiger Satz bleibt


def test_a3_failed_live_attempt_is_retried_on_the_next_post(
    seeded_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    doctor = staff(seeded_app)
    p = pid(seeded_app, "SYN-0001")
    seen = doctor.get(f"{BASE}/patients/{p}/summary").json()["sentences"]
    alert = next(r for s in seen for r in s["refs"] if r.startswith("alert-"))
    configure_openai(monkeypatch)
    monkeypatch.setattr(adapters, "_urlopen", Gateway(None))  # Gateway down (404)
    first = doctor.post(f"{BASE}/patients/{p}/summary").json()
    assert first["mode"] == "fallback"
    monkeypatch.setattr(adapters, "_urlopen", Gateway(f"Es gibt eine rote Meldung [{alert}]."))
    second = doctor.post(f"{BASE}/patients/{p}/summary").json()
    assert second["mode"] == "live"
