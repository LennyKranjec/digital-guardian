"""Meldungserzeugung: Regeln auf die Historie, Rauschbremse, Safety-Ausnahme, Benachrichtigung.

Das LLM bestimmt hier nichts: Stufen und Schwellen kommen aus der versionierten Konfiguration
(`rules-vN`), die Entscheidung aus den reinen Funktionen in `rules.py`. Jede Meldung speichert die
vollständige Erklärung (Regel, Version, Parameter, Beobachtung, Fenster, Belege).

Rauschbremse (README §3): höchstens eine offene Meldung je `(rule_id, symptom_key, attribute)`, nach
Quittierung `cooldown_hours` Ruhe. Safety vor Rauschbremse (G-02): ein höherer Wert als der der
bestehenden Meldung desselben Tripels bricht Dedupe und Cooldown durch. `R-MIS-01` (missing) wird
nicht hier ausgewertet (T-05).
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.ports.notifier import Notice
from waechter.content import Content
from waechter.models import (
    Alert,
    AlertAction,
    Answer,
    Notification,
    Patient,
    Response,
    Therapy,
)
from waechter.notifier import get_notifier
from waechter.services import rules as engine
from waechter.services.config import active_body, require_content
from waechter.services.questionnaire import localize
from waechter.timeutil import iso_prague, to_prague

logger = logging.getLogger("waechter.alerts")

STATUS_OPEN: Final = "open"
STATUS_ACKNOWLEDGED: Final = "acknowledged"
ACTION_ACKNOWLEDGE: Final = "acknowledge"
EVALUATED_KINDS: Final = ("threshold", "baseline_delta", "trend")
DEFAULT_LANG: Final = "cs"
PENDING_NOTICES: Final = "waechter.pending_notices"
#: Platzhalter für Meldungen ohne Symptom (R-MIS-01); die Spalte ist NOT NULL, die API liefert null
NO_SYMPTOM: Final = ""

_HEADLINES: Final = {
    "threshold": {
        "cs": "{subject}: hodnota {value} dosáhla prahu {threshold}",
        "en": "{subject}: value {value} reached threshold {threshold}",
        "de": "{subject}: Wert {value} hat die Schwelle {threshold} erreicht",
    },
    "baseline_delta": {
        "cs": "{subject}: hodnota {value}, výchozí hodnota {baseline} (změna +{delta})",
        "en": "{subject}: value {value}, baseline {baseline} (change +{delta})",
        "de": "{subject}: Wert {value}, Ausgangswert {baseline} (Änderung +{delta})",
    },
    "missing": {
        "cs": "Bez odpovědi {days} dní (limit {limit})",
        "en": "No response for {days} days (limit {limit})",
        "de": "Seit {days} Tagen ohne Antwort (Grenze {limit})",
    },
    "trend": {
        "cs": "{subject}: rostoucí trend +{slope} za den, odhad {projected}",
        "en": "{subject}: rising trend +{slope} per day, projected {projected}",
        "de": "{subject}: steigender Trend +{slope} pro Tag, Prognose {projected}",
    },
}

#: Lokalisierte Attributnamen für die Headline; `presence` (ja/nein) wird nicht genannt (leer).
_ATTRIBUTE_LABELS: Final = {
    "severity": {"cs": "závažnost", "en": "severity", "de": "Schweregrad"},
    "frequency": {"cs": "četnost", "en": "frequency", "de": "Häufigkeit"},
    "interference": {
        "cs": "vliv na běžné činnosti",
        "en": "interference with daily activities",
        "de": "Beeinträchtigung im Alltag",
    },
}


def _fact(prefix: str, ident: str) -> str:
    return f"{prefix}-{ident}"


def load_series(
    session: Session, response: Response, symptom_key: str, attribute: str
) -> list[engine.Point]:
    """Werte (ohne `null`) der Patientin bis einschließlich dieser Antwort, chronologisch.

    Sortierung `(recorded_at, response_id)` (G-08); übersprungene Werte bleiben Lücken.
    """
    rows = session.execute(
        select(Answer.value, Answer.id, Response.recorded_at, Response.id)
        .join(Response, Response.id == Answer.response_id)
        .where(
            Response.patient_id == response.patient_id,
            Answer.symptom_key == symptom_key,
            Answer.attribute == attribute,
            Answer.value.is_not(None),
            or_(
                Response.recorded_at < response.recorded_at,
                and_(Response.recorded_at == response.recorded_at, Response.id <= response.id),
            ),
        )
        .order_by(Response.recorded_at, Response.id)
    )
    return [
        engine.Point(t=recorded_at, value=int(value), ref=_fact("obs", answer_id))
        for value, answer_id, recorded_at, _ in rows
        if value is not None
    ]


def rule_applies(rule: dict[str, Any], symptom_key: str, attribute: str) -> bool:
    keys: Sequence[str] = rule.get("symptom_keys") or ()
    attributes: Sequence[str] = rule.get("attributes") or ()
    return (not keys or symptom_key in keys) and (not attributes or attribute in attributes)


def regimen_change(session: Session, patient_id: str, now: datetime) -> tuple[datetime, str] | None:
    """Start des aktuellen Therapieschemas, falls es einem anderen Schema folgt (T-25).

    Maßgeblich sind die Therapie-Einträge bis `now`. Ein neuer Zyklus desselben Schemas setzt
    nicht zurück; der Start ist der erste Eintrag der letzten Folge gleicher `regimen_id`. Ohne
    Wechsel (nur ein Schema bisher) gibt es keine Begrenzung: `None`.
    """
    rows = session.execute(
        select(Therapy.regimen_id, Therapy.cycle_start)
        .where(Therapy.patient_id == patient_id, Therapy.cycle_start <= now)
        .order_by(Therapy.cycle_start, Therapy.id)
    ).all()
    if not rows:
        return None
    index = len(rows) - 1
    current = rows[index].regimen_id
    while index > 0 and rows[index - 1].regimen_id == current:
        index -= 1
    return None if index == 0 else (rows[index].cycle_start, current)


def _run(
    rule: dict[str, Any],
    now: datetime,
    value: int,
    series: list[engine.Point],
    since_regimen: datetime | None = None,
) -> engine.RuleHit | None:
    params: dict[str, float] = rule["params"]
    if rule["kind"] == "threshold":
        return engine.threshold(value, params)
    if rule["kind"] == "baseline_delta":
        return engine.baseline_delta(
            now, value, [p for p in series if p.t < now], params, since_regimen
        )
    return engine.trend(now, value, series, params)


def _cycle_day(session: Session, response: Response) -> int | None:
    """Zyklustag (1 = Zyklusbeginn) nach Kalendertagen in Europe/Prague (G-04)."""
    start = session.scalar(
        select(Therapy.cycle_start)
        .where(Therapy.patient_id == response.patient_id)
        .order_by(Therapy.cycle_start.desc())
        .limit(1)
    )
    if start is None:
        return None
    days = (to_prague(response.recorded_at).date() - to_prague(start).date()).days
    return days + 1 if days >= 0 else None


def _alert_value(alert: Alert) -> float | None:
    value = alert.explanation_json.get("observed", {}).get("value")
    return None if value is None else float(value)


def _acknowledged_at(session: Session, alert: Alert) -> datetime:
    at = session.scalar(
        select(AlertAction.at)
        .where(AlertAction.alert_id == alert.id, AlertAction.action == ACTION_ACKNOWLEDGE)
        .order_by(AlertAction.at.desc())
        .limit(1)
    )
    return at or alert.created_at


def _recovered_since(session: Session, alert: Alert, now: datetime) -> bool:
    """DR-012: zwischen Meldung und jetzt liegt eine Antwort des Tripels unter der Auslöseschwelle.

    Maßgeblich ist `params.min_value` der Meldung (Schwellen- und Baseline-Regeln); Trend-Meldungen
    haben keine solche Schwelle und enden nicht durch Entwarnung.
    """
    threshold = alert.explanation_json.get("params", {}).get("min_value")
    if threshold is None or alert.attribute is None or alert.symptom_key == NO_SYMPTOM:
        return False
    return (
        session.scalar(
            select(Answer.id)
            .join(Response, Response.id == Answer.response_id)
            .where(
                Response.patient_id == alert.patient_id,
                Response.recorded_at > alert.created_at,
                Response.recorded_at < now,
                Answer.symptom_key == alert.symptom_key,
                Answer.attribute == alert.attribute,
                Answer.value.is_not(None),
                Answer.value < threshold,
            )
            .limit(1)
        )
        is not None
    )


def suppressed(
    session: Session,
    patient_id: str,
    rule_id: str,
    symptom_key: str,
    attribute: str,
    value: int,
    now: datetime,
    cooldown_hours: float,
) -> bool:
    """Rauschbremse mit Safety-Ausnahmen (G-02, DR-012): `True`, wenn keine Meldung entsteht."""
    existing = session.scalars(
        select(Alert).where(
            Alert.patient_id == patient_id,
            Alert.rule_id == rule_id,
            Alert.symptom_key == symptom_key,
            Alert.attribute == attribute,
        )
    ).all()
    blocking: list[float] = []
    for alert in existing:
        if _recovered_since(session, alert, now):
            continue  # Entwarnung beendet die Episode (DR-012): Rückfall ⇒ sofort neue Meldung
        quiet_until = _acknowledged_at(session, alert) + timedelta(hours=cooldown_hours)
        if alert.status == STATUS_OPEN or now < quiet_until:
            blocking.append(_alert_value(alert) or 0.0)
    if not blocking:
        return False
    return float(value) <= max(blocking)  # nur eine Verschlechterung bricht die Bremse durch


_TRIAGE_HEADLINES: Final = {
    "R-TRI-RED": {
        "cs": "Triáž: červená úroveň (zástupná pravidla)",
        "en": "Triage: red level (placeholder rules)",
        "de": "Triage: Stufe Rot (Platzhalter-Regeln)",
    },
    "R-TRI-YEL": {
        "cs": "Triáž: žlutá úroveň (zástupná pravidla)",
        "en": "Triage: yellow level (placeholder rules)",
        "de": "Triage: Stufe Gelb (Platzhalter-Regeln)",
    },
}


def headline(alert: Alert, content: Content, lang: str = DEFAULT_LANG) -> str:
    """Deterministische Kurzbeschreibung aus Regel und Werten (cs/en; sonst Englisch)."""
    triage = _TRIAGE_HEADLINES.get(alert.rule_id)
    if triage is not None:  # Meldungen des Triage-Baums (T-16): ohne Symptom, ohne Schwelle
        return triage.get(lang, triage["en"])
    explanation = alert.explanation_json
    observed = explanation.get("observed", {})
    params = explanation.get("params", {})
    labels = {i["symptom_key"]: i["label"] for i in content.items["items"]}
    label = localize(labels[alert.symptom_key], lang) if alert.symptom_key in labels else ""
    templates = _HEADLINES[explanation["kind"]]
    return templates.get(lang, templates["en"]).format(
        subject=_subject(label, alert.attribute, lang),
        value=_plain(observed.get("value")),
        threshold=_plain(params.get("min_value")),
        baseline=_plain(observed.get("baseline")),
        delta=_plain(observed.get("delta")),
        slope=_plain(observed.get("slope_per_day")),
        projected=_plain(observed.get("projected_value")),
        days=_plain(observed.get("days_without_response")),
        limit=_plain(params.get("max_days_without_response")),
    )


def _subject(label: str, attribute: str | None, lang: str) -> str:
    """Symptom mit lokalisiertem Attribut („Průjem (závažnost)“); presence/unbekannt ohne."""
    names = _ATTRIBUTE_LABELS.get(attribute or "")
    if names is None:
        return label
    return f"{label} ({names.get(lang, names['en'])})"


def _plain(number: float | None) -> str:
    if number is None:
        return "?"
    return str(int(number)) if float(number).is_integer() else f"{number:g}"


def explanation_view(alert: Alert, lang: str = DEFAULT_LANG) -> dict[str, Any]:
    """Erklärung im Vertragsformat (`rationale` lokalisiert); Grundlage für die Lese-API."""
    stored = dict(alert.explanation_json)
    rationale = stored.pop("rationale_i18n", None)
    stored["rationale"] = localize(rationale, lang) if rationale else ""
    triage = stored.get("triage")
    if isinstance(triage, dict) and "reason_codes" in triage:
        stored["triage"] = {
            **triage,
            "reason_codes": [_reason_code_view(r, lang) for r in triage["reason_codes"] or []],
        }
    return stored


def _reason_code_view(entry: Any, lang: str) -> dict[str, Any]:
    """T-16G: Begründung als Objekt {code, text, kind?, items?}; Altbestand tolerant."""
    if isinstance(entry, str):
        return {"code": entry, "text": entry}
    view = {k: v for k, v in entry.items() if k != "text_i18n"}
    texts = entry.get("text_i18n") or {}
    view["text"] = texts.get(lang) or texts.get("en") or entry.get("text") or entry["code"]
    return view


def _explanation(
    session: Session,
    response: Response,
    rule: dict[str, Any],
    hit: engine.RuleHit,
    current_ref: str,
    change: tuple[datetime, str] | None = None,
) -> dict[str, Any]:
    observed: dict[str, float | None] = {
        "value": None,
        "baseline": None,
        "delta": None,
        "slope_per_day": None,
        "projected_value": None,
    }
    observed.update(hit.observed)
    evidence = [_fact("resp", response.id), current_ref]
    evidence += [ref for ref in hit.refs if ref not in evidence]
    window = (
        None
        if hit.window is None
        else {"from": iso_prague(hit.window[0]), "to": iso_prague(hit.window[1])}
    )
    explanation: dict[str, Any] = {
        "kind": rule["kind"],
        "params": dict(rule["params"]),
        "observed": observed,
        "baseline_window": window,
        "cycle_day": _cycle_day(session, response),
        "evidence": evidence,
        "rationale_i18n": rule["rationale"],
        "source_id": rule.get("source_id"),
    }
    if change is not None and _limited_by_regimen(rule, hit, change[0]):
        # T-25: das Baseline-Fenster beginnt beim Start des aktuellen Therapieschemas
        explanation["baseline_limit"] = {
            "reason": "regimen_change",
            "regimen_id": change[1],
            "since": iso_prague(change[0]),
        }
    return explanation


def _limited_by_regimen(rule: dict[str, Any], hit: engine.RuleHit, since: datetime) -> bool:
    """`True`, wenn der Therapiewechsel das Fenster gekürzt hat (sonst Erklärung wie vor T-25)."""
    if rule["kind"] != "baseline_delta" or hit.window is None:
        return False
    return hit.window[0] == since


def _notify(session: Session, patient: Patient, alert: Alert, content: Content) -> None:
    """Sofortbenachrichtigung: In-App-Zeile plus Port. Text nur mit Pseudonym (G-17)."""
    text = f"{patient.pseudonym}: {headline(alert, content)}"
    session.add(
        Notification(
            patient_id=patient.id,
            alert_id=alert.id,
            level=alert.level,
            channel="in_app",
            text=text,
            at=alert.created_at,
            synthetic=True,
        )
    )
    # Kanal erst nach dem Commit bedienen: ein Rollback darf keine Meldung "ausgesendet" haben.
    session.info.setdefault(PENDING_NOTICES, []).append(
        (Notice(subject_id=patient.id, kind=f"alert.{alert.level}", text=text), alert.created_at)
    )


def dispatch_pending_notices(session: Session) -> None:
    """Sendet die gesammelten Benachrichtigungen über den Port (nach dem Commit).

    Je Notice isoliert: ein Ausfall des Kanals gefährdet weder die gespeicherte Antwort (die
    Patientin bekommt weiter ihren Beleg) noch die übrigen Notices; geloggt wird nur der Typname.
    Die persistente Liste `wa_notifications` ist bereits geschrieben.
    """
    for notice, at in session.info.pop(PENDING_NOTICES, []):
        try:
            get_notifier().notify(notice, at)
        except Exception as error:  # Kanalausfall: Antwort ist gesichert, übrige Notices folgen
            logger.error("notification channel failed (%s)", type(error).__name__)


def discard_pending_notices(session: Session) -> None:
    session.info.pop(PENDING_NOTICES, None)


def red_symptom_keys(
    session: Session,
    response: Response,
    rules: dict[str, Any],
) -> list[str]:
    """Symptome, für die für diese Antwort mindestens eine aktive **rote** Regel feuert.

    Unabhängig von Rauschbremse und Cooldown (`suppressed`): Der Akut-Hinweis an die Patientin
    hängt daran, dass die Regel auslöst, nicht daran, ob eine neue Meldung angelegt wird. Reine
    Auswertung ohne Schreibzugriff.
    """
    answers = session.scalars(
        select(Answer)
        .where(Answer.response_id == response.id, Answer.value.is_not(None))
        .order_by(Answer.symptom_key, Answer.attribute)
    ).all()
    found: dict[str, None] = {}
    change = regimen_change(session, response.patient_id, response.recorded_at)
    for rule in rules["rules"]:
        if not rule["enabled"] or rule["level"] != "red" or rule["kind"] not in EVALUATED_KINDS:
            continue
        for answer in answers:
            if answer.value is None or not rule_applies(rule, answer.symptom_key, answer.attribute):
                continue
            series = load_series(session, response, answer.symptom_key, answer.attribute)
            since = change[0] if change else None
            if _run(rule, response.recorded_at, answer.value, series, since) is not None:
                found.setdefault(answer.symptom_key)
    return list(found)


def evaluate_response(
    session: Session,
    response: Response,
    *,
    content: Content | None = None,
    rules: dict[str, Any] | None = None,
) -> list[Alert]:
    """Wertet alle Antwortwerte dieser Antwort gegen die aktive Regelversion aus.

    Gibt die neu erzeugten Meldungen zurück. Gleiche Historie und Konfiguration ⇒ gleiche
    Meldungen (keine Uhr: Zeitbezug ist `response.recorded_at`).
    """
    content = content or require_content()
    rules = rules or active_body(session, "rules") or content.rules
    patient = session.get(Patient, response.patient_id)
    if patient is None:
        return []
    now = response.recorded_at
    noise = rules["noise"]
    created: list[Alert] = []
    change = regimen_change(session, patient.id, now)
    since = change[0] if change else None
    answers = session.scalars(
        select(Answer)
        .where(Answer.response_id == response.id, Answer.value.is_not(None))
        .order_by(Answer.symptom_key, Answer.attribute)
    ).all()
    for rule in rules["rules"]:
        if not rule["enabled"] or rule["kind"] not in EVALUATED_KINDS:
            continue
        for answer in answers:
            if answer.value is None or not rule_applies(rule, answer.symptom_key, answer.attribute):
                continue
            series = load_series(session, response, answer.symptom_key, answer.attribute)
            hit = _run(rule, now, answer.value, series, since)
            if hit is None or suppressed(
                session,
                patient.id,
                rule["id"],
                answer.symptom_key,
                answer.attribute,
                answer.value,
                now,
                noise["cooldown_hours"],
            ):
                continue
            alert = Alert(
                patient_id=patient.id,
                response_id=response.id,
                rule_id=rule["id"],
                rule_version=rules["version"],
                level=rule["level"],
                symptom_key=answer.symptom_key,
                attribute=answer.attribute,
                status=STATUS_OPEN,
                explanation_json=_explanation(
                    session, response, rule, hit, _fact("obs", answer.id), change
                ),
                notified=rule["level"] in noise["notify_levels"],
                version=1,
                created_at=now,
                synthetic=True,
            )
            session.add(alert)
            session.flush()
            if alert.notified:
                _notify(session, patient, alert, content)
            created.append(alert)
    session.flush()
    return created
