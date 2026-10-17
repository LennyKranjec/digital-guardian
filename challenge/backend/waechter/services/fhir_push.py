"""Push des Transaction-Bundles an einen FHIR-R4-Server (Vertrag v2.6/v2.8, nur Standardlib).

Konfiguration ausschließlich aus der Umgebung: `WAECHTER_FHIR_BASE_URL` (ohne URL ⇒ `disabled`),
optional `WAECHTER_FHIR_USER` / `WAECHTER_FHIR_PASSWORD` (Basic Auth). Zugangsdaten stehen weder in
Log noch Repr noch Antwort; Fehlertexte enthalten nur Statuscodes und FHIR-Fehlerarten, keine
Patientendaten und keine URL. Nur synthetische Patientinnen (sonst 409 `not_synthetic`).
Das URL-Schema ist auf http(s) begrenzt.
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.services import fhir_export
from waechter.services.patient_views import get_patient

LOG = logging.getLogger("waechter.fhir_push")

BASE_URL_ENV: Final = "WAECHTER_FHIR_BASE_URL"
USER_ENV: Final = "WAECHTER_FHIR_USER"
PASSWORD_ENV: Final = "WAECHTER_FHIR_PASSWORD"  # noqa: S105 (Name der Variablen, kein Wert)
TIMEOUT_SECONDS: Final = 20.0
MAX_ERRORS: Final = 10
MEDIA_TYPE: Final = "application/fhir+json"


@dataclass(frozen=True)
class PushConfig:
    base_url: str | None
    user: str | None = None
    password: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:  # kein Passwort, keine URL (kann Zugangsdaten enthalten)
        return f"PushConfig(enabled={self.enabled}, auth={self.user is not None})"

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def authorization(self) -> str | None:
        if not self.user:
            return None
        token = base64.b64encode(f"{self.user}:{self.password or ''}".encode()).decode("ascii")
        return f"Basic {token}"


def config_from_env(env: Mapping[str, str] | None = None) -> PushConfig:
    source = os.environ if env is None else env
    base = (source.get(BASE_URL_ENV) or "").strip()
    if base and urlsplit(base).scheme not in {"http", "https"}:
        LOG.warning("%s hat kein http(s)-Schema, Push bleibt deaktiviert", BASE_URL_ENV)
        base = ""
    return PushConfig(
        base_url=base or None,
        user=(source.get(USER_ENV) or None),
        password=(source.get(PASSWORD_ENV) or None),
    )


def _result(
    status: str,
    http_status: int | None,
    entries: int,
    created: int = 0,
    updated: int = 0,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "http_status": http_status,
        "entries": entries,
        "created": created,
        "updated": updated,
        "errors": (errors or [])[:MAX_ERRORS],
    }


def _outcome_errors(body: Any) -> list[str]:
    """Art und Schwere der Meldungen eines OperationOutcome, ohne Freitext (Datenschutz)."""
    if not isinstance(body, dict) or body.get("resourceType") != "OperationOutcome":
        return []
    issues = body.get("issue")
    if not isinstance(issues, list):
        return []
    return [
        f"{i.get('severity', 'error')}: {i.get('code', 'unknown')}"
        for i in issues
        if isinstance(i, dict)
    ]


def _parse(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None


def _evaluate(http_status: int, raw: bytes, entries: int) -> dict[str, Any]:
    """Bewertung der Serverantwort (`transaction-response`): 201 neu, 200 ersetzt, sonst Fehler."""
    body = _parse(raw)
    if not isinstance(body, dict) or body.get("resourceType") != "Bundle":
        return _result("failed", http_status, entries, errors=["invalid_response"])
    created = updated = 0
    errors: list[str] = []
    for item in body.get("entry") or []:
        status = str(item.get("response", {}).get("status", "")) if isinstance(item, dict) else ""
        code = status.split(" ", 1)[0]
        if code == "201":
            created += 1
        elif code in {"200", "204"}:
            updated += 1
        else:
            errors.append(f"entry: HTTP {code or 'unknown'}")
    if body.get("type") != "transaction-response":
        errors.append("response: not a transaction-response")
    if len(body.get("entry") or []) != entries:
        errors.append("response: entry count differs")
    ok = not errors
    return _result("sent" if ok else "failed", http_status, entries, created, updated, errors)


def send(config: PushConfig, bundle: dict[str, Any], timeout: float) -> dict[str, Any]:
    """Sendet das Bundle; alle Fehlerarten werden zu `failed` (nie eine Exception)."""
    entries = len(bundle.get("entry", []))
    if not config.enabled or config.base_url is None:
        return _result("disabled", None, entries)
    headers = {"Content-Type": MEDIA_TYPE, "Accept": MEDIA_TYPE}
    authorization = config.authorization()
    if authorization is not None:
        headers["Authorization"] = authorization
    data = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310
        config.base_url, data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return _evaluate(int(response.status), response.read(), entries)
    except urllib.error.HTTPError as error:
        errors = [f"HTTP {error.code}"]
        try:
            errors.extend(_outcome_errors(_parse(error.read())))
        finally:
            error.close()
        return _result("failed", error.code, entries, errors=errors)
    except TimeoutError:
        return _result("failed", None, entries, errors=["timeout"])
    except urllib.error.URLError as error:
        reason = "timeout" if isinstance(error.reason, TimeoutError) else "connection_failed"
        return _result("failed", None, entries, errors=[reason])
    except OSError:
        return _result("failed", None, entries, errors=["connection_failed"])


def push(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient_id: str,
    content: Content,
    config: PushConfig | None = None,
) -> dict[str, Any]:
    patient = get_patient(session, patient_id)
    if not patient.synthetic:
        raise ApiError(409, "not_synthetic", "Only synthetic patients may be pushed")
    bundle = fhir_export.transaction_bundle(session, clock, content, patient)
    result = send(config if config is not None else config_from_env(), bundle, TIMEOUT_SECONDS)
    record_audit(
        session,
        clock,
        principal.actor,
        "fhir_push",
        "patient",
        target_id=patient.id,
        subject_id=patient.id,
        details={"status": result["status"], "entries": result["entries"]},
    )
    session.commit()
    LOG.info("FHIR-Push: status=%s entries=%s", result["status"], result["entries"])
    return result
