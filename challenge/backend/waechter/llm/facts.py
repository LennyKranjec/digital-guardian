"""Faktenliste einer Patientin für die Kurzfassung (RAG nur auf Daten dieser Patientin).

Jede Zeile hat eine Fakt-ID (`ther-`, `visit-`, `resp-`, `obs-`, `alert-`, `assess-`, `ft-`), die
über `GET /patients/{id}/facts/{factId}` auflösbar ist, und einen kurzen deterministischen
Text (cs/en).
Zeitfenster: seit dem letzten vergangenen Termin plus alle offenen Meldungen. Notizen der Ärztin
und der Diagnosetext gehören nie dazu. **Freitexte der Patientin** (T-22, Vertrag v2.9) kommen nur
als Zitat in Fakten `ft-<id>` vor (höchstens `MAX_FREE_TEXTS`, Satzzeichen und Klammern ersetzt);
der Prüfer (genau ein Beleg, nur Wörter dieses Belegs) gilt auch für sie, der Prompt nennt sie
Daten, nie Anweisungen. Der Fakten-Hash ist der SHA-256 über Sprache, IDs und Texte.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from waechter.content import Content
from waechter.models import Assessment, FreeText, Patient, free_text_newest_first
from waechter.services.alerts import headline
from waechter.services.assessment_queries import assessment_view
from waechter.services.patient_views import (
    Reading,
    cycle_day_of,
    latest_past_visit,
    readings,
    regimen_of,
    since_last_visit_rows,
    symptom_label,
    upcoming_visit,
    visits_of,
    window_start,
)
from waechter.services.questionnaire import localize
from waechter.services.status import (
    LIGHT_ORDER,
    compute_status,
    current_therapy,
    last_value_response,
)
from waechter.timeutil import days_between, prague_date

_T: Final = {
    "therapy": {
        "cs": "Léčba: {regimen}; účinné látky: {drugs}; začátek cyklu {date}; den cyklu {day}.",
        "en": "Therapy: {regimen}; substances: {drugs}; cycle start {date}; cycle day {day}.",
        "de": "Therapie: {regimen}; Wirkstoffe: {drugs}; Zyklusbeginn {date}; Zyklustag {day}.",
    },
    "last_visit": {
        "cs": "Poslední návštěva: {date}.",
        "en": "Last visit: {date}.",
        "de": "Letzter Besuch: {date}.",
    },
    "next_visit": {
        "cs": "Příští plánovaná návštěva: {date}.",
        "en": "Next planned visit: {date}.",
        "de": "Nächster geplanter Besuch: {date}.",
    },
    "response": {
        "cs": "Poslední odpověď s hodnotami: {date}; dní bez odpovědi: {days}.",
        "en": "Last response with values: {date}; days without response: {days}.",
        "de": "Letzte Antwort mit Werten: {date}; Tage ohne Antwort: {days}.",
    },
    "first": {
        "cs": "{label} ({attribute}), první hodnota od poslední návštěvy: {value} dne {date}.",
        "en": "{label} ({attribute}), first value since the last visit: {value} on {date}.",
        "de": "{label} ({attribute}), erster Wert seit dem letzten Besuch: {value} am {date}.",
    },
    "latest": {
        "cs": "{label} ({attribute}), poslední hodnota: {value} dne {date}; vývoj: {direction}; "
        "dní bez hodnoty: {missing}.",
        "en": "{label} ({attribute}), latest value: {value} on {date}; trend: {direction}; "
        "days without value: {missing}.",
        "de": "{label} ({attribute}), letzter Wert: {value} am {date}; Verlauf: {direction}; "
        "Tage ohne Wert: {missing}.",
    },
    "highest": {
        "cs": "{label} ({attribute}), nejvyšší hodnota od poslední návštěvy: {value} dne {date}.",
        "en": "{label} ({attribute}), highest value since the last visit: {value} on {date}.",
        "de": "{label} ({attribute}), höchster Wert seit dem letzten Besuch: {value} am {date}.",
    },
    "alert_open": {
        "cs": "Otevřená výstraha ({level}), pravidlo {rule}: {headline}; vznik {date}.",
        "en": "Open alert ({level}), rule {rule}: {headline}; created {date}.",
        "de": "Offene Meldung ({level}), Regel {rule}: {headline}; entstanden {date}.",
    },
    "alert_persisting": {
        "cs": "Potvrzená výstraha, pravidlo {rule}: {headline}; vznik {date}; "
        "hodnota stále dosahuje prahu.",
        "en": "Acknowledged alert, rule {rule}: {headline}; created {date}; "
        "value still at or above the threshold.",
        "de": "Bestätigte Meldung, Regel {rule}: {headline}; entstanden {date}; "
        "Wert erreicht die Schwelle weiterhin.",
    },
    "assessment": {
        "cs": "Lékařské hodnocení {date}: {items}.",
        "en": "Clinician assessment {date}: {items}.",
        "de": "Ärztliche Bewertung {date}: {items}.",
    },
}
_LEVEL: Final = {
    "cs": {"red": "červená", "yellow": "žlutá", "grey": "šedá"},
    "en": {"red": "red", "yellow": "yellow", "grey": "grey"},
    "de": {"red": "rot", "yellow": "gelb", "grey": "grau"},
}
_DIRECTION: Final = {
    "cs": {"up": "rostoucí", "down": "klesající", "flat": "beze změny", "unknown": "neznámý"},
    "en": {"up": "rising", "down": "falling", "flat": "unchanged", "unknown": "unknown"},
    "de": {"up": "steigend", "down": "fallend", "flat": "unverändert", "unknown": "unbekannt"},
}
_GRADE: Final = {
    "cs": "{term} stupeň {grade}",
    "en": "{term} grade {grade}",
    "de": "{term} Grad {grade}",
}
MAX_ASSESSMENTS: Final = 2
MAX_FREE_TEXTS: Final = 5
#: Der Fakt enthält NIE den Text der Patientin (T-22F, A3 F-02): das Modell sieht nur Datum, Modus
#: und die zugeordneten Symptome; das Zitat zeigt ausschließlich die Oberfläche der Ärztin.
_FREE_TEXT: Final = {
    "cs": "Volný text pacientky {date} ({mode}){extra}.",
    "en": "Patient free text {date} ({mode}){extra}.",
    "de": "Freitext der Patientin {date} ({mode}){extra}.",
}
_FREE_MODE: Final = {
    "cs": {
        "template": "seznam slov",
        "fallback": "seznam slov, náhradní",
        "live": "jazykový model",
    },
    "en": {"template": "word list", "fallback": "word list, fallback", "live": "language model"},
    "de": {"template": "Wortliste", "fallback": "Wortliste, Rückfall", "live": "Sprachmodell"},
}
_FREE_EXTRA: Final = {
    "suggested": {
        "cs": "; návrh zařazení (nehodnoceno, nepotvrzeno): {labels}",
        "en": "; suggested mapping (not rated, unconfirmed): {labels}",
        "de": "; Zuordnungsvorschlag (nicht bewertet, unbestätigt): {labels}",
    },
}
_SENTENCE_END: Final = re.compile(r"[.!?]+(?:\s+|$)")


@dataclass(frozen=True)
class Fact:
    id: str
    kind: str
    text: str
    #: Rolle innerhalb der Art (Messwerte: first | latest | highest); nicht Teil des Fakten-Hashs
    role: str = ""


@dataclass(frozen=True)
class FactSet:
    facts: list[Fact]
    lang: str
    hash: str
    unknown_topics: list[str]

    def mapping(self) -> dict[str, str]:
        return {fact.id: fact.text for fact in self.facts}


_ATTRIBUTE_NAMES: Final[dict[str, dict[str, str]]] = {
    "severity": {"cs": "závažnost", "en": "severity", "de": "Schweregrad"},
    "frequency": {"cs": "četnost", "en": "frequency", "de": "Häufigkeit"},
    "interference": {
        "cs": "vliv na běžné činnosti",
        "en": "interference",
        "de": "Beeinträchtigung",
    },
    "presence": {"cs": "výskyt", "en": "presence", "de": "Auftreten"},
}


def _lang(lang: str) -> str:
    return lang if lang in ("cs", "en", "de") else "en"


def _day(moment: datetime) -> str:
    return prague_date(moment).isoformat()


def facts_hash(facts: list[Fact], lang: str) -> str:
    payload = json.dumps(
        {"lang": lang, "facts": [[f.id, f.text] for f in facts]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def inline_text(text: str) -> str:
    """Freitext als ein Satzstück: Klammern und Satzzeichen würden Belege/Sätze zerreißen."""
    flat = " ".join(text.replace("[", "(").replace("]", ")").split())
    return _SENTENCE_END.sub(" / ", flat).strip(" /")


def _free_text_facts(
    session: Session, content: Content, patient: Patient, start: datetime | None, lang: str
) -> list[Fact]:
    """Freitexte der Patientin als Fakten `ft-<id>` (T-22); `relevant` bei Vorschlag/Warnwort.

    Der Text der Patientin gehört NICHT in den Fakt (kein Zitat): so kann er nicht als scheinbar
    vom System stammender Satz der Kurzfassung belegt werden. Die Ärztin sieht ihn im Cockpit.
    """
    query = select(FreeText).where(FreeText.patient_id == patient.id)
    if start is not None:
        query = query.where(FreeText.created_at >= start)
    rows = session.scalars(query.order_by(*free_text_newest_first()).limit(MAX_FREE_TEXTS)).all()
    facts: list[Fact] = []
    for row in rows:
        labels = list(
            dict.fromkeys(
                symptom_label(content, s["symptom_key"], lang) for s in row.suggestions_json
            )
        )
        extra = ""
        if labels:
            extra += _FREE_EXTRA["suggested"][lang].format(labels=", ".join(labels))
        facts.append(
            Fact(
                f"ft-{row.id}",
                "free_text",
                _FREE_TEXT[lang].format(
                    date=_day(row.created_at),
                    mode=_FREE_MODE[lang].get(row.mapper_mode, row.mapper_mode),
                    extra=extra,
                ),
                role="relevant" if labels else "plain",
            )
        )
    return facts


def _pick(points: list[Reading]) -> tuple[Reading, Reading, Reading] | None:
    """Erster, letzter und höchster (frühester) Wert; `None` ohne Werte."""
    values = [p for p in points if p.value is not None]
    if not values:
        return None
    highest = max(values, key=lambda p: (p.value or 0, -p.t.timestamp()))
    return values[0], values[-1], highest


def build_facts(
    session: Session, clock: Clock, content: Content, patient: Patient, lang: str
) -> FactSet:
    lang = _lang(lang)
    now = clock.now()
    facts: list[Fact] = []
    unknown: list[str] = []
    therapy = current_therapy(session, patient.id)
    visits = visits_of(session, patient.id)
    data = readings(session, patient.id)

    if therapy is not None:
        regimen = regimen_of(content, therapy.regimen_id)
        drugs = ", ".join(d["name"] for d in regimen["drugs"]) if regimen else "?"
        facts.append(
            Fact(
                f"ther-{therapy.id}",
                "therapy",
                _T["therapy"][lang].format(
                    regimen=localize(regimen["label"], lang) if regimen else therapy.regimen_id,
                    drugs=drugs,
                    date=_day(therapy.cycle_start),
                    day=cycle_day_of(therapy, now) or "?",
                ),
            )
        )
    else:
        unknown.append("therapy")

    past, upcoming = latest_past_visit(visits, now), upcoming_visit(visits, now)
    if past is not None:
        facts.append(
            Fact(f"visit-{past.id}", "visit", _T["last_visit"][lang].format(date=_day(past.at)))
        )
    if upcoming is not None:
        facts.append(
            Fact(
                f"visit-{upcoming.id}",
                "visit",
                _T["next_visit"][lang].format(date=_day(upcoming.at)),
            )
        )
    if past is None and upcoming is None:
        unknown.append("visit")

    status = compute_status(session, clock, patient, content)
    last_values = last_value_response(session, patient.id)
    if last_values is not None:
        facts.append(
            Fact(
                f"resp-{last_values.id}",
                "response",
                _T["response"][lang].format(
                    date=_day(last_values.recorded_at),
                    days=days_between(last_values.recorded_at, now),
                ),
            )
        )
    else:
        unknown.append("response")

    open_alerts = sorted(
        status.open_alerts, key=lambda a: (-LIGHT_ORDER[a.level], a.created_at, a.id)
    )
    for alert in open_alerts:
        facts.append(
            Fact(
                f"alert-{alert.id}",
                "alert",
                _T["alert_open"][lang].format(
                    level=_LEVEL[lang][alert.level],
                    rule=alert.rule_id,
                    headline=headline(alert, content, lang),
                    date=_day(alert.created_at),
                ),
            )
        )
    for alert in status.persisting:
        facts.append(
            Fact(
                f"alert-{alert.id}",
                "alert",
                _T["alert_persisting"][lang].format(
                    rule=alert.rule_id,
                    headline=headline(alert, content, lang),
                    date=_day(alert.created_at),
                ),
            )
        )

    start = window_start(visits, therapy, data, now)
    rows = {
        (r["symptom_key"], r["attribute"]): r
        for r in since_last_visit_rows(session, clock, content, patient, lang)
    }
    seen: set[str] = set()
    for symptom_key, attribute in sorted(data):
        series = data[(symptom_key, attribute)]
        picked = _pick([p for p in series if start is None or p.t >= start])
        if picked is None:
            continue
        first, latest, highest = picked
        row: dict[str, Any] = rows.get((symptom_key, attribute), {})
        names = _ATTRIBUTE_NAMES.get(attribute, {})  # T-07H: Attribut in der Sprache des Fakts
        common = {
            "label": symptom_label(content, symptom_key, lang),
            "attribute": names.get(lang) or names.get("en") or attribute,
        }
        entries = [
            ("first", first, {}),
            (
                "latest",
                latest,
                {
                    "direction": _DIRECTION[lang][row.get("direction", "unknown")],
                    "missing": row.get("missing_days", 0),
                },
            ),
            ("highest", highest, {}),
        ]
        for kind, point, extra in entries:
            fact_id = f"obs-{point.answer_id}"
            # gleicher Messwert nur einmal; "letzter" hat Vorrang vor "erster"/"höchster"
            if kind != "latest" and (point is latest or fact_id in seen):
                continue
            if kind == "highest" and point is first:
                continue
            seen.add(fact_id)
            facts.append(
                Fact(
                    fact_id,
                    "observation",
                    _T[kind][lang].format(value=point.value, date=_day(point.t), **common, **extra),
                    role=kind,
                )
            )

    assessments = session.scalars(
        select(Assessment)
        .where(Assessment.patient_id == patient.id)
        .order_by(Assessment.assessed_at.desc(), Assessment.id)
    ).all()
    recent = [a for a in assessments if start is None or a.assessed_at >= start][:MAX_ASSESSMENTS]
    for assessment in recent:
        view = assessment_view(session, assessment, content)
        items = "; ".join(
            _GRADE[lang].format(term=i["term_en"], grade=i["grade"]) for i in view["items"]
        )
        facts.append(
            Fact(
                f"assess-{assessment.id}",
                "assessment",
                _T["assessment"][lang].format(date=_day(assessment.assessed_at), items=items),
            )
        )
    if not recent:
        unknown.append("assessment")

    facts.extend(_free_text_facts(session, content, patient, start, lang))
    return FactSet(facts=facts, lang=lang, hash=facts_hash(facts, lang), unknown_topics=unknown)
