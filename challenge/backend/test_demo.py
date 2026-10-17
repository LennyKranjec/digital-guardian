"""Demo-Reset (T-10): Kernstück von challenge/demo/reset.ps1|sh gegen eine Temp-DB.

Die Skripte selbst (PowerShell/Bash) setzen nur Umgebungsvariablen und rufen `waechter.demo.main()`.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.core.settings import Settings
from conftest import CHALLENGE_DIR, FROZEN_NOW
from waechter.constants import CONTENT_DIR_ENV
from waechter.demo import (
    DEMO_ANCHOR,
    DemoResetError,
    demo_db_path,
    demo_settings,
    main,
    reset_demo,
)

REAL_CONTENT = CHALLENGE_DIR / "content"


def settings_for(directory: Path, name: str = "demo.db") -> Settings:
    data = directory / "data"
    data.mkdir(parents=True, exist_ok=True)
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(data / name).as_posix()}",
        challenge_dir=CHALLENGE_DIR,
        app_frozen_now=FROZEN_NOW,
    )


def table_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(path)) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' and name like 'wa_%' order by 1"
            )
        ]
        return {n: connection.execute(f"select count(*) from {n}").fetchone()[0] for n in names}  # noqa: S608


def test_reset_creates_a_checked_demo_database(tmp_path: Path) -> None:
    report = reset_demo(settings_for(tmp_path))
    assert report.ok, report.render()
    assert report.database == tmp_path / "data" / "demo.db"
    assert report.database.is_file()
    names = [c.name for c in report.checks]
    assert "Demo-Konten (admin, doctor, patient, patient2, patient6)" in names
    assert any(n.startswith("Patientinnen = ") for n in names)
    assert any(n.startswith("Ampel SYN-0001 = ") for n in names)
    assert "SYN-0001 hat eine Kurzfassung" in names
    text = report.render()
    assert "Demo bereit." in text
    assert "SYN-0001:" in text


def test_reset_restores_the_initial_state_after_changes(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    first = reset_demo(settings)
    path = first.database
    baseline = table_counts(path)
    with closing(sqlite3.connect(path)) as connection:  # Demo "verbrauchen": löschen und ändern
        connection.execute("pragma foreign_keys=off")
        connection.execute("delete from wa_alerts")
        connection.execute("delete from wa_answers")
        connection.execute("update wa_patients set display_name='verändert'")
        connection.commit()
    assert table_counts(path) != baseline
    second = reset_demo(settings)
    assert second.ok, second.render()
    assert (
        table_counts(path) == baseline
    )  # reproduzierbar: gleiche Zeilenzahlen wie beim ersten Mal


def test_reset_deletes_only_the_demo_database(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    neighbour = tmp_path / "data" / "app.db"
    neighbour.write_bytes(b"not touched")
    other = tmp_path / "keep.txt"
    other.write_text("keep", encoding="utf-8")
    reset_demo(settings)
    assert neighbour.read_bytes() == b"not touched"
    assert other.read_text(encoding="utf-8") == "keep"


def test_reset_removes_stale_sidecar_files(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    base = tmp_path / "data" / "demo.db"
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(f"{base}{suffix}").write_bytes(b"stale")
    report = reset_demo(settings)
    assert report.ok, report.render()
    assert not Path(f"{base}-wal").exists()
    assert not Path(f"{base}-journal").exists()


@pytest.mark.parametrize(
    ("url", "needle"),
    [
        ("sqlite:///{tmp}/data/app.db", "app.db"),  # andere Datei im Datenordner
        ("sqlite:///{tmp}/elsewhere/demo.db", "demo.db"),  # richtiger Name, falscher Ordner
        ("sqlite:///{tmp}/demo.db", "demo.db"),
        ("sqlite:///:memory:", "SQLite file"),
        ("postgresql://user@host/db", "SQLite file"),
    ],
)
def test_reset_refuses_everything_but_the_demo_database(
    tmp_path: Path, url: str, needle: str
) -> None:
    target = tmp_path / "data" / "app.db"
    target.parent.mkdir()
    target.write_bytes(b"precious")
    settings = Settings(
        _env_file=None,
        database_url=url.format(tmp=tmp_path.as_posix()),
        challenge_dir=CHALLENGE_DIR,
        app_frozen_now=FROZEN_NOW,
    )
    with pytest.raises(DemoResetError, match=needle):
        reset_demo(settings)
    assert target.read_bytes() == b"precious"


def test_demo_path_must_end_in_data_demo_db(tmp_path: Path) -> None:
    assert demo_db_path(settings_for(tmp_path)) == tmp_path / "data" / "demo.db"
    with pytest.raises(DemoResetError):
        demo_db_path(settings_for(tmp_path, name="demo2.db"))


def test_demo_settings_force_demo_mode_and_default_to_the_anchor() -> None:
    plain = Settings(_env_file=None, demo_mode=False, app_frozen_now=None)
    forced = demo_settings(plain)
    assert forced.demo_mode is True
    assert forced.app_frozen_now is not None
    assert forced.app_frozen_now.isoformat() == DEMO_ANCHOR
    kept = demo_settings(Settings(_env_file=None, app_frozen_now=FROZEN_NOW))
    assert kept.app_frozen_now == FROZEN_NOW


def test_check_fails_when_the_clock_is_not_the_scenario_anchor(tmp_path: Path) -> None:
    other = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'data' / 'demo.db').as_posix()}",
        challenge_dir=CHALLENGE_DIR,
        app_frozen_now=FROZEN_NOW.replace(day=20),
    )
    report = reset_demo(other)
    assert not report.ok  # Ampeln gelten nur zur Ankerzeit
    assert any(c.name.startswith("Uhr") and not c.ok for c in report.checks)
    assert "NICHT bereit" in report.render()


def test_main_reads_the_environment_and_reports_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(data / 'demo.db').as_posix()}")
    monkeypatch.setenv("APP_FROZEN_NOW", DEMO_ANCHOR)
    monkeypatch.setenv("CHALLENGE_DIR", str(CHALLENGE_DIR))
    assert main() == 0
    assert "Demo bereit." in capsys.readouterr().out
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(data / 'app.db').as_posix()}")
    assert main() == 2
    assert "Reset abgelehnt" in capsys.readouterr().err


@pytest.mark.skipif(not REAL_CONTENT.is_dir(), reason="challenge/content/ (A1) nicht vorhanden")
def test_reset_with_the_real_scenario_matches_all_expected_lights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL_CONTENT))
    settings = settings_for(tmp_path).model_copy(
        update={"app_frozen_now": demo_settings(Settings(_env_file=None)).app_frozen_now}
    )
    report = reset_demo(settings)
    assert report.ok, report.render()
    lights = [c for c in report.checks if c.name.startswith("Ampel ")]
    assert len(lights) >= 5
    assert all(c.ok for c in lights)
