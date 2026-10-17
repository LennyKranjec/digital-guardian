"""Demo zurücksetzen: Demo-DB löschen, migrieren, seeden, Ergebnis prüfen (Runbook, challenge/demo).

Das Kernstück für `challenge/demo/reset.ps1|sh`. Es löscht **nur** eine Datenbankdatei namens
`demo.db` in einem Ordner `data` (Standard `platform/backend/data/demo.db`); jede andere URL oder
Datei wird abgelehnt. Danach laufen Migration und Seed wie bei `python -m app.cli seed`, und eine
kurze Prüfung per Testclient (ohne Server) bestätigt den Ausgangszustand der Demo.

Kein Netz außer dem konfigurierten LLM-Modus (Standard `template`: kein Netz).
"""

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final

from fastapi.testclient import TestClient

from app.core.db import create_db_engine
from app.core.settings import Settings
from app.main import create_app
from app.persistence.migrate import upgrade_to_head
from app.plugins import load_challenge_plugin
from app.registry import Registry
from app.services import seed
from app.services.seed import DEMO_PASSWORD
from waechter.content import ContentError, get_content

DEMO_DB_NAME: Final = "demo.db"
DEMO_DB_DIR: Final = "data"
DEMO_ANCHOR: Final = "2026-10-17T09:00:00+02:00"
SQLITE_PREFIX: Final = "sqlite:///"
ACCOUNTS: Final = ("admin", "doctor", "patient", "patient2", "patient6")
SIDE_FILES: Final = ("", "-wal", "-shm", "-journal")
CSRF: Final = {"X-Requested-With": "fetch"}
API: Final = "/api/v1"


class DemoResetError(RuntimeError):
    """Der Reset wurde abgelehnt oder konnte nicht durchgeführt werden."""


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Report:
    database: Path
    checks: list[Check] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))

    def render(self) -> str:
        rows = [
            f"{'OK  ' if c.ok else 'FAIL'} {c.name}" + (f" - {c.detail}" if c.detail else "")
            for c in self.checks
        ]
        verdict = "Demo bereit." if self.ok else "Demo NICHT bereit - Prüfung fehlgeschlagen."
        return "\n".join([f"Demo-DB: {self.database}", *self.lines, *rows, verdict])


def demo_db_path(settings: Settings) -> Path:
    """Pfad der Demo-DB; lehnt alles andere als `…/data/demo.db` (SQLite-Datei) ab."""
    url = settings.resolved_database_url
    if not url.startswith(SQLITE_PREFIX):
        raise DemoResetError("DATABASE_URL must be a SQLite file (sqlite:///…/data/demo.db)")
    raw = url.removeprefix(SQLITE_PREFIX)
    if raw in ("", ":memory:"):
        raise DemoResetError("DATABASE_URL must be a SQLite file (sqlite:///…/data/demo.db)")
    path = Path(raw)
    if path.name != DEMO_DB_NAME or path.parent.name != DEMO_DB_DIR:
        raise DemoResetError(
            f"refusing to reset {path.name!r}: only a file named {DEMO_DB_NAME} in a folder named "
            f"{DEMO_DB_DIR} is deleted"
        )
    return path


def _delete_database(path: Path) -> None:
    for suffix in SIDE_FILES:
        Path(f"{path}{suffix}").unlink(missing_ok=True)


def demo_settings(settings: Settings) -> Settings:
    """Erzwingt Demo-Betrieb: `DEMO_MODE`, eingefrorene Ankerzeit (falls nicht gesetzt)."""
    frozen = settings.app_frozen_now or datetime.fromisoformat(DEMO_ANCHOR)
    return settings.model_copy(update={"demo_mode": True, "app_frozen_now": frozen})


def _migrate_and_seed(settings: Settings) -> None:
    registry = Registry()
    if not load_challenge_plugin(settings, registry):
        raise DemoResetError("challenge plugin not found")
    engine = create_db_engine(settings.resolved_database_url)
    try:
        upgrade_to_head(engine, registry)
    finally:
        engine.dispose()
    app = create_app(settings)
    try:
        with app.state.session_factory() as session:
            seed.provision(session, settings, app.state.registry, app.state.clock)
    finally:
        app.state.engine.dispose()


def verify(settings: Settings, report: Report) -> None:
    """Prüft den Ausgangszustand per Testclient (kein Server): Konten, Ampeln, Kurzfassung."""
    try:
        content = get_content()
    except ContentError as error:
        report.add("Inhalt", False, f"{len(error.issues)} Verstöße")
        return
    if content is None:
        report.add("Inhalt", False, "Inhaltsordner fehlt")
        return
    anchor = datetime.fromisoformat(content.scenario["anchor"])
    clock_ok = settings.app_frozen_now == anchor
    report.add(
        "Uhr = Ankerzeit des Szenarios", clock_ok, f"APP_FROZEN_NOW={settings.app_frozen_now}"
    )
    _verify_triage(report)
    app = create_app(settings)
    try:
        with TestClient(app, headers=CSRF) as client:
            _verify_accounts(client, report)
            _verify_cockpit(client, content.scenario["patients"], clock_ok, report)
    finally:
        app.state.engine.dispose()


def _verify_triage(report: Report) -> None:
    """Kompiliert und verifiziert alle Triage-Profile (Vorwärmen, Fehler fallen sofort auf)."""
    from waechter.services import triage  # spät: lädt den Triage-Kern erst für den Reset

    started = time.monotonic()
    try:
        count = triage.compile_all()
    except Exception as error:  # jede Ursache melden, der Reset bricht nicht ab
        report.add("Triage-Profile kompiliert", False, type(error).__name__)
        return
    if count is None:
        report.lines.append("  Triage: keine Wissensbasis (triage.yaml fehlt)")
        return
    report.add(
        f"Triage-Profile kompiliert und verifiziert ({count})",
        count > 0,
        f"{time.monotonic() - started:.0f} s",
    )


def _login(client: TestClient, username: str) -> bool:
    response = client.post(
        f"{API}/auth/login", json={"username": username, "password": DEMO_PASSWORD}
    )
    return response.status_code == 200


def _verify_accounts(client: TestClient, report: Report) -> None:
    failed = [name for name in ACCOUNTS if not _login(client, name)]
    report.add(
        "Demo-Konten (admin, doctor, patient, patient2, patient6)", not failed, ", ".join(failed)
    )


def _verify_cockpit(
    client: TestClient,
    scenario_patients: list[dict[str, object]],
    clock_ok: bool,
    report: Report,
) -> None:
    _login(client, "doctor")
    rows = client.get(f"{API}/waechter/patients").json()
    by_pseudonym = {r["pseudonym"]: r for r in rows}
    report.add(
        f"Patientinnen = {len(scenario_patients)}",
        len(by_pseudonym) == len(scenario_patients),
        f"{len(by_pseudonym)} gefunden",
    )
    for spec in scenario_patients:
        expected = spec.get("expected")
        row = by_pseudonym.get(str(spec["pseudonym"]))
        if not isinstance(expected, dict) or row is None:
            continue
        want = expected["traffic_light_at_anchor"]
        report.add(
            f"Ampel {spec['pseudonym']} = {want}",
            clock_ok and row["traffic_light"] == want,
            f"ist {row['traffic_light']}, offene Meldungen {row['open_alerts']}",
        )
        report.lines.append(
            f"  {spec['pseudonym']}: {row['traffic_light']:<6} offen {row['open_alerts']}  "
            f"{row['display_name']}"
        )
    demo = by_pseudonym.get("SYN-0001")
    if demo is None:
        report.add("SYN-0001 vorhanden", False)
        return
    summary = client.get(f"{API}/waechter/patients/{demo['patient_id']}/summary")
    body = summary.json() if summary.status_code == 200 else {}
    report.add(
        "SYN-0001 hat eine Kurzfassung",
        summary.status_code == 200 and bool(body.get("sentences")),
        f"Modus {body.get('mode')}, {len(body.get('sentences', []))} Sätze, "
        f"{body.get('dropped_sentences')} verworfen",
    )
    notes = client.get(f"{API}/waechter/notifications").json()
    report.lines.append(f"  Sofortbenachrichtigungen: {len(notes)}")


def reset_demo(settings: Settings) -> Report:
    """Setzt die Demo-DB zurück und liefert den Prüfbericht (`DemoResetError` bei Ablehnung)."""
    settings = demo_settings(settings)
    path = demo_db_path(settings)
    _delete_database(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = Report(database=path)
    _migrate_and_seed(settings)
    report.add("Datenbank angelegt", path.is_file(), path.name)
    verify(settings, report)
    return report


def main() -> int:
    """Einstieg für `challenge/demo/reset.py`: Einstellungen aus Umgebung/.env."""
    for stream in (sys.stdout, sys.stderr):  # Namen mit Umlauten auch auf cp1252-Konsolen
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    try:
        report = reset_demo(Settings())
    except DemoResetError as error:
        print(f"Reset abgelehnt: {error}", file=sys.stderr)
        return 2
    print(report.render())
    return 0 if report.ok else 1
