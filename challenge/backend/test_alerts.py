"""Meldungen: Orakel aus scenario.yaml, Erklärung, Rauschbremse + Safety, Benachrichtigung."""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.memory_notifier import MemoryNotifier
from app.main import create_app
from app.services import seed
from conftest import CHALLENGE_DIR, FROZEN_NOW, login, make_settings, migrate
from waechter import notifier
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, get_content
from waechter.models import Alert, AlertAction, Notification, Patient, Response
from waechter.services.alerts import explanation_view, headline
from waechter.timeutil import to_prague

RESPONSES = "/api/v1/waechter/me/responses"
QID = "items-v1:FIX-REG"
REAL_CONTENT = CHALLENGE_DIR / "content"


@pytest.fixture
def mailbox() -> Iterator[MemoryNotifier]:
    """Frischer Benachrichtigungskanal je Test (Singleton wird danach zurückgesetzt)."""
    previous = notifier.get_notifier()
    fresh = MemoryNotifier()
    notifier.set_notifier(fresh)
    yield fresh
    notifier.set_notifier(previous)


def _seeded(tmp_path: Path) -> FastAPI:
    settings = make_settings(tmp_path)
    migrate(settings)
    app = create_app(settings)
    with app.state.session_factory() as session:
        seed.provision(session, settings, app.state.registry, app.state.clock)
    return app


def _day_offset(moment: datetime, anchor: datetime) -> int:
    return (to_prague(moment).date() - to_prague(anchor).date()).days


def _actual(session: Session, anchor: datetime) -> dict[str, list[tuple[Any, ...]]]:
    result: dict[str, list[tuple[Any, ...]]] = {}
    for alert in session.scalars(select(Alert)):
        patient = session.get(Patient, alert.patient_id)
        assert patient is not None
        result.setdefault(patient.pseudonym, []).append(
            (
                _day_offset(alert.created_at, anchor),
                to_prague(alert.created_at).hour,
                alert.rule_id,
                alert.symptom_key,
                alert.attribute,
                alert.level,
            )
        )
    return result


def _check_oracle(app: FastAPI, content: Content) -> int:
    anchor = datetime.fromisoformat(content.scenario["anchor"])
    checked = 0
    with app.state.session_factory() as session:
        actual = _actual(session, anchor)
    for spec in content.scenario["patients"]:
        expected = spec.get("expected")
        if expected is None:
            continue
        found = actual.get(spec["pseudonym"], [])
        want = [
            (e["day_offset"], e["rule_id"], e["symptom_key"], e["attribute"], e["level"])
            for e in expected["alerts"]
        ]
        got = [(d, rule, s, a, lv) for d, _, rule, s, a, lv in found]
        assert sorted(got) == sorted(want), spec["pseudonym"]  # Menge EXAKT
        for e in expected["alerts"]:
            if "hour" in e:
                assert any(f[0] == e["day_offset"] and f[1] == e["hour"] for f in found)
        checked += 1
    return checked


# --- Orakel ---------------------------------------------------------------------------------


def test_oracle_fixture_scenario_matches_exactly(tmp_path: Path, mailbox: MemoryNotifier) -> None:
    content = get_content()
    assert content is not None
    app = _seeded(tmp_path)
    assert _check_oracle(app, content) == len(content.scenario["patients"])


@pytest.mark.skipif(not REAL_CONTENT.is_dir(), reason="challenge/content/ (A1) nicht vorhanden")
def test_oracle_real_scenario_matches_exactly(
    tmp_path: Path, mailbox: MemoryNotifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    content = get_content()
    assert content is not None
    app = _seeded(tmp_path)
    assert _check_oracle(app, content) >= 1


def test_seed_twice_creates_no_duplicates_and_is_deterministic(
    tmp_path: Path, mailbox: MemoryNotifier
) -> None:
    first = _seeded(tmp_path / "a")
    (tmp_path / "b").mkdir()
    second = _seeded(tmp_path / "b")

    def summary(app: FastAPI) -> list[tuple[Any, ...]]:
        with app.state.session_factory() as session:
            seed.provision(
                session, app.state.settings, app.state.registry, app.state.clock
            )  # zweiter Seed
            rows = session.scalars(select(Alert).order_by(Alert.created_at, Alert.rule_id))
            return [
                (
                    a.rule_id,
                    a.rule_version,
                    a.level,
                    a.symptom_key,
                    a.attribute,
                    a.created_at,
                    a.explanation_json["observed"],
                    a.explanation_json["params"],
                    a.explanation_json["cycle_day"],
                    len(a.explanation_json["evidence"]),
                )
                for a in rows
            ]

    one, two = summary(first), summary(second)
    assert one == two
    assert one  # nicht leer
    with first.state.session_factory() as session:
        pairs = [
            (a.patient_id, a.response_id, a.rule_id, a.symptom_key)
            for a in session.scalars(select(Alert))
        ]
    assert len(pairs) == len(set(pairs))  # keine Doppel je Antwort/Regel/Symptom


# --- Erklärung ------------------------------------------------------------------------------


def test_alert_explanation_is_complete(tmp_path: Path, mailbox: MemoryNotifier) -> None:
    app = _seeded(tmp_path)
    content = get_content()
    assert content is not None
    with app.state.session_factory() as session:
        trend = session.scalars(select(Alert).where(Alert.rule_id == "R-TRD-01")).one()
        explanation = trend.explanation_json
        assert trend.rule_version == "rules-v1"
        assert trend.status == "open"
        assert trend.notified is False  # gelb ⇒ nur Arbeitsliste
        assert explanation["kind"] == "trend"
        assert explanation["params"]["min_slope_per_day"] == 0.5
        assert explanation["observed"] == {
            "value": 2.0,
            "baseline": None,
            "delta": None,
            "slope_per_day": 0.5,
            "projected_value": 3.0,
        }
        assert explanation["baseline_window"]["to"].endswith("+02:00")
        assert explanation["cycle_day"] == 5  # Zyklusbeginn Tag -6, Alarm Tag -2
        assert explanation["evidence"][0].startswith("resp-")
        assert explanation["evidence"][1].startswith("obs-")
        assert len(explanation["evidence"]) == 4  # Antwort, aktueller Wert, zwei frühere Werte
        view = explanation_view(trend, "en")
        assert view["rationale"] == "Fixture creeping change"
        assert "rationale_i18n" not in view
        assert explanation_view(trend, "cs")["rationale"] == "Testovací plíživá změna"
        assert headline(trend, content, "en") == (
            "Nausea (severity): rising trend +0.5 per day, projected 3"
        )
        assert headline(trend, content).startswith("Nevolnost (závažnost): rostoucí trend")
        assert headline(trend, content, "de").startswith("Nausea (Schweregrad): steigender Trend")
        delta = session.scalars(select(Alert).where(Alert.rule_id == "R-DLT-01")).first()
        assert delta is not None
        assert "baseline" in headline(delta, content, "en")


def test_null_values_are_not_part_of_series(tmp_path: Path, mailbox: MemoryNotifier) -> None:
    from waechter.services.alerts import load_series

    app = _seeded(tmp_path)
    with app.state.session_factory() as session:
        patient = session.scalars(select(Patient).where(Patient.pseudonym == "SYN-0001")).one()
        last = session.scalars(
            select(Response)
            .where(Response.patient_id == patient.id)
            .order_by(Response.recorded_at.desc())
        ).first()
        assert last is not None
        series = load_series(session, last, "fever", "presence")
        assert [p.value for p in series] == [0, 0]  # der übersprungene Wert fehlt, kein Imputieren


# --- Benachrichtigung -----------------------------------------------------------------------


def test_red_alerts_notify_yellow_do_not(tmp_path: Path, mailbox: MemoryNotifier) -> None:
    app = _seeded(tmp_path)
    with app.state.session_factory() as session:
        alerts = session.scalars(select(Alert)).all()
        notes = session.scalars(select(Notification)).all()
        red = [a for a in alerts if a.level == "red"]
        assert red
        assert {n.alert_id for n in notes} == {a.id for a in red}
        assert all(a.notified == (a.level == "red") for a in alerts)
        for note in notes:
            assert note.channel == "in_app"
            assert note.text.startswith("SYN-000")  # nur Pseudonym (G-17)
            assert "Test" not in note.text  # kein Anzeigename
    assert len(mailbox.sent) == len(red)
    assert all(notice.kind == "alert.red" for _, notice in mailbox.sent)


# --- Live: Rauschbremse und Safety ----------------------------------------------------------


def _post(client: TestClient, answers: list[tuple[str, str, int]]) -> dict[str, Any]:
    payload = {
        "client_submission_id": str(uuid.uuid4()),
        "questionnaire_id": QID,
        "answers": [{"symptom_key": s, "attribute": a, "value": v} for s, a, v in answers],
    }
    response = client.post(RESPONSES, json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _alerts(app: FastAPI, patient: str, rule: str) -> list[Alert]:
    with app.state.session_factory() as session:
        pid = session.scalars(select(Patient.id).where(Patient.pseudonym == patient)).one()
        return list(
            session.scalars(
                select(Alert)
                .where(Alert.patient_id == pid, Alert.rule_id == rule)
                .order_by(Alert.created_at, Alert.id)
            )
        )


@pytest.fixture
def live(tmp_path: Path, mailbox: MemoryNotifier) -> tuple[FastAPI, TestClient]:
    app = _seeded(tmp_path)
    client = TestClient(app, headers={"X-Requested-With": "fetch"})
    login(client, "patient2")  # SYN-0002
    return app, client


def test_live_submission_creates_red_alert_and_neutral_receipt(
    live: tuple[FastAPI, TestClient], mailbox: MemoryNotifier
) -> None:
    app, client = live
    before = len(mailbox.sent)
    receipt = _post(client, [("fever", "presence", 1)])
    assert set(receipt) == {"response_id", "recorded_at", "answered", "skipped", "message_key"}
    (alert,) = _alerts(app, "SYN-0002", "R-URG-01")
    assert (alert.level, alert.notified, alert.response_id) == ("red", True, receipt["response_id"])
    assert alert.created_at == FROZEN_NOW
    assert len(mailbox.sent) == before + 1


def test_repeat_within_open_alert_is_deduplicated(live: tuple[FastAPI, TestClient]) -> None:
    app, client = live
    _post(client, [("fever", "presence", 1)])
    _post(client, [("fever", "presence", 1)])  # gleicher Wert, Meldung noch offen ⇒ keine zweite
    assert len(_alerts(app, "SYN-0002", "R-URG-01")) == 1


def test_worsening_breaks_through_dedupe_even_when_acknowledged(
    live: tuple[FastAPI, TestClient],
) -> None:
    app, client = live
    _post(client, [("nausea", "severity", 3)])
    (first,) = _alerts(app, "SYN-0002", "R-SEV-01")
    with app.state.session_factory() as session:  # Ärztin hat quittiert (vor 1 h)
        stored = session.get(Alert, first.id)
        assert stored is not None
        stored.status = "acknowledged"
        session.add(
            AlertAction(
                alert_id=first.id,
                action="acknowledge",
                decision="other",
                at=FROZEN_NOW - timedelta(hours=1),
            )
        )
        session.commit()
    _post(client, [("nausea", "severity", 3)])  # gleicher Wert im Cooldown ⇒ gehalten
    assert len(_alerts(app, "SYN-0002", "R-SEV-01")) == 1
    _post(client, [("nausea", "severity", 4)])  # Verschlechterung ⇒ durch (G-02)
    assert len(_alerts(app, "SYN-0002", "R-SEV-01")) == 2


def test_cooldown_expires(live: tuple[FastAPI, TestClient]) -> None:
    app, client = live
    _post(client, [("fever", "presence", 1)])
    (first,) = _alerts(app, "SYN-0002", "R-URG-01")
    with app.state.session_factory() as session:
        stored = session.get(Alert, first.id)
        assert stored is not None
        stored.status = "acknowledged"
        session.add(
            AlertAction(
                alert_id=first.id,
                action="acknowledge",
                decision="other",
                at=FROZEN_NOW - timedelta(hours=25),  # cooldown_hours = 24 ist vorbei
            )
        )
        session.commit()
    _post(client, [("fever", "presence", 1)])
    assert len(_alerts(app, "SYN-0002", "R-URG-01")) == 2


def test_disabled_rule_does_not_fire(live: tuple[FastAPI, TestClient]) -> None:
    app, client = live
    from waechter.models import ConfigVersion

    with app.state.session_factory() as session:
        row = session.scalars(select(ConfigVersion).where(ConfigVersion.kind == "rules")).one()
        body = dict(row.body_json)
        body["rules"] = [{**r, "enabled": r["id"] != "R-URG-01"} for r in body["rules"]]
        row.body_json = body
        session.commit()
    _post(client, [("fever", "presence", 1)])
    assert _alerts(app, "SYN-0002", "R-URG-01") == []


def test_rule_version_comes_from_active_config(live: tuple[FastAPI, TestClient]) -> None:
    app, client = live
    from waechter.models import ConfigVersion

    with app.state.session_factory() as session:
        row = session.scalars(select(ConfigVersion).where(ConfigVersion.kind == "rules")).one()
        row.body_json = {**row.body_json, "version": "rules-v9"}
        session.commit()
    _post(client, [("fever", "presence", 1)])
    (alert,) = _alerts(app, "SYN-0002", "R-URG-01")
    assert alert.rule_version == "rules-v9"


def test_missing_rule_is_not_evaluated_here(live: tuple[FastAPI, TestClient]) -> None:
    app, client = live
    _post(client, [("nausea", "severity", 0)])
    with app.state.session_factory() as session:
        assert not session.scalars(select(Alert).where(Alert.rule_id == "R-MIS-01")).all()


class StepClock:
    """Uhr, die der Test vorstellt (Entwarnung braucht verschiedene Zeitpunkte)."""

    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


def test_all_clear_ends_the_episode_and_a_relapse_alerts_again(
    live: tuple[FastAPI, TestClient],
) -> None:
    """DR-012: Entwarnung unter der Schwelle beendet die Episode, der Rückfall meldet sofort neu."""
    app, client = live
    clock = StepClock(FROZEN_NOW)
    app.state.clock = clock
    _post(client, [("nausea", "severity", 3)])  # Meldung A (offen)
    clock.instant += timedelta(hours=1)
    _post(client, [("nausea", "severity", 3)])  # gleicher Wert, keine Entwarnung ⇒ gehalten
    assert len(_alerts(app, "SYN-0002", "R-SEV-01")) == 1
    clock.instant += timedelta(hours=1)
    _post(client, [("nausea", "severity", 1)])  # Entwarnung (unter 3)
    clock.instant += timedelta(hours=1)
    _post(client, [("nausea", "severity", 3)])  # Rückfall ⇒ sofort neue Meldung
    after = _alerts(app, "SYN-0002", "R-SEV-01")
    assert [a.status for a in after] == ["open", "open"]  # die alte bleibt offen
    clock.instant += timedelta(hours=1)
    _post(client, [("nausea", "severity", 3)])  # neue Episode läuft, wieder gehalten
    assert len(_alerts(app, "SYN-0002", "R-SEV-01")) == 2


def test_a_low_value_at_the_same_instant_is_not_an_all_clear(
    live: tuple[FastAPI, TestClient],
) -> None:
    app, client = live
    _post(client, [("nausea", "severity", 3)])
    _post(client, [("nausea", "severity", 1)])  # derselbe (eingefrorene) Zeitpunkt
    _post(client, [("nausea", "severity", 3)])
    assert len(_alerts(app, "SYN-0002", "R-SEV-01")) == 1


def test_headline_uses_localized_attribute_labels_never_the_key() -> None:
    from waechter.services.alerts import _subject

    assert _subject("Průjem", "severity", "cs") == "Průjem (závažnost)"
    assert _subject("Diarrhea", "severity", "en") == "Diarrhea (severity)"
    assert _subject("Durchfall", "severity", "de") == "Durchfall (Schweregrad)"
    assert _subject("Nausea", "frequency", "de") == "Nausea (Häufigkeit)"
    assert _subject("Nausea", "interference", "fr") == "Nausea (interference with daily activities)"
    assert _subject("Horečka", "presence", "cs") == "Horečka"  # ja/nein: Attribut weglassen
    assert _subject("Horečka", None, "cs") == "Horečka"
    assert _subject("Horečka", "unbekannt", "en") == "Horečka"
