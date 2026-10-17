"""Triage-Dienst (Vertrag `triage.md` §5): Entscheidung je Antwort, Meldungen, Befundkarte.

Jede gespeicherte Antwort (Web-Sitzung, `/me/responses`, später Telefon/Papier) bekommt eine
Entscheidung `wa_triage_decisions`: reine Funktion der gespeicherten Antworten, des Vorberichts und
der Wissensbasis (keine Uhr, kein Zufall, kein LLM; `created_at` = Zeitpunkt der Antwort).

Meldungen: RED ⇒ `R-TRI-RED` (rot, Sofortbenachrichtigung), YELLOW ⇒ `R-TRI-YEL`, je Antwort
höchstens eine. **Rauschbremse:** besteht für dieselbe Antwort schon eine Meldung der
Bestandsregeln mit mindestens gleicher Stufe, entsteht keine zusätzliche; die Entscheidung hängt
dann an dieser Meldung (`explanation.triage`). Zusätzlich keine zweite offene Meldung derselben
Regel und keine neue innerhalb der Ruhezeit nach der Quittierung, solange keine grüne
Entscheidung dazwischenliegt.
Seed-Antworten bekommen Entscheidungen, aber keine Meldungen (Bestandsorakel bleiben gültig).

Fehlt `triage.yaml` (z. B. Fixture-Inhalte), ist die Triage aus und alles andere unverändert.
"""

import logging
import os
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.services.access import not_found
from app.services.audit import Actor, record_audit
from app.services.auth import Principal
from waechter.content import Content, content_dir, get_content
from waechter.models import Alert, Answer, Patient, Response, TriageDecision
from waechter.services import advice as advice_service
from waechter.services import alerts
from waechter.services.config import active_body
from waechter.services.questionnaire import active_therapy, diagnosis_group_for, localize
from waechter.timeutil import iso_prague, prague_date
from waechter.triage.counterfactual import Counterfactual, counterfactuals
from waechter.triage.engine import INCOMPLETE_SAFETY_ITEMS, Level
from waechter.triage.kb import KnowledgeBase, ResolvedProfile, build_kb, read_triage_yaml
from waechter.triage.policy import FlipPolicy
from waechter.triage.runtime import ProfileRuntime, runtime_for

logger = logging.getLogger("waechter.triage")

#: Seed-Läufe setzen dieses Flag in `session.info`: Entscheidungen ja, Meldungen nein
SEED_FLAG: Final = "waechter_seeding"
#: Seed: nur die jüngste Antwort je Patientin bekommt Kontrafaktische und Tipp-Regeln (Startzeit)
SEED_LAST: Final = "waechter_seeding_last_response"
RULE_RED: Final = "R-TRI-RED"
RULE_YELLOW: Final = "R-TRI-YEL"
_ALERT_LEVEL: Final = {"RED": "red", "YELLOW": "yellow"}
_RULE_OF: Final = {"red": RULE_RED, "yellow": RULE_YELLOW}
_RANK: Final = {"yellow": 1, "red": 2}
_STATUS: Final = "placeholder"
_RATIONALE: Final = {
    "red": {
        "cs": "Rozhodovací strom (zástupná pravidla, klinicky neschváleno): úroveň červená.",
        "en": "Decision tree (placeholder rules, not clinically approved): red level.",
        "de": "Entscheidungsbaum (Platzhalter-Regeln, nicht klinisch freigegeben): Stufe Rot.",
    },
    "yellow": {
        "cs": "Rozhodovací strom (zástupná pravidla, klinicky neschváleno): úroveň žlutá.",
        "en": "Decision tree (placeholder rules, not clinically approved): yellow level.",
        "de": "Entscheidungsbaum (Platzhalter-Regeln, nicht klinisch freigegeben): Stufe Gelb.",
    },
}
_CF_TEXT: Final = {
    ("lower", "cs"): "{label} (stupeň) klesl na ≤ {to}",
    ("lower", "en"): "{label} (grade) dropped to ≤ {to}",
    ("lower", "de"): "{label} (Grad) auf ≤ {to} sänke",
    ("raise", "cs"): "{label} (stupeň) vzrostl na ≥ {to}",
    ("raise", "en"): "{label} (grade) rose to ≥ {to}",
    ("raise", "de"): "{label} (Grad) auf ≥ {to} stiege",
}
_CF_JOIN: Final = {"cs": " a ", "en": " and ", "de": " und "}
_SHIELD_TEXT: Final = {
    "cs": "Pevná spodní hranice {floor} brání snížení",
    "en": "Floor {floor} prevents lowering",
    "de": "Boden {floor} verhindert Senkung",
}
_INCOMPLETE_TEXT: Final = {
    "cs": "Chybí odpověď na bezpečnostní otázku, nejméně žlutá",
    "en": "A safety question is unanswered, at least yellow",
    "de": "Eine Sicherheitsfrage ist unbeantwortet, mindestens Gelb",
}
_LEAF_TEXT: Final = {
    "cs": "List stromu {target} {leaf}",
    "en": "Tree leaf {target} {leaf}",
    "de": "Baumblatt {target} {leaf}",
}

_KB_CACHE: dict[Path, tuple[tuple[int, int, int], KnowledgeBase]] = {}


def get_kb(content: Content | None = None) -> KnowledgeBase | None:
    """Geprüfte Wissensbasis des Inhaltsordners; `None`, wenn `triage.yaml` fehlt (Triage aus)."""
    directory = content_dir()
    path = directory / "triage.yaml"
    if not path.is_file():
        return None
    content = content or get_content()
    if content is None:
        return None
    stat = path.stat()
    fingerprint = (stat.st_mtime_ns, stat.st_size, id(content))
    key = directory.resolve()
    cached = _KB_CACHE.get(key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    attributes = {
        item["symptom_key"]: [a["attribute"] for a in item["attributes"]]
        for item in content.items["items"]
    }
    regimens = {r["id"]: list(r["symptom_keys"]) for r in content.regimens["regimens"]}
    kb = build_kb(read_triage_yaml(directory), attributes=attributes, regimens=regimens)
    _KB_CACHE[key] = (fingerprint, kb)
    return kb


_WARMUP_STARTED = False
WARMUP_ENV: Final = "WAECHTER_TRIAGE_WARMUP"


def compile_all() -> int | None:
    """Kompiliert und verifiziert alle Profile (Cache); Anzahl, `None` ohne Wissensbasis."""
    kb = get_kb()
    if kb is None:
        return None
    for profile_id in kb.profiles:
        runtime_for(kb, profile_id)
    return len(kb.profiles)


def _warm() -> None:
    """Kompiliert und verifiziert alle Profile im Hintergrund (Cache für die ersten Anfragen)."""
    try:
        count = compile_all()
        kb = get_kb()
        if kb is not None:
            for composition_id in kb.compositions:
                if "+" not in composition_id:  # T-24: Klassenmodul-Profile mit vorwärmen
                    runtime_for(kb, composition_id)
        if count is not None:
            logger.info("triage warm-up finished (%d profiles)", count)
    except Exception as error:  # Anfragen melden den Fehler selbst (kein stiller Rückfall)
        logger.error("triage warm-up failed (%s)", type(error).__name__)


def start_warmup() -> bool:
    """Startet das Vorwärmen einmal je Prozess; `WAECHTER_TRIAGE_WARMUP=0` schaltet es ab."""
    global _WARMUP_STARTED
    if _WARMUP_STARTED or os.environ.get(WARMUP_ENV) == "0":
        return False
    _WARMUP_STARTED = True
    threading.Thread(target=_warm, name="triage-warmup", daemon=True).start()
    return True


def profile_id_for(kb: KnowledgeBase, session: Session, patient_id: str) -> str | None:
    """Triage-Profil der aktuellen Therapie (Blattprofil des Regimes) oder `None`.

    T-24: Hat die Diagnosegruppe der Patientin ein Diagnosemodul, gilt die Variante
    `<Profil>+<Modul>`; so stellt auch die adaptive Sitzung die Diagnose-Zusatzfragen.
    """
    base = kb.regimen_profile.get(active_therapy(session, patient_id).regimen_id)
    if base is None:
        return None
    patient = session.get(Patient, patient_id)
    content = get_content()
    code = patient.diagnosis_code if patient else None
    group = diagnosis_group_for(content, code) if content is not None else None
    return kb.variant_for(base, group["id"] if group else None)


def cycle_week(session: Session, patient_id: str, at: datetime) -> int:
    """Zykluswoche (0-basiert) des Zeitpunkts nach Prager Kalendertagen (Round-Robin der Slots)."""
    therapy = active_therapy(session, patient_id)
    day = (prague_date(at) - prague_date(therapy.cycle_start)).days + 1
    return max(day - 1, 0) // 7


def state_of(answers: Sequence[Answer]) -> dict[tuple[str, str], int]:
    """Beantwortete Felder (`null` = übersprungen bleibt fehlend)."""
    return {(a.symptom_key, a.attribute): a.value for a in answers if a.value is not None}


def previous_grades(
    session: Session, response: Response, profile: ResolvedProfile
) -> dict[str, int] | None:
    """Symptomgrade des letzten früheren Berichts derselben Patientin; erster Bericht ⇒ `None`."""
    earlier = session.scalar(
        select(Response)
        .where(
            Response.patient_id == response.patient_id,
            Response.id != response.id,
            Response.source
            != FOLLOWUP_SOURCE,  # Folgefragen sind Teilantworten, nie Vergleichsstand
            (Response.recorded_at < response.recorded_at)
            | ((Response.recorded_at == response.recorded_at) & (Response.id < response.id)),
        )
        .order_by(Response.recorded_at.desc(), Response.id.desc())
        .limit(1)
    )
    if earlier is None:
        return None
    answers = session.scalars(select(Answer).where(Answer.response_id == earlier.id)).all()
    return profile.grades(state_of(answers))


# ---- Entscheidung -------------------------------------------------------------------------
def _counterfactual_json(entry: Counterfactual) -> dict[str, Any]:
    return {
        "direction": entry.direction,
        "kind": entry.api_kind,
        "changes": [
            {"symptom_key": c.symptom_key, "from": c.from_grade, "to": c.to_grade}
            for c in entry.changes
        ],
        "to_level": entry.to_level.name if entry.to_level is not None else None,
        "floor_id": entry.floor_id,
    }


def _reasons(
    runtime: ProfileRuntime, result: Any, grades: Mapping[str, int]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"kind": "shield", "code": hit.floor_id, "items": list(hit.items)}
        for hit in result.shield_hits
    ]
    tree_level = result.components[0].level if result.components else Level.GREEN
    leaves = result.leaves[0] if result.leaves else None
    if leaves is not None and tree_level >= Level.YELLOW:
        target = "red" if tree_level is Level.RED else "yellow"
        leaf_id = leaves.red if tree_level is Level.RED else leaves.yellow
        rendered = next(
            (r for r in runtime.rules if r.leaf_id == leaf_id and r.level == target.upper()), None
        )
        out.append(
            {
                "kind": "path",
                "code": leaf_id,
                "target": target,
                "items": [
                    s for s, g in sorted(grades.items(), key=lambda p: (-p[1], p[0])) if g >= 1
                ],
                "text": dict(rendered.text) if rendered else {},
                "rules": list(rendered.teacher_rule_ids) if rendered else [],
            }
        )
    if result.incomplete:
        out.append({"kind": "incomplete", "code": INCOMPLETE_SAFETY_ITEMS})
    if leaves is not None:
        out.append({"kind": "leaf", "code": leaves.yellow, "target": "yellow"})
        out.append({"kind": "leaf", "code": leaves.red, "target": "red"})
    return out


FOLLOWUP_SOURCE = "free_text_followup"
FOLLOWUP_BASE_DAYS = 7


def _followup_base(session: Session, response: Response) -> Response | None:
    """Jüngster Check-in (nicht Folgefrage) der Patientin in den Tagen davor, sonst `None`."""
    return session.scalars(
        select(Response)
        .where(
            Response.patient_id == response.patient_id,
            Response.source != FOLLOWUP_SOURCE,
            Response.recorded_at <= response.recorded_at,
            Response.recorded_at >= response.recorded_at - timedelta(days=FOLLOWUP_BASE_DAYS),
        )
        .order_by(Response.recorded_at.desc(), Response.id)
        .limit(1)
    ).first()


def decide(
    session: Session,
    response: Response,
    content: Content,
    kb: KnowledgeBase,
    *,
    create_alerts: bool = True,
) -> TriageDecision | None:
    """Entscheidung zu einer gespeicherten Antwort (idempotent); `None`, wenn kein Profil passt."""
    existing = session.scalar(
        select(TriageDecision).where(TriageDecision.response_id == response.id)
    )
    if existing is not None:
        return existing
    patient = session.get(Patient, response.patient_id)
    if patient is None:
        return None
    profile_id = profile_id_for(kb, session, patient.id)
    if profile_id is None:
        return None
    runtime = runtime_for(kb, profile_id)
    profile = runtime.composition.components[0]
    answers = session.scalars(select(Answer).where(Answer.response_id == response.id)).all()
    state = state_of(answers)
    anchor = response
    if response.source == FOLLOWUP_SOURCE:
        # Folgefrage zu einem Freitext: die Antwort ergänzt den letzten Check-in (T-22), statt
        # allein als unvollständige Antwort zu gelten; nur Felder des Profils zählen
        base = _followup_base(session, response)
        if base is not None:
            anchor = base
            merged = state_of(
                session.scalars(select(Answer).where(Answer.response_id == base.id)).all()
            )
            merged.update(state)
            state = merged
        known = set(profile.symptoms)
        state = {pair: value for pair, value in state.items() if pair[0] in known}
    previous = previous_grades(session, anchor, profile)
    engine = runtime.engine
    result = engine.level(state, previous)
    grades = engine.grades(state)
    bounds = FlipPolicy(engine).bounds(
        state, previous, cycle_week(session, patient.id, response.recorded_at)
    )
    light = bool(session.info.get(SEED_FLAG)) and response.id != session.info.get(SEED_LAST)
    cfs = (
        [] if light else counterfactuals(engine, grades, previous, missing_safety=result.incomplete)
    )
    recommendations = (
        [] if light else advice_service.evaluate_with_escalation(session, response, content)[0]
    )
    leaves = result.leaves[0] if result.leaves else None
    row = TriageDecision(
        response_id=response.id,
        patient_id=patient.id,
        profile_id=profile_id,
        level=result.level.name,
        level_lo=bounds.lo.name,
        level_hi=max(bounds.hi, result.level).name,
        incomplete=result.incomplete,
        reason_codes_json=_reasons(runtime, result, grades),
        rule_version=kb.hash,
        tree_version=runtime.tree_version,
        leaf_ids_json={"yellow": leaves.yellow, "red": leaves.red} if leaves else {},
        shield_hits_json=[
            {"floor_id": h.floor_id, "min_level": h.min_level.name, "items": list(h.items)}
            for h in result.shield_hits
        ],
        counterfactuals_json=[_counterfactual_json(c) for c in cfs],
        recommendations_json=[
            {
                "rule_id": r.rule_id,
                "symptom_key": r.symptom_key,
                "outcome": r.status,
                "value": r.value,
            }
            for r in recommendations
        ],
        asked_questions=len(state) if response.source == FOLLOWUP_SOURCE else len(answers),
        full_questions=profile.full_question_count,
        composition_hash=runtime.composition.composition_hash,
        composition_status=runtime.composition.composition_status,
        component_ids_json=[c.id for c in runtime.composition.components],
        coverage_gap=runtime.composition.coverage_gap,
        created_at=response.recorded_at,
        synthetic=True,
    )
    session.add(row)
    session.flush()
    if create_alerts:
        _raise_alert(session, response, patient, row, content, kb)
    return row


def _lock_patient(session: Session, patient_id: str) -> None:
    session.execute(
        update(Patient).where(Patient.id == patient_id).values(synthetic=Patient.synthetic)
    )


def decide_safely(session: Session, clock: Clock, actor: Actor, response_id: str) -> bool:
    """Eigene Transaktion nach den Regeln; ein Fehler gefährdet weder Antwort noch Regeln."""
    content = get_content()
    if content is None:
        return False
    try:
        kb = get_kb(content)
        if kb is None:
            return False
        response = session.get(Response, response_id)
        if response is None:
            return False
        _lock_patient(session, response.patient_id)
        decide(session, response, content, kb, create_alerts=not session.info.get(SEED_FLAG))
        session.commit()
    except Exception as error:
        session.rollback()
        alerts.discard_pending_notices(session)
        logger.error("triage decision failed (%s)", type(error).__name__)
        _record_failure(session, clock, actor, response_id, type(error).__name__)
        return False
    alerts.dispatch_pending_notices(session)
    return True


def _record_failure(
    session: Session, clock: Clock, actor: Actor, response_id: str, error_type: str
) -> None:
    try:
        response = session.get(Response, response_id)
        record_audit(
            session,
            clock,
            actor,
            "triage_failed",
            "response",
            target_id=response_id,
            subject_id=response.patient_id if response is not None else None,
            details={"error": error_type},
        )
        session.commit()
    except Exception as error:
        session.rollback()
        logger.error("marking failed triage failed (%s)", type(error).__name__)


# ---- Meldungen R-TRI-RED / R-TRI-YEL ------------------------------------------------------
_REASON_LANGS: Final = ("cs", "en", "de")


def _reason_i18n(
    kb: KnowledgeBase, row: TriageDecision, entry: Mapping[str, Any]
) -> dict[str, Any]:
    """Begründung an der Meldung wie `TriageDecision.reason_codes[]`, Text je Sprache (T-16G)."""
    views = {lang: _reason_view(kb, row, entry, lang) for lang in _REASON_LANGS}
    first = views["en"]
    stored: dict[str, Any] = {
        "code": first["code"],
        "kind": first["kind"],
        "text_i18n": {lang: view["text"] for lang, view in views.items()},
    }
    if first.get("items"):
        stored["items"] = list(first["items"])
    return stored


def _summary(kb: KnowledgeBase, row: TriageDecision) -> dict[str, Any]:
    return {
        "level": row.level,
        "level_lo": row.level_lo,
        "level_hi": row.level_hi,
        "incomplete": row.incomplete,
        "response_id": row.response_id,
        "profile_id": row.profile_id,
        "tree_version": row.tree_version,
        "rule_version": row.rule_version,
        "reason_codes": [_reason_i18n(kb, row, r) for r in row.reason_codes_json],
    }


def _attach(alert: Alert, row: TriageDecision, kb: KnowledgeBase) -> None:
    alert.explanation_json = {**alert.explanation_json, "triage": _summary(kb, row)}


def _green_since(session: Session, patient_id: str, after: datetime) -> bool:
    return (
        session.scalar(
            select(TriageDecision.id).where(
                TriageDecision.patient_id == patient_id,
                TriageDecision.level == Level.GREEN.name,
                TriageDecision.created_at > after,
            )
        )
        is not None
    )


def _raise_alert(
    session: Session,
    response: Response,
    patient: Patient,
    row: TriageDecision,
    content: Content,
    kb: KnowledgeBase,
) -> Alert | None:
    level = _ALERT_LEVEL.get(row.level)
    if level is None:
        return None
    own = session.scalars(select(Alert).where(Alert.response_id == response.id)).all()
    covering = [
        a
        for a in own
        if not a.rule_id.startswith("R-TRI") and _RANK.get(a.level, 0) >= _RANK[level]
    ]
    if not covering:  # T-16G F-03: auch eine offene Meldung einer früheren Antwort deckt ab
        covering = [
            a
            for a in session.scalars(
                select(Alert)
                .where(Alert.patient_id == patient.id, Alert.status == alerts.STATUS_OPEN)
                .order_by(Alert.created_at.desc(), Alert.id)
            )
            if _RANK.get(a.level, 0) >= _RANK[level]
        ]
    if covering:  # Rauschbremse: Meldung gleicher/höherer Stufe trägt die Entscheidung (G-02:
        _attach(covering[0], row, kb)  # eine höhere Stufe bricht immer durch)
        return None
    rules = active_body(session, "rules") or content.rules
    noise = rules["noise"]
    rule_id = _RULE_OF[level]
    for earlier in session.scalars(
        select(Alert).where(Alert.patient_id == patient.id, Alert.rule_id == rule_id)
    ):
        if earlier.status == alerts.STATUS_OPEN:
            _attach(earlier, row, kb)
            return None
        quiet_until = alerts._acknowledged_at(session, earlier) + timedelta(
            hours=noise["cooldown_hours"]
        )
        if response.recorded_at < quiet_until and not _green_since(
            session, patient.id, earlier.created_at
        ):
            return None
    alert = Alert(
        patient_id=patient.id,
        response_id=response.id,
        rule_id=rule_id,
        rule_version=kb.version,
        level=level,
        symptom_key="",
        attribute=None,
        status=alerts.STATUS_OPEN,
        explanation_json={
            "kind": "triage",  # A0-Entscheid (v2.8): keine falsche Schwellen-Erklärung
            "params": {},
            "observed": {},
            "baseline_window": None,
            "cycle_day": alerts._cycle_day(session, response),
            "evidence": [alerts._fact("resp", response.id)],
            "rationale_i18n": _RATIONALE[level],
            "source_id": None,
            "triage": _summary(kb, row),
        },
        notified=level in noise["notify_levels"],
        version=1,
        created_at=response.recorded_at,
        synthetic=True,
    )
    session.add(alert)
    session.flush()
    if alert.notified:
        alerts._notify(session, patient, alert, content)
    return alert


# ---- Lesen: Befundkarte, Übersicht, Regelkarte --------------------------------------------
def _labels(content: Content, lang: str) -> dict[str, str]:
    return {i["symptom_key"]: localize(i["label"], lang) for i in content.items["items"]}


def _floor_text(kb: KnowledgeBase, profile_id: str, floor_id: str, lang: str) -> str:
    profile = kb.find(profile_id)
    if profile is not None:
        for floor in profile.floors:
            if floor.id == floor_id and floor.text:
                return f"{floor_id}: {floor.text.get(lang) or floor.text.get('en') or floor_id}"
    return floor_id


def _reason_view(
    kb: KnowledgeBase, row: TriageDecision, entry: Mapping[str, Any], lang: str
) -> dict[str, Any]:
    kind = entry["kind"]
    code = entry["code"]
    if kind == "shield":
        text = _floor_text(kb, row.profile_id, code, lang)
    elif kind == "path":
        stored: Mapping[str, str] = entry.get("text") or {}
        text = stored.get(lang) or stored.get("en") or code
    elif kind == "incomplete":
        text = _INCOMPLETE_TEXT.get(lang, _INCOMPLETE_TEXT["en"])
    else:
        text = _LEAF_TEXT.get(lang, _LEAF_TEXT["en"]).format(
            target=entry.get("target", ""), leaf=code
        )
    view: dict[str, Any] = {"code": code, "text": text, "kind": kind}
    if entry.get("items"):
        view["items"] = list(entry["items"])
    return view


def _counterfactual_view(
    kb: KnowledgeBase,
    row: TriageDecision,
    entry: Mapping[str, Any],
    labels: Mapping[str, str],
    lang: str,
) -> dict[str, Any]:
    if entry["kind"] == "shield":
        text = _SHIELD_TEXT.get(lang, _SHIELD_TEXT["en"]).format(floor=entry["floor_id"])
        return {"kind": "shield", "direction": entry["direction"], "text": text, "changes": []}
    template = _CF_TEXT.get((entry["direction"], lang)) or _CF_TEXT[(entry["direction"], "en")]
    parts = [
        template.format(label=labels.get(c["symptom_key"], c["symptom_key"]), to=c["to"])
        for c in entry["changes"]
    ]
    return {
        "kind": "change",
        "direction": entry["direction"],
        "text": _CF_JOIN.get(lang, _CF_JOIN["en"]).join(parts),
        "changes": [dict(c) for c in entry["changes"]],
        "to_level": entry.get("to_level"),
    }


def decision_view(
    kb: KnowledgeBase, content: Content, row: TriageDecision, lang: str
) -> dict[str, Any]:
    """`TriageDecision` im Vertragsformat (Texte lokalisiert, Struktur aus der Zeile)."""
    labels = _labels(content, lang)
    return {
        "response_id": row.response_id,
        "decided_at": iso_prague(row.created_at),
        "level": row.level,
        "level_lo": row.level_lo,
        "level_hi": row.level_hi,
        "incomplete": row.incomplete,
        "profile_id": row.profile_id,
        "rule_version": row.rule_version,
        "tree_version": row.tree_version,
        "leaf_ids": dict(row.leaf_ids_json),
        "reason_codes": [_reason_view(kb, row, e, lang) for e in row.reason_codes_json],
        "counterfactuals": [
            _counterfactual_view(kb, row, e, labels, lang) for e in row.counterfactuals_json
        ],
        "recommendations": [dict(r) for r in row.recommendations_json],
        "asked_questions": row.asked_questions,
        "full_questions": row.full_questions,
        "composition_hash": row.composition_hash,
        "composition_status": row.composition_status,
        "status": _STATUS,
    }


def latest_row(
    session: Session, patient_id: str, response_id: str | None = None
) -> TriageDecision | None:
    query = select(TriageDecision).where(TriageDecision.patient_id == patient_id)
    if response_id is not None:
        query = query.where(TriageDecision.response_id == response_id)
    return session.scalars(
        query.order_by(TriageDecision.created_at.desc(), TriageDecision.id).limit(1)
    ).first()


def latest_summary(session: Session, patient_id: str) -> dict[str, Any] | None:
    """Kurzform der jüngsten Entscheidung für die Patientenübersicht (`triage_latest`)."""
    row = latest_row(session, patient_id)
    if row is None:
        return None
    return {
        "response_id": row.response_id,
        "decided_at": iso_prague(row.created_at),
        "level": row.level,
        "level_lo": row.level_lo,
        "level_hi": row.level_hi,
        "incomplete": row.incomplete,
        "profile_id": row.profile_id,
        "status": _STATUS,
    }


def decision_for_patient(
    session: Session,
    clock: Clock,
    principal: Principal,
    content: Content,
    patient_id: str,
    response_id: str | None,
    lang: str,
) -> dict[str, Any]:
    """`GET /patients/{id}/triage`: letzte oder gewählte Entscheidung; sonst 404."""
    kb = get_kb(content)
    if kb is None or session.get(Patient, patient_id) is None:
        raise not_found()
    row = latest_row(session, patient_id, response_id)
    if row is None:
        raise not_found()
    record_audit(
        session,
        clock,
        principal.actor,
        "view_triage",
        "response",
        target_id=row.response_id,
        subject_id=patient_id,
    )
    session.commit()
    return decision_view(kb, content, row, lang)


def rule_card(content: Content, lang: str) -> dict[str, Any]:
    """`GET /config/triage`: Regelkarte je Profil (kompiliert, verifiziert, Hashes, Platzhalter)."""
    kb = get_kb(content)
    if kb is None:
        raise not_found()
    profiles: list[dict[str, Any]] = []
    shown = {
        **kb.profiles,
        **{k: v for k, v in kb.compositions.items() if "+" not in k},  # T-24 Klassenmodule
    }
    for profile_id, profile in shown.items():
        runtime = runtime_for(kb, profile_id)
        report = runtime.report.to_dict()
        compiled = runtime.compiled[0]
        profiles.append(
            {
                "profile_id": profile_id,
                "regimen_ids": list(profile.regimen_ids),
                "tree_version": runtime.tree_version,
                "composition_hash": runtime.composition.composition_hash,
                "trees": {
                    "yellow": {"leaves": compiled.yellow.leaves, "depth": compiled.yellow.depth},
                    "red": {"leaves": compiled.red.leaves, "depth": compiled.red.depth},
                },
                "verification": {
                    k: report[k]
                    for k in ("points", "under", "over", "monotone_violations", "scope")
                },
                "components": report["components"],
                "rules": [
                    {
                        "level": r.level.lower(),
                        "text": r.text.get(lang) or r.text.get("en") or r.expression,
                        "leaf_id": r.leaf_id,
                        "teacher_rule_ids": list(r.teacher_rule_ids),
                    }
                    for r in runtime.rules
                ],
                "floors": [
                    {
                        "id": f.id,
                        "text": (f.text or {}).get(lang) or (f.text or {}).get("en") or f.when,
                        "min_level": f.level.name,
                        "locked": f.locked,
                        "status": f.status,
                    }
                    for f in profile.floors
                ],
                "placeholders": _placeholders(profile),
                "status": profile.status,
            }
        )
    from waechter.triage.compiler import COMPILER_VERSION

    return {"kb_version": kb.hash, "compiler_version": COMPILER_VERSION, "profiles": profiles}


def _placeholders(profile: ResolvedProfile) -> list[str]:
    ids = {
        rule.assumption
        for rule in (*profile.red_rules, *profile.yellow_rules, *profile.floors)
        if rule.assumption and rule.status == _STATUS
    }
    return sorted(ids)
