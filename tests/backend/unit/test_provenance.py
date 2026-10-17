"""Test von scripts/provenance.py gegen ein Wegwerf-Repository mit festen Commit-Zeiten."""

import importlib.util
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "provenance.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("provenance", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str, when: str | None = None) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}
    if when:
        env |= {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(  # noqa: S603
        ["git", "-c", f"safe.directory={repo.as_posix()}", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        env=env,
    )


def _commit(repo: Path, files: dict[str, str], message: str, when: str) -> None:
    for name, text in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message, when=when)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(
        tmp_path,
        {"platform/backend/a.py": "1", "README.md": "x"},
        "Basis",
        "2026-10-15T10:00:00+02:00",
    )
    _commit(
        tmp_path,
        {"challenge/feature.py": "1"},
        "Challenge-Start",
        "2026-10-16T13:00:00+02:00",
    )
    _commit(
        tmp_path,
        {"platform/backend/a.py": "2", "docs/extra.md": "y"},
        "platform-fix: Fehler im Kern",
        "2026-10-16T14:00:00+02:00",
    )
    return tmp_path


def test_zone_rules() -> None:
    zone_of = _load().zone_of
    assert zone_of("challenge/x.py") == "challenge"
    assert zone_of("platform/frontend/a.ts") == "platform"
    assert zone_of("tests/backend/t.py") == "platform"
    assert zone_of("package.json") == "platform"
    assert zone_of("docs/EXTENDING.md") == "sonstige"


def test_first_change_zone_class_and_fixes_without_tag(repo: Path) -> None:
    rows, fixes, _ = _load().collect(repo)
    by_path = {r.path: r for r in rows}
    assert by_path["platform/backend/a.py"].klass == "pre-event"  # erste Änderung zählt
    assert by_path["README.md"].zone == "platform"
    assert by_path["challenge/feature.py"].klass == "during-event"
    assert by_path["challenge/feature.py"].zone == "challenge"
    assert by_path["docs/extra.md"].zone == "sonstige"
    assert [subject for _, subject in fixes] == ["platform-fix: Fehler im Kern"]


def test_tag_defines_the_boundary_when_present(repo: Path) -> None:
    _git(repo, "tag", "pre-rakathon", "HEAD~1")  # Tag nach Commit 2: Commit 3 ist during-event
    rows, _, _ = _load().collect(repo)
    by_path = {r.path: r for r in rows}
    assert by_path["challenge/feature.py"].klass == "pre-event"  # vor dem Tag, trotz Zeitpunkt
    assert by_path["docs/extra.md"].klass == "during-event"


def test_render_lists_table_fixes_and_late_changes(repo: Path) -> None:
    module = _load()
    rows, fixes, late = module.collect(repo)
    text = module.render(rows, fixes, late)
    assert "| Datei | Erste Änderung | Zeitpunkt | Zone | Klasse | Ursprungspfad |" in text
    assert "platform-fix: Fehler im Kern" in text
    assert text.count("\n| ") >= 4
    assert "## Commits nach der Grenze, die die Zone platform berühren" in text


def test_non_ascii_paths_keep_their_zone_and_are_readable(repo: Path) -> None:
    _commit(
        repo, {"challenge/Přehled_Übersicht.py": "1"}, "Tschechisch", "2026-10-16T15:00:00+02:00"
    )
    rows, _, _ = _load().collect(repo)
    by_path = {r.path: r for r in rows}
    row = by_path["challenge/Přehled_Übersicht.py"]  # unquotiert lesbar
    assert row.zone == "challenge"
    assert row.klass == "during-event"


def test_rename_keeps_first_change_and_origin_of_the_old_path(repo: Path) -> None:
    body = "\n".join(f"zeile {i}" for i in range(40))
    _commit(repo, {"platform/backend/groß.py": body}, "Datei", "2026-10-15T11:00:00+02:00")
    _git(repo, "mv", "platform/backend/groß.py", "platform/backend/neu.py", when=None)
    _git(repo, "commit", "-m", "Umbenennung", when="2026-10-16T16:00:00+02:00")
    rows, _, _ = _load().collect(repo)
    by_path = {r.path: r for r in rows}
    renamed = by_path["platform/backend/neu.py"]
    assert renamed.klass == "pre-event"  # erste Änderung war vor der Grenze
    assert renamed.origin == "platform/backend/groß.py"
    assert "platform/backend/groß.py" not in by_path  # nicht mehr getrackt


def test_silent_platform_changes_after_the_boundary_are_listed_and_marked(repo: Path) -> None:
    _commit(repo, {"platform/backend/a.py": "3"}, "still geändert", "2026-10-16T17:00:00+02:00")
    _commit(repo, {"challenge/x.py": "1"}, "nur challenge", "2026-10-16T18:00:00+02:00")
    module = _load()
    rows, fixes, late = module.collect(repo)
    by_subject = {c.subject: c for c in late}
    assert by_subject["still geändert"].marked is False
    assert by_subject["platform-fix: Fehler im Kern"].marked is True
    assert "nur challenge" not in by_subject  # berührt platform/ nicht
    assert "Challenge-Start" not in by_subject
    text = module.render(rows, fixes, late)
    assert "still geändert (platform/backend/a.py) - ohne platform-fix:" in text


def test_totals_per_zone_and_class_and_commits_after_the_boundary(repo: Path) -> None:
    _commit(repo, {"platform/backend/a.py": "3"}, "still geändert", "2026-10-16T17:00:00+02:00")
    module = _load()
    rows, fixes, late = module.collect(repo)
    text = module.render(rows, fixes, late, module.commits_after_boundary(repo))
    assert "## Summen (aus der Tabelle unten)" in text
    assert "| platform | pre-event | 2 |" in text  # a.py, README.md
    assert "| challenge | during-event | 1 |" in text
    assert "| sonstige | during-event | 1 |" in text  # docs/extra.md
    assert "Dateien gesamt: 4" in text
    # drei Commits nach der Grenze: Challenge-Start, platform-fix, still geändert
    assert "Commits nach der Grenze: 3 (davon berühren platform: 2, ohne platform-fix: 1)" in text
    assert module.commits_after_boundary(repo) == 3
