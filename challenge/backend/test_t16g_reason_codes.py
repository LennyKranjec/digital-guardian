"""T-16G (A0): Begründungen an Meldungen als Objekte, lokalisiert; Altbestand tolerant."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from waechter.services.alerts import explanation_view


def _alert(triage: dict[str, Any]) -> Any:
    return SimpleNamespace(explanation_json={"kind": "triage", "triage": triage})


def test_reason_codes_are_objects_with_text_in_the_requested_language() -> None:
    stored = {
        "level": "red",
        "reason_codes": [
            {
                "code": "F_FEVER",
                "kind": "shield",
                "items": ["fever"],
                "text_i18n": {"cs": "Horečka", "en": "Fever", "de": "Fieber"},
            }
        ],
    }
    for lang, text in (("cs", "Horečka"), ("en", "Fever"), ("de", "Fieber"), ("xx", "Fever")):
        view = explanation_view(_alert(stored), lang)["triage"]["reason_codes"]
        assert view == [{"code": "F_FEVER", "kind": "shield", "items": ["fever"], "text": text}]


def test_legacy_string_reason_codes_become_objects() -> None:
    view = explanation_view(_alert({"level": "red", "reason_codes": ["F_FEVER"]}), "cs")
    assert view["triage"]["reason_codes"] == [{"code": "F_FEVER", "text": "F_FEVER"}]


def test_stored_explanation_is_not_mutated() -> None:
    stored = {"level": "red", "reason_codes": ["F_FEVER"]}
    alert = _alert(stored)
    explanation_view(alert, "cs")
    assert alert.explanation_json["triage"]["reason_codes"] == ["F_FEVER"]
