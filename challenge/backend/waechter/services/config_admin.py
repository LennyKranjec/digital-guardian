"""Versionierte Konfigurationsänderung durch die Administration (G-12, DR-014, T-09).

`PUT /config/rules|report` legt eine neue Version `rules-vN+1` bzw. `report-vN+1` an und aktiviert
sie. Die Änderung ist bedingt (`expected_version` = aktive Version, sonst 409 `version_conflict`):
das Umschalten der aktiven Version ist ein einziges `UPDATE … WHERE version = expected AND active`,
so gewinnt bei gleichzeitigen Änderungen genau eine. Geprüft wird wie beim Laden der Dateien
(Schema und Querverweise, Fehler mit Feldpfad, nie mit Werten) plus Sicherheitsböden:

- mindestens eine aktive **rote** Regel, die mit gültigen Antworten auslösen kann: Schwellen im
  Bereich der Skala 0-4 bzw. `presence` 0/1 **und** mindestens eine Kombination Symptom/Attribut
  des Fragebogens, auf die die Regel zutrifft (T-09G; sonst 422 `no_red_rule`),
- keine `NaN`/`Infinity`-Zahlen und plausible Bereiche (Skalenwerte 0-4, Tage 1-366),
- rote Meldungen bleiben sofort zu melden (`noise.notify_levels` enthält `red`, sonst 422
  `no_red_notification`),
- Parameter je Regelart vollständig und sinnvoll (sonst scheitert die Regel-Engine zur Laufzeit).

Bereits erzeugte Meldungen behalten ihre `rule_version`; die Engine nutzt die neue Version für neue
Antworten. Jede Änderung wird auditiert (`config_change`: Art, alte und neue Version, Länge der
Notiz; nie Werte).
"""

import math
import re
from typing import Any, Final

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.persistence.models import User
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import ContentIssue, validate_document
from waechter.models import ConfigVersion
from waechter.services.alerts import rule_applies
from waechter.services.config import require_content
from waechter.services.questionnaire import max_value
from waechter.timeutil import iso_prague

KINDS: Final = ("rules", "report")
#: Pflichtparameter je Regelart: (Untergrenze, strikt?, Obergrenze). Skalenwerte reichen von 0 bis
#: `SCALE_MAX`; Tage von 0 (ausgeschlossen) bis `DAYS_MAX`.
SCALE_MAX: Final = 4.0
DAYS_MAX: Final = 366.0
Bound = tuple[float, bool, float | None]
REQUIRED_PARAMS: Final[dict[str, dict[str, Bound]]] = {
    "threshold": {"min_value": (0, False, SCALE_MAX)},
    "baseline_delta": {
        "baseline_days": (0, True, DAYS_MAX),
        "min_delta": (0, False, SCALE_MAX),
        "min_value": (0, False, SCALE_MAX),
    },
    "trend": {
        "window_days": (0, True, DAYS_MAX),
        "min_points": (2, False, DAYS_MAX),
        "horizon_days": (0, False, DAYS_MAX),
        "target_value": (0, False, SCALE_MAX),
        "min_slope_per_day": (0, False, SCALE_MAX),
    },
    "missing": {"max_days_without_response": (0, True, DAYS_MAX)},
}
VERSION_NUMBER: Final = re.compile(r"-v([0-9]+)$")


def _field(path: str, code: str, message: str) -> FieldError:
    return FieldError(field=path.removeprefix("$.").removeprefix("$"), code=code, message=message)


def _issues(issues: list[ContentIssue], prefix: str) -> list[FieldError]:
    return [_field(f"{prefix}{i.path.removeprefix('$')}", "invalid", i.message) for i in issues]


def _param_errors(rules: list[dict[str, Any]]) -> list[FieldError]:
    errors: list[FieldError] = []
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        base = f"rules.rules[{index}]"
        if rule["id"] in seen:
            errors.append(_field(f"{base}.id", "duplicate_id", "duplicate id"))
        seen.add(rule["id"])
        for name, bound in REQUIRED_PARAMS[rule["kind"]].items():
            params: dict[str, Any] = rule["params"]
            if name not in params:
                errors.append(
                    _field(f"{base}.params.{name}", "required", "required field is missing")
                )
            else:
                lower, exclusive, upper = bound
                value = params[name]
                if value < lower or (exclusive and value == lower) or (upper and value > upper):
                    errors.append(_field(f"{base}.params.{name}", "out_of_range", "out of range"))
        errors.extend(_window_errors(base, rule))
    return errors


def _window_errors(base: str, rule: dict[str, Any]) -> list[FieldError]:
    """Trend: das Fenster muss mindestens `min_points` Tage umfassen (ein Wert je Tag zählt)."""
    params: dict[str, Any] = rule["params"]
    has_both = {"window_days", "min_points"} <= params.keys()
    if rule["kind"] == "trend" and has_both and params["window_days"] < params["min_points"]:
        return [_field(f"{base}.params.window_days", "out_of_range", "window below min_points")]
    return []


def _non_finite(value: Any, path: str) -> list[FieldError]:
    """`NaN`/`±Infinity` sind nie gültig (JSON-Erweiterung von Python); Pfad statt Wert melden."""
    if isinstance(value, float) and not math.isfinite(value):
        return [_field(path, "non_finite", "number must be finite")]
    if isinstance(value, dict):
        return [e for k, v in value.items() for e in _non_finite(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [e for i, v in enumerate(value) for e in _non_finite(v, f"{path}[{i}]")]
    return []


def _asked_pairs() -> list[tuple[str, str]]:
    """Alle Kombinationen Symptom/Attribut, die der Fragebogen überhaupt erfragt (Itemkatalog)."""
    content = require_content()
    return [
        (item["symptom_key"], attribute["attribute"])
        for item in content.items["items"]
        for attribute in item["attributes"]
    ]


def _reachable(rule: dict[str, Any], asked: list[tuple[str, str]]) -> bool:
    """Kann die Regel mit gültigen Antworten überhaupt auslösen?

    Es muss eine erfragte Kombination Symptom/Attribut geben, auf die die Regel zutrifft (sonst
    löst sie nie aus), und alle Schwellen müssen im Wertebereich dieses Attributs liegen
    (`presence` 0/1, sonst 0-4).
    """
    params: dict[str, Any] = rule["params"]
    needed = [params[n] for n in ("min_value", "min_delta", "target_value") if n in params]
    return any(
        rule_applies(rule, symptom, attribute)
        and all(value <= max_value(attribute) for value in needed)
        for symptom, attribute in asked
    )


def _symptom_errors(rules: list[dict[str, Any]]) -> list[FieldError]:
    content = require_content()
    known = {item["symptom_key"] for item in content.items["items"]}
    return [
        _field(f"rules.rules[{i}].symptom_keys[{j}]", "unknown_symptom", "unknown symptom_key")
        for i, rule in enumerate(rules)
        for j, key in enumerate(rule.get("symptom_keys", []))
        if key not in known
    ]


def validate_rules(document: dict[str, Any]) -> None:
    """Schema, Querverweise, Parameter und Sicherheitsböden; wirft `ApiError` 422."""
    errors = _non_finite(document, "rules")
    errors += _issues(validate_document("rules", document), "rules") if not errors else []
    if errors:
        raise ApiError(422, "validation_failed", "Invalid rules", errors)
    rules: list[dict[str, Any]] = document["rules"]
    errors = [*_param_errors(rules), *_symptom_errors(rules)]
    if errors:
        raise ApiError(422, "validation_failed", "Invalid rules", errors)
    asked = _asked_pairs()
    if not any(r["enabled"] and r["level"] == "red" and _reachable(r, asked) for r in rules):
        raise ApiError(
            422,
            "no_red_rule",
            "At least one enabled, reachable red rule is required",
            [_field("rules.rules", "no_red_rule", "no enabled red rule that can trigger")],
        )
    if "red" not in document["noise"]["notify_levels"]:
        raise ApiError(
            422,
            "no_red_notification",
            "Red alerts must stay in noise.notify_levels",
            [_field("rules.noise.notify_levels", "no_red_notification", "red is required")],
        )


def validate_report(document: dict[str, Any]) -> None:
    errors = _non_finite(document, "report")
    errors += _issues(validate_document("report", document), "report") if not errors else []
    if errors:
        raise ApiError(422, "validation_failed", "Invalid report", errors)


def _number(version: str) -> int:
    match = VERSION_NUMBER.search(version)
    return int(match.group(1)) if match else 0


def _display_name(session: Session, user_id: str | None) -> str:
    user = session.get(User, user_id) if user_id else None
    return user.display_name if user is not None else "system"


def _state(session: Session, row: ConfigVersion) -> dict[str, Any]:
    return {
        "version": row.version,
        "changed_at": iso_prague(row.created_at),
        "changed_by": _display_name(session, row.created_by),
        "change_note": row.change_note,
    }


def update_config(
    session: Session,
    clock: Clock,
    principal: Principal,
    kind: str,
    expected_version: str,
    body: dict[str, Any],
    change_note: str | None,
) -> dict[str, Any]:
    """Neue Version aktivieren (nur Administration; Aufrufer prüft die Rolle)."""
    if "version" in body:
        raise ApiError(
            422,
            "validation_failed",
            "version is assigned by the server",
            [_field(f"{kind}.version", "not_allowed", "version is assigned by the server")],
        )
    placeholder = {"version": f"{kind}-v1", **body}
    (validate_rules if kind == "rules" else validate_report)(placeholder)

    rows = session.scalars(select(ConfigVersion).where(ConfigVersion.kind == kind)).all()
    active = next((r for r in rows if r.active), None)
    if active is None or active.version != expected_version:
        raise ApiError(409, "version_conflict", "Active version differs from expected_version")
    new_version = f"{kind}-v{max(_number(r.version) for r in rows) + 1}"

    switched = session.execute(
        update(ConfigVersion)
        .where(
            ConfigVersion.id == active.id,
            ConfigVersion.active.is_(True),
            ConfigVersion.version == expected_version,
        )
        .values(active=False)
    )
    if switched.rowcount != 1:  # type: ignore[attr-defined]  # CursorResult.rowcount
        session.rollback()
        raise ApiError(409, "version_conflict", "Active version differs from expected_version")
    row = ConfigVersion(
        kind=kind,
        version=new_version,
        body_json={"version": new_version, **body},
        active=True,
        created_at=clock.now(),
        created_by=principal.user_id,
        change_note=change_note,
    )
    session.add(row)
    record_audit(
        session,
        clock,
        principal.actor,
        "config_change",
        "config",
        target_id=new_version,
        details={
            "kind": kind,
            "from": expected_version,
            "to": new_version,
            "note_length": len(change_note or ""),
        },
    )
    try:
        session.commit()
    except IntegrityError:  # paralleler Wechsel war schneller
        session.rollback()
        raise ApiError(409, "version_conflict", "Active version changed concurrently") from None
    return _state(session, row)


def history(session: Session, kind: str) -> list[dict[str, Any]]:
    """Alle Versionen der Art, neueste zuerst: wer, wann, Notiz, aktiv."""
    rows = session.scalars(select(ConfigVersion).where(ConfigVersion.kind == kind)).all()
    ordered = sorted(rows, key=lambda r: (-_number(r.version), r.id))
    return [
        {
            "version": r.version,
            "changed_at": iso_prague(r.created_at),
            "changed_by": _display_name(session, r.created_by),
            "change_note": r.change_note,
            "active": r.active,
        }
        for r in ordered
    ]
