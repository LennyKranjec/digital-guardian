"""Fragebogen: Kern-Items plus Regime-Profil plus Profil der Diagnosegruppe (Vertrag v1.9).

Reine Auswahl und Lokalisierung aus der geprüften Konfiguration; keine Bewertung und keine
Diagnose: der (synthetische) ICD-10-Code kommt aus den Stammdaten, das System leitet daraus nur die
Auswahl zusätzlicher Fragen ab. Die Auswahl dient auch der Validierung eingehender Antworten
(`responses.py`). Das Intervall (`due`) stammt aus `schedule.yaml`.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.services.access import not_found
from waechter.content import Content
from waechter.models import Answer, Patient, Response, Therapy
from waechter.timeutil import from_prague_local, iso_prague, prague_date, to_prague

SOURCE_CORE: Final = "core"
SOURCE_REGIMEN: Final = "regimen"
SOURCE_DIAGNOSIS: Final = "diagnosis"
NO_GROUP: Final = "none"

#: Obergrenze der Antwortwerte je Attribut (presence: nein/ja, sonst 0 bis 4)
PRESENCE_MAX: Final = 1
SCALE_MAX: Final = 4

_REASON: Final = {
    "cs": "Otázky odpovídající vaší léčbě: {label}",
    "en": "Questions matching your therapy: {label}",
    "de": "Fragen passend zu Ihrer Therapie: {label}",
}
# Mit Diagnosegruppe: bewusst ohne das Wort „Diagnose“ (Patiententexte, Verbotsliste COMMON §2).
_REASON_GROUP: Final = {
    "cs": "Otázky odpovídající vaší léčbě ({label}) a vašemu onemocnění ({group})",
    "en": "Questions matching your therapy ({label}) and your illness ({group})",
    "de": "Fragen passend zu Ihrer Therapie ({label}) und Ihrer Erkrankung ({group})",
}


@dataclass(frozen=True)
class Selection:
    questionnaire_id: str
    regimen: dict[str, Any]
    #: (Item, Quelle) in Anzeigereihenfolge: erst Kern, dann Regime-Profil, dann Diagnosegruppe
    items: list[tuple[dict[str, Any], str]]
    diagnosis_group: dict[str, Any] | None = None
    #: Bis v1.8 gültige ID `<items>:<regime>` bleibt für Antworten zulässig
    legacy_id: str = ""

    @property
    def accepted_ids(self) -> frozenset[str]:
        return frozenset({self.questionnaire_id, self.legacy_id})

    def allowed_pairs(self) -> set[tuple[str, str]]:
        return {
            (item["symptom_key"], a["attribute"])
            for item, _ in self.items
            for a in item["attributes"]
        }


def localize(text: dict[str, str], lang: str) -> str:
    """`lang`, sonst Englisch, sonst Tschechisch (cs/en sind Pflicht, de optional)."""
    return text.get(lang) or text.get("en") or text["cs"]


def max_value(attribute: str) -> int:
    return PRESENCE_MAX if attribute == "presence" else SCALE_MAX


def active_therapy(session: Session, patient_id: str) -> Therapy:
    therapy = session.scalars(
        select(Therapy)
        .where(Therapy.patient_id == patient_id)
        .order_by(Therapy.cycle_start.desc(), Therapy.id)
        .limit(1)
    ).first()
    if therapy is None:
        raise not_found()
    return therapy


def diagnosis_group_for(content: Content, code: str | None) -> dict[str, Any] | None:
    """Diagnosegruppe zum ICD-10-Code (Präfix an der Punktgrenze; der längste Präfix gewinnt)."""
    if not code or content.diagnoses is None:
        return None
    normalized = code.strip().upper()
    best: tuple[int, dict[str, Any]] | None = None
    for group in content.diagnoses["diagnoses"]:
        for prefix in group["icd10_prefixes"]:
            matches = (
                normalized == prefix
                or normalized.startswith(prefix + ".")
                or ("." in prefix and normalized.startswith(prefix))
            )
            if matches and (best is None or len(prefix) > best[0]):
                best = (len(prefix), group)
    return best[1] if best else None


def select_items(session: Session, patient_id: str, content: Content) -> Selection:
    therapy = active_therapy(session, patient_id)
    patient = session.get(Patient, patient_id)
    group = diagnosis_group_for(content, patient.diagnosis_code if patient else None)
    selection = select_for_regimen(content, therapy.regimen_id, group["id"] if group else None)
    if selection is None:
        raise not_found()
    return selection


def select_for_regimen(
    content: Content, regimen_id: str, diagnosis_group_id: str | None = None
) -> Selection | None:
    """Auswahl (Kern + Regime + Diagnosegruppe); `None`, wenn das Regime unbekannt ist.

    Eine unbekannte Gruppen-ID wirkt wie „keine Gruppe“ (alte Antworten bleiben auswertbar).
    """
    regimen = next((r for r in content.regimens["regimens"] if r["id"] == regimen_id), None)
    if regimen is None:
        return None
    group = None
    if diagnosis_group_id and content.diagnoses is not None:
        group = next(
            (g for g in content.diagnoses["diagnoses"] if g["id"] == diagnosis_group_id), None
        )
    by_key = {i["symptom_key"]: i for i in content.items["items"]}
    core = [(i, SOURCE_CORE) for i in content.items["items"] if i.get("core")]
    chosen = {i["symptom_key"] for i, _ in core}
    profile = [
        (by_key[key], SOURCE_REGIMEN)
        for key in regimen["symptom_keys"]
        if key in by_key and key not in chosen
    ]
    chosen |= {i["symptom_key"] for i, _ in profile}
    extra = [
        (by_key[key], SOURCE_DIAGNOSIS)
        for key in (group["symptom_keys"] if group else [])
        if key in by_key and key not in chosen
    ]
    legacy = f"{content.items['version']}:{regimen['id']}"
    return Selection(
        questionnaire_id=f"{legacy}:{group['id'] if group else NO_GROUP}",
        regimen=regimen,
        items=[*core, *profile, *extra],
        diagnosis_group=group,
        legacy_id=legacy,
    )


def option_labels(
    content: Content, attribute: str, symptom_key: str | None = None
) -> list[dict[str, Any]] | None:
    """Antwortbeschriftungen 0…n: `options` am Attribut des Items (T-23, z. B. grammatische Form im
    offiziellen PRO-CTCAE-Wortlaut), sonst die Standardbeschriftung `scale_labels` des Attributs."""
    for item in content.items["items"]:
        if item["symptom_key"] != symptom_key:
            continue
        for a in item["attributes"]:
            if a["attribute"] == attribute and a.get("options"):
                return list(a["options"])
    standard: list[dict[str, Any]] | None = content.items["scale_labels"].get(attribute)
    return standard


RECALL_INITIAL: Final = "initial_7d"
RECALL_DAILY: Final = "daily_24h"
WORDING_OFFICIAL: Final = "official"
WORDING_ADAPTED_RECALL: Final = "adapted_recall"
WORDING_OWN: Final = "own"


def recall_mode(session: Session, patient_id: str, now: datetime) -> str:
    """Rückblick der Fragen (DR-041): `initial_7d` (offizieller Wortlaut „7 Tage“) beim ersten
    Fragebogen nach Therapiebeginn oder Regimewechsel (anderes `regimen_id`), danach `daily_24h`.
    Ein neuer Zyklus desselben Regimes setzt nicht zurück; Therapien nach `now` zählen nicht."""
    started = session.scalars(
        select(Therapy)
        .where(Therapy.patient_id == patient_id, Therapy.cycle_start <= now)
        .order_by(Therapy.cycle_start.desc(), Therapy.id)
    ).all()
    if not started:
        return RECALL_INITIAL
    run_start = started[0].cycle_start  # Beginn des letzten Laufs desselben Regimes
    for earlier in started[1:]:
        if earlier.regimen_id != started[0].regimen_id:
            break
        run_start = earlier.cycle_start
    answered = session.scalar(
        select(Response.id)
        .join(Answer, Answer.response_id == Response.id)
        .where(
            Response.patient_id == patient_id,
            Response.recorded_at >= run_start,
            Answer.value.is_not(None),
        )
        .limit(1)
    )
    return RECALL_DAILY if answered is not None else RECALL_INITIAL


def question_text(attribute: dict[str, Any], lang: str, mode: str) -> str:
    """Fragetext des Attributs im Rückblick `mode`; eigene Items haben nur `question`."""
    daily = attribute.get("question_daily")
    source = daily if mode == RECALL_DAILY and daily else attribute["question"]
    return localize(source, lang)


def wording_of(attribute: dict[str, Any], mode: str) -> str:
    """Herkunft des Wortlauts: official | adapted_recall (nur die Zeitangabe ersetzt) | own."""
    if attribute.get("wording") != "official_wording":
        return WORDING_OWN
    if mode == RECALL_DAILY and attribute.get("question_daily"):
        return WORDING_ADAPTED_RECALL
    return WORDING_OFFICIAL


def wording_for(content: Content, symptom_key: str, attribute: str, mode: str) -> str | None:
    """`wording_of` für ein (Symptom, Attribut) aus items.yaml; `None`, wenn das Paar fehlt."""
    for item in content.items["items"]:
        if item["symptom_key"] == symptom_key:
            for a in item["attributes"]:
                if a["attribute"] == attribute:
                    return wording_of(a, mode)
    return None


def recall_period_text(content: Content, lang: str, mode: str) -> str:
    key = "recall_period_daily" if mode == RECALL_DAILY else "recall_period"
    recall = content.items.get(key) or content.items.get("recall_period")
    return localize(recall, lang) if recall else ""


def options_for(
    content: Content, attribute: str, lang: str, symptom_key: str | None = None
) -> list[dict[str, Any]]:
    labels = option_labels(content, attribute, symptom_key)
    if labels is None:
        return [{"value": v, "label": str(v)} for v in range(max_value(attribute) + 1)]
    return [{"value": v, "label": localize(label, lang)} for v, label in enumerate(labels)]


def reason_for(selection: Selection, lang: str) -> str:
    """Begründungszeile „Fragen passend zu Ihrer Therapie (und Erkrankung)“, lokalisiert."""
    regimen_label = localize(selection.regimen["label"], lang)
    group = selection.diagnosis_group
    if group is None:
        return _REASON.get(lang, _REASON["en"]).format(label=regimen_label)
    return _REASON_GROUP.get(lang, _REASON_GROUP["en"]).format(
        label=regimen_label, group=localize(group["label"], lang)
    )


@dataclass(frozen=True)
class Due:
    next_due_at: datetime
    overdue: bool
    interval_days: int


def interval_for(schedule: dict[str, Any], cycle_day: int) -> int:
    """Intervall der Phase, in die `cycle_day` fällt; sonst das Standardintervall."""
    for phase in schedule["phases"]:
        if phase["from_cycle_day"] <= cycle_day <= phase["to_cycle_day"]:
            return int(phase["interval_days"])
    return int(schedule["default_interval_days"])


def due_for(session: Session, patient_id: str, content: Content, now: datetime) -> Due | None:
    """Nächster Termin: letzte Antwort mit mindestens einem Wert + Intervall (Prager Kalendertage).

    Fällig ab Beginn dieses Kalendertags (Prag). Ohne Antwort gilt der Zyklusbeginn. Das Intervall
    richtet sich nach dem Zyklustag des Bezugszeitpunkts (letzte Antwort bzw. Zyklusbeginn).
    """
    if content.schedule is None:
        return None
    therapy = active_therapy(session, patient_id)
    last = session.scalar(
        select(Response.recorded_at)
        .join(Answer, Answer.response_id == Response.id)
        .where(Response.patient_id == patient_id, Answer.value.is_not(None))
        .order_by(Response.recorded_at.desc())
        .limit(1)
    )
    if last is None:
        interval = interval_for(content.schedule, 1)
        return Due(therapy.cycle_start, now >= therapy.cycle_start, interval)
    cycle_day = (prague_date(last) - prague_date(therapy.cycle_start)).days + 1
    interval = interval_for(content.schedule, cycle_day)
    day_start = to_prague(last).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    next_due = from_prague_local(day_start + timedelta(days=interval))
    return Due(next_due, now >= next_due, interval)


def build_questionnaire(
    session: Session, patient: Patient, content: Content, lang: str | None, clock: Clock
) -> dict[str, Any]:
    chosen_lang = lang or patient.language
    selection = select_items(session, patient.id, content)
    mode = recall_mode(session, patient.id, clock.now())
    group = selection.diagnosis_group
    reason = reason_for(selection, chosen_lang)
    body: dict[str, Any] = {
        "questionnaire_id": selection.questionnaire_id,
        "items_version": content.items["version"],
        "regimen_id": selection.regimen["id"],
        "diagnosis_group": group["id"] if group else None,
        "lang": chosen_lang,
        "recall_period": recall_period_text(content, chosen_lang, mode),
        "recall": mode,
        "selection_reason": reason,
        "items": [
            {
                "symptom_key": item["symptom_key"],
                "label": localize(item["label"], chosen_lang),
                "source": source,
                "questions": [
                    {
                        "attribute": a["attribute"],
                        "text": question_text(a, chosen_lang, mode),
                        "options": options_for(
                            content, a["attribute"], chosen_lang, item["symptom_key"]
                        ),
                    }
                    for a in item["attributes"]
                ],
            }
            for item, source in selection.items
        ],
    }
    due = due_for(session, patient.id, content, clock.now())
    if due is not None:
        body["due"] = {
            "next_due_at": iso_prague(due.next_due_at),
            "overdue": due.overdue,
            "interval_days": due.interval_days,
        }
    if content.advice is not None:
        body["escalation_general"] = localize(content.advice["escalation"]["general"], chosen_lang)
    return body
