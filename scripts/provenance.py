"""Herkunftstabelle aus der Git-Historie (nur Standardbibliothek).

Je Datei: erste Änderung (Commit), Zeitpunkt, Zone (platform | challenge | sonstige), Klasse
(pre-event | during-event) und bei Umbenennungen der Ursprungspfad. Grenze: Tag `pre-rakathon`,
sonst 2026-10-16T12:00+02:00 (Committer-Zeitpunkt). Zusätzlich:

- Commits mit Betreff `platform-fix: ...`;
- alle Commits **nach der Grenze**, die die Zone `platform` berühren, markiert mit
  „ohne platform-fix:“, wenn der Betreff das Präfix nicht trägt (stille Plattformänderung).

Aufruf: python scripts/provenance.py [--repo .] [--out provenance/TABLE.md]
Dateinamen werden unquotiert gelesen (`core.quotepath=false`); Namen mit Tab oder Zeilenumbruch
werden nicht unterstützt.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

CUTOFF = datetime(2026, 10, 16, 12, 0, tzinfo=timezone(timedelta(hours=2)))
TAG = "pre-rakathon"
FIX_PREFIX = "platform-fix:"
PLATFORM_PREFIXES = ("platform/", "tests/", "scripts/", ".github/")
SEP = "\x1f"


@dataclass(frozen=True)
class Row:
    path: str
    commit: str
    when: datetime
    zone: str
    klass: str
    origin: str = ""


@dataclass(frozen=True)
class LateChange:
    commit: str
    when: datetime
    subject: str
    paths: tuple[str, ...]
    marked: bool  # True = trägt das Präfix `platform-fix:`


@dataclass
class _Commit:
    sha: str
    when: datetime
    subject: str
    changes: list[tuple[str, str, str]] = field(default_factory=list)  # (Status, alt, neu)


def _run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [
        "git",
        "-c",
        f"safe.directory={repo.resolve().as_posix()}",
        "-c",
        "core.quotepath=false",
        *args,
    ]
    return subprocess.run(  # noqa: S603 - feste Argumentliste, kein Shell
        command, cwd=repo, check=check, capture_output=True, text=True, encoding="utf-8"
    )


def _git(repo: Path, *args: str) -> str:
    return _run(repo, *args).stdout


def zone_of(path: str) -> str:
    if path.startswith("challenge/"):
        return "challenge"
    if "/" not in path or path.startswith(PLATFORM_PREFIXES):
        return "platform"
    return "sonstige"


def _tag_exists(repo: Path) -> bool:
    return bool(_git(repo, "tag", "--list", TAG).strip())


def _is_pre_event(repo: Path, commit: str, when: datetime, use_tag: bool) -> bool:
    if use_tag:
        return _run(repo, "merge-base", "--is-ancestor", commit, TAG, check=False).returncode == 0
    return when < CUTOFF


def _commits(repo: Path) -> list[_Commit]:
    log = _git(repo, "log", "--reverse", "-M", f"--format=%x00%H{SEP}%cI{SEP}%s", "--name-status")
    commits: list[_Commit] = []
    for block in log.split("\x00")[1:]:
        header, _, body = block.partition("\n")
        sha, iso, subject = header.split(SEP, 2)
        commit = _Commit(sha, datetime.fromisoformat(iso), subject)
        for line in body.splitlines():
            parts = line.split("\t")
            if len(parts) < 2 or not parts[0]:
                continue
            status = parts[0][0]
            if status in "RC" and len(parts) >= 3:
                commit.changes.append((status, parts[1], parts[2]))
            else:
                commit.changes.append((status, parts[1], parts[1]))
        commits.append(commit)
    return commits


def collect(repo: Path) -> tuple[list[Row], list[tuple[str, str]], list[LateChange]]:
    """Dateizeilen (nach Pfad sortiert), `platform-fix:`-Commits und späte Plattformänderungen."""
    use_tag = _tag_exists(repo)
    first: dict[str, tuple[str, datetime, str]] = {}  # Pfad -> (Commit, Zeit, Ursprungspfad)
    fixes: list[tuple[str, str]] = []
    late: list[LateChange] = []
    for commit in _commits(repo):
        if commit.subject.startswith(FIX_PREFIX):
            fixes.append((commit.sha[:10], commit.subject))
        pre = _is_pre_event(repo, commit.sha, commit.when, use_tag)
        touched: list[str] = []
        for status, old, new in commit.changes:
            if status in "RC":
                # Umbenennung/Kopie: erste Änderung und Herkunft des alten Pfads übernehmen
                inherited = first.get(old)
                if new not in first:
                    first[new] = (
                        (inherited[0], inherited[1], inherited[2] or old)
                        if inherited
                        else (commit.sha, commit.when, old)
                    )
                touched += [old, new]
            else:
                first.setdefault(new, (commit.sha, commit.when, ""))
                touched.append(new)
        platform_paths = tuple(sorted({p for p in touched if zone_of(p) == "platform"}))
        if platform_paths and not pre:
            marked = commit.subject.startswith(FIX_PREFIX)
            late.append(
                LateChange(commit.sha[:10], commit.when, commit.subject, platform_paths, marked)
            )
    tracked = set(_git(repo, "ls-files").splitlines())
    rows = []
    for path, (sha, when, origin) in sorted(first.items()):
        if path not in tracked:
            continue
        klass = "pre-event" if _is_pre_event(repo, sha, when, use_tag) else "during-event"
        rows.append(Row(path, sha[:10], when, zone_of(path), klass, origin))
    return rows, fixes, late


def commits_after_boundary(repo: Path) -> int:
    """Anzahl aller Commits nach der Grenze (Tag-Vorfahrenbeziehung bzw. Zeitpunkt), alle Zonen."""
    use_tag = _tag_exists(repo)
    return sum(1 for c in _commits(repo) if not _is_pre_event(repo, c.sha, c.when, use_tag))


def render(
    rows: list[Row],
    fixes: list[tuple[str, str]],
    late: list[LateChange] | None = None,
    commits_after: int | None = None,
) -> str:
    late_lines = [
        f"- {c.commit} {c.when.isoformat()} {c.subject} ({', '.join(c.paths)})"
        f"{'' if c.marked else ' - ohne platform-fix:'}"
        for c in late or []
    ]
    totals: dict[tuple[str, str], int] = {}
    for r in rows:
        totals[(r.zone, r.klass)] = totals.get((r.zone, r.klass), 0) + 1
    sums = [f"| {zone} | {klass} | {n} |" for (zone, klass), n in sorted(totals.items())]
    unmarked = sum(1 for c in late or [] if not c.marked)
    lines = [
        "## Summen (aus der Tabelle unten)",
        "",
        "| Zone | Klasse | Dateien |",
        "|---|---|---|",
        *sums,
        "",
        f"Dateien gesamt: {len(rows)}",
        *(
            [
                f"Commits nach der Grenze: {commits_after} "
                f"(davon berühren platform: {len(late or [])}, ohne platform-fix: {unmarked})"
            ]
            if commits_after is not None
            else []
        ),
        "",
        "## Dateien",
        "",
        "| Datei | Erste Änderung | Zeitpunkt | Zone | Klasse | Ursprungspfad |",
        "|---|---|---|---|---|---|",
        *(
            f"| {r.path} | {r.commit} | {r.when.isoformat()} | {r.zone} | {r.klass} | {r.origin} |"
            for r in rows
        ),
        "",
        "## platform-fix-Commits",
        "",
        *([f"- {commit} {subject}" for commit, subject in fixes] or ["- (keine)"]),
        "",
        "## Commits nach der Grenze, die die Zone platform berühren",
        "",
        *(late_lines or ["- (keine)"]),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    rows, fixes, late = collect(args.repo)
    text = render(rows, fixes, late, commits_after_boundary(args.repo))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
