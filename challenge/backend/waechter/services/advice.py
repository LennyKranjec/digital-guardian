"""Empfehlungsregeln ADV-xx und Rady pacientovi (Vertrag v1.9/v1.10/v2.1, `triage.md` §6).

Reine, deterministische Auswertung (keine Uhr, kein Zufall, kein LLM, keine Bewertung durch ein
Modell). Eine Regel feuert, wenn irgendein beantwortetes Attribut des Symptoms im Bereich
`[min_value, max_value]` liegt. **Unterdrückt** (`suppressed_acute`, keine Tipps, nur der
Akut-Hinweis) wird sie, wenn das Symptom eine rote Regel auslöst oder in `always_acute_for` steht.
Der Akut-Hinweis (`escalation.level = acute`) gilt, wenn für diese Antwort irgendeine rote Regel
feuert oder ein Symptom aus `always_acute_for` mit Wert ≥ 1 gemeldet wurde.

Patient:innen sehen nie Ampel, Regel-Text, Grad oder Schwelle; `rule_id` steht im Beleg, die UI
zeigt sie nicht. Die Ärztin sieht `Recommendation` später in der Befundkarte (T-16).
"""

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from waechter.content import Content
from waechter.models import Answer, Response
from waechter.services import alerts
from waechter.services.config import active_body
from waechter.services.questionnaire import Selection, localize

LEVEL_ACUTE: Final = "acute"
LEVEL_GENERAL: Final = "general"
SHOWN: Final = "shown"
SUPPRESSED_ACUTE: Final = "suppressed_acute"
DEFAULT_MAX_VALUE: Final = 4
_PLACEHOLDER = re.compile(r"^\s*\[.*\]\s*$")

type Key = tuple[str, str]
type Answers = Mapping[Key, int | None]


@dataclass(frozen=True)
class Recommendation:
    """Ergebnis einer Empfehlungsregel zu einer Antwort (Befundkarte: ID, Symptom, Wert, Status)."""

    rule_id: str
    symptom_key: str
    value: int
    status: Literal["shown", "suppressed_acute"]


def phone_or_none(value: str | None) -> str | None:
    """Telefonnummer der Ambulanz; ein Platzhalter in eckigen Klammern wird nie angezeigt."""
    if value is None or not value.strip() or _PLACEHOLDER.match(value):
        return None
    return value.strip()


def _values_by_symptom(answers: Answers) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for (symptom, _attribute), value in answers.items():
        if value is not None:
            found.setdefault(symptom, []).append(value)
    return found


def always_acute(advice: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(advice["escalation"].get("always_acute_for", []))


def is_acute(advice: Mapping[str, Any], answers: Answers, red_symptoms: Collection[str]) -> bool:
    """Akut-Hinweis nötig: rote Regel für diese Antwort oder `always_acute_for` mit Wert ≥ 1."""
    if red_symptoms:
        return True
    values = _values_by_symptom(answers)
    return any(max(values.get(s, [0])) >= 1 for s in always_acute(advice))


def recommendations_for(
    advice: Mapping[str, Any], answers: Answers, red_symptoms: Collection[str]
) -> list[Recommendation]:
    """Alle feuernden Regeln in Dateireihenfolge; reine Funktion der drei Argumente."""
    values = _values_by_symptom(answers)
    suppressed = set(red_symptoms) | always_acute(advice)
    result: list[Recommendation] = []
    for rule in advice["advice"]:
        low, high = rule["min_value"], rule.get("max_value", DEFAULT_MAX_VALUE)
        matching = [v for v in values.get(rule["symptom_key"], []) if low <= v <= high]
        if not matching:
            continue
        status: Literal["shown", "suppressed_acute"] = (
            SUPPRESSED_ACUTE if rule["symptom_key"] in suppressed else SHOWN
        )
        result.append(Recommendation(rule["id"], rule["symptom_key"], max(matching), status))
    return result


def stored_answers(session: Session, response_id: str) -> dict[Key, int | None]:
    rows = session.scalars(select(Answer).where(Answer.response_id == response_id)).all()
    return {(a.symptom_key, a.attribute): a.value for a in rows}


def evaluate_recommendations(
    session: Session, response: Response, content: Content
) -> list[Recommendation]:
    """Empfehlungen zu einer gespeicherten Antwort (wiederverwendbar, z. B. für T-16)."""
    if content.advice is None:
        return []
    rules = active_body(session, "rules") or content.rules
    red = alerts.red_symptom_keys(session, response, rules)
    return recommendations_for(content.advice, stored_answers(session, response.id), red)


def evaluate_with_escalation(
    session: Session, response: Response, content: Content
) -> tuple[list[Recommendation], bool]:
    """`(Empfehlungen, akut)` mit einmaliger Auswertung der roten Regeln."""
    if content.advice is None:
        return [], False
    rules = active_body(session, "rules") or content.rules
    red = alerts.red_symptom_keys(session, response, rules)
    answers = stored_answers(session, response.id)
    return (
        recommendations_for(content.advice, answers, red),
        is_acute(content.advice, answers, red),
    )


def escalation_body(content: Content, lang: str, *, acute: bool) -> dict[str, Any]:
    if content.advice is None:
        raise ValueError("advice.yaml is not loaded")
    block = content.advice["escalation"]
    return {
        "level": LEVEL_ACUTE if acute else LEVEL_GENERAL,
        "text": localize(block["acute" if acute else "general"], lang),
        "ambulance_phone": phone_or_none(block.get("ambulance_phone")),
    }


def _sources(advice: Mapping[str, Any], ids: list[str]) -> list[dict[str, str]]:
    by_id = {s["id"]: s for s in advice.get("sources", [])}
    out: list[dict[str, str]] = []
    for source_id in ids:
        source = by_id.get(source_id)
        if source is None:
            continue
        entry = {"id": source["id"], "title": source["title"]}
        if source.get("url"):
            entry["url"] = source["url"]
        out.append(entry)
    return out


def _label(content: Content, symptom_key: str, lang: str) -> str:
    for item in content.items["items"]:
        if item["symptom_key"] == symptom_key:
            return localize(item["label"], lang)
    return symptom_key


def _rule(advice: Mapping[str, Any], rule_id: str) -> Mapping[str, Any]:
    return next(r for r in advice["advice"] if r["id"] == rule_id)


def receipt_parts(
    content: Content, recommendations: list[Recommendation], lang: str, *, acute: bool
) -> dict[str, Any]:
    """`advice[]` (nur `shown`) und `escalation` für den Beleg; leer ohne advice.yaml."""
    if content.advice is None:
        return {}
    shown: list[dict[str, Any]] = []
    for rec in recommendations:
        if rec.status != SHOWN:
            continue
        rule = _rule(content.advice, rec.rule_id)
        shown.append(
            {
                "rule_id": rec.rule_id,
                "symptom_key": rec.symptom_key,
                "label": _label(content, rec.symptom_key, lang),
                "tips": [localize(tip, lang) for tip in rule["tips"]],
                "sources": _sources(content.advice, rule["source_ids"]),
            }
        )
    return {"advice": shown, "escalation": escalation_body(content, lang, acute=acute)}


def fallback_parts(content: Content, lang: str) -> dict[str, Any]:
    """Wenn die Auswertung scheitert: nie unterwarnen (Akut-Hinweis), keine Tipps."""
    if content.advice is None:
        return {}
    return {"advice": [], "escalation": escalation_body(content, lang, acute=True)}


def help_page(content: Content, selection: Selection, lang: str) -> dict[str, Any]:
    """`GET /me/advice`: alle Regeln der Symptome des eigenen Fragebogens, lokalisiert.

    Symptome aus `always_acute_for` erscheinen ohne Tipps (`acute_only`), nur mit dem Hinweis.
    """
    advice = content.advice
    if advice is None:
        return {"lang": lang, "advice": [], "escalation": None}
    keys = {item["symptom_key"] for item, _ in selection.items}
    acute_only = always_acute(advice)
    rules: list[dict[str, Any]] = []
    for rule in advice["advice"]:
        if rule["symptom_key"] not in keys:
            continue
        hidden = rule["symptom_key"] in acute_only
        rules.append(
            {
                "rule_id": rule["id"],
                "symptom_key": rule["symptom_key"],
                "label": _label(content, rule["symptom_key"], lang),
                "acute_only": hidden,
                "tips": [] if hidden else [localize(tip, lang) for tip in rule["tips"]],
                "sources": [] if hidden else _sources(advice, rule["source_ids"]),
            }
        )
    block = advice["escalation"]
    return {
        "lang": lang,
        "escalation": {
            "general": localize(block["general"], lang),
            "acute": localize(block["acute"], lang),
            "ambulance_phone": phone_or_none(block.get("ambulance_phone")),
        },
        "advice": rules,
    }
