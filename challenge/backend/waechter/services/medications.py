"""Arzneimittelsuche für die Ärztin (Vertrag v2.3, `triage.md` §8): Identifikation, nie Regel.

Reine Auswertung des Katalogs `medications.yaml` (Name, Wirkstoff cs/en, Handelsname, Synonyme,
kódSÚKL, ATC). Die Suche bestimmt keine Fragen, Ampel oder Regeln. Audit `medication_search` ohne
Suchtext (nur Art und Trefferzahl).

Normalisierung: trimmen, klein, ohne Diakritik (Unicode-NFKD). Art der Suche:
- nur Ziffern ⇒ kódSÚKL: auf 7 Stellen mit führenden Nullen aufgefüllt, exakt vor Präfix;
- Buchstabe + zwei Ziffern (+ Buchstaben/Ziffern) ⇒ ATC-Präfix;
- sonst Name: Anfang des Namens vor Anfang eines Teilworts vor Zeichenfolge im Wort (ab 3 Zeichen).

T-33: Liefert der kuratierte Katalog weniger als 10 Treffer, wird zusätzlich der SÚKL-Index
(`sukl_index.csv`, Open Data DLP, gebaut von `content/tools/build_sukl_index.py`) durchsucht:
gleiche Art der Suche, beim Namen nur Namensanfang/Wortanfang. Diese Treffer tragen
`status: "sukl_only"` (ID `SUKL-<kód>`, ohne Regime, SPC oder Nebenwirkungsprofil) und stehen immer
hinter den kuratierten; insgesamt höchstens 25 Treffer.
"""

import csv
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import ApiError, FieldError
from app.services.access import not_found
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content, content_dir
from waechter.models import Therapy
from waechter.services.questionnaire import localize

MIN_QUERY: Final = 2
MAX_RESULTS: Final = 20
SUKL_FALLBACK_BELOW: Final = 10
MAX_WITH_SUKL: Final = 25
SUKL_INDEX_FILE: Final = "sukl_index.csv"
SUKL_ID_PREFIX: Final = "SUKL-"
SUKL_ONLY: Final = "sukl_only"
SUKL_LENGTH: Final = 7
SUBSTRING_MIN: Final = 3
_ATC = re.compile(r"^[a-z][0-9]{2}(?:[a-z]{1,2}(?:[0-9]{1,2})?)?$")
_WORDS = re.compile(r"[^\W_]+")

Match = Literal["sukl_code", "atc", "name", "synonym", "id"]
Kind = Literal["sukl", "atc", "name"]


@dataclass(frozen=True)
class Hit:
    medication: dict[str, Any]
    match: Match
    rank: int


def normalize(text: str) -> str:
    """Trimmen, klein, ohne Diakritik; mehrfache Leerzeichen werden zu einem."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.split())


def classify(query: str) -> Kind:
    """Art der (normalisierten) Suche."""
    if query.isascii() and query.isdigit():
        return "sukl"
    if _ATC.match(query):
        return "atc"
    return "name"


def _name_rank(query: str, candidate: str) -> int | None:
    """0 = Anfang des Namens, 1 = Anfang eines Teilworts, 2 = Zeichenfolge im Wort, sonst `None`."""
    text = normalize(candidate)
    if text.startswith(query):
        return 0
    if any(word.startswith(query) for word in _WORDS.findall(text)):
        return 1
    if len(query) >= SUBSTRING_MIN and query in text:
        return 2
    return None


def _by_sukl(query: str, medications: list[dict[str, Any]]) -> list[Hit]:
    padded = query.zfill(SUKL_LENGTH)
    exact = [m for m in medications if m.get("sukl_code") == padded]
    if exact:
        return [Hit(m, "sukl_code", 0) for m in exact]
    return [
        Hit(m, "sukl_code", 1)
        for m in medications
        if m.get("sukl_code") and m["sukl_code"].startswith(query)
    ]


def _by_atc(query: str, medications: list[dict[str, Any]]) -> list[Hit]:
    return [
        Hit(m, "atc", 0 if m["atc"].lower() == query else 1)
        for m in medications
        if m["atc"].lower().startswith(query)
    ]


def _by_name(query: str, medications: list[dict[str, Any]]) -> list[Hit]:
    hits: list[Hit] = []
    for med in medications:
        names = [*med["inn"].values(), *([med["trade_name"]] if med.get("trade_name") else [])]
        ranks = [r for r in (_name_rank(query, n) for n in names) if r is not None]
        if ranks:
            hits.append(Hit(med, "name", min(ranks)))
            continue
        synonym_ranks = [
            r for r in (_name_rank(query, s) for s in med.get("synonyms", [])) if r is not None
        ]
        if synonym_ranks:
            hits.append(Hit(med, "synonym", min(synonym_ranks)))
    return hits


def search(content: Content, raw_query: str) -> tuple[Kind, list[Hit]]:
    """Treffer (höchstens 20), sortiert: exakte Nummer > Namensanfang > Teilwort; dann nach ID."""
    query = normalize(raw_query)
    if len(query) < MIN_QUERY:
        raise ApiError(
            422,
            "validation_failed",
            "Query too short",
            [FieldError(field="q", code="too_short", message="At least 2 characters")],
        )
    if content.medications is None:
        return classify(query), []
    medications: list[dict[str, Any]] = content.medications["medications"]
    kind = classify(query)
    finder = {"sukl": _by_sukl, "atc": _by_atc, "name": _by_name}[kind]
    hits = sorted(finder(query, medications), key=lambda h: (h.rank, h.medication["id"]))
    return kind, hits[:MAX_RESULTS]


@dataclass(frozen=True)
class SuklEntry:
    sukl_code: str
    name: str
    strength: str
    package: str
    atc: str
    form: str
    holder: str
    norm_name: str
    words: tuple[str, ...]


@dataclass(frozen=True)
class SuklHit:
    entry: SuklEntry
    match: Match
    rank: int


@lru_cache(maxsize=4)
def _load_sukl_index(path: Path) -> tuple[SuklEntry, ...]:
    """Index einmal pro Prozess (und Pfad) laden; fehlt die Datei, ist der Index leer."""
    if not path.is_file():
        return ()
    entries: list[SuklEntry] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            name = normalize(row["name"])
            entries.append(
                SuklEntry(
                    sukl_code=row["sukl_code"],
                    name=row["name"],
                    strength=row["strength"],
                    package=row["package"],
                    atc=row["atc"],
                    form=row["form"],
                    holder=row.get("holder") or "",
                    norm_name=name,
                    words=tuple(_WORDS.findall(name)),
                )
            )
    return tuple(entries)


def sukl_index() -> tuple[SuklEntry, ...]:
    return _load_sukl_index((content_dir() / SUKL_INDEX_FILE).resolve())


def _sukl_find(kind: Kind, query: str, index: tuple[SuklEntry, ...]) -> list[SuklHit]:
    if kind == "sukl":
        padded = query.zfill(SUKL_LENGTH)
        exact = [SuklHit(e, "sukl_code", 0) for e in index if e.sukl_code == padded]
        return exact or [SuklHit(e, "sukl_code", 1) for e in index if e.sukl_code.startswith(query)]
    if kind == "atc":
        return [
            SuklHit(e, "atc", 0 if e.atc.lower() == query else 1)
            for e in index
            if e.atc and e.atc.lower().startswith(query)
        ]
    hits: list[SuklHit] = []
    for e in index:
        if e.norm_name.startswith(query):
            hits.append(SuklHit(e, "name", 0))
        elif any(word.startswith(query) for word in e.words):
            hits.append(SuklHit(e, "name", 1))
    return hits


def search_with_sukl(content: Content, raw_query: str) -> tuple[Kind, list[Hit], list[SuklHit]]:
    """Kuratierte Treffer (unverändert) und, bei weniger als 10, ergänzende SÚKL-Treffer.

    SÚKL-Treffer: ohne kódSÚKL, die schon kuratiert gefunden wurden; sortiert nach (Rang, Name,
    kódSÚKL); zusammen mit den kuratierten höchstens 25.
    """
    kind, hits = search(content, raw_query)
    if len(hits) >= SUKL_FALLBACK_BELOW:
        return kind, hits, []
    curated_codes = {h.medication.get("sukl_code") for h in hits}
    extra = [
        h
        for h in _sukl_find(kind, normalize(raw_query), sukl_index())
        if h.entry.sukl_code not in curated_codes
    ]
    extra.sort(key=lambda h: (h.rank, h.entry.norm_name, h.entry.sukl_code))
    return kind, hits, extra[: MAX_WITH_SUKL - len(hits)]


def sukl_view(entry: SuklEntry, match: Match) -> dict[str, Any]:
    """Antwortobjekt `Medication` für einen reinen SÚKL-Treffer: Basisdaten, kein Therapieprofil."""
    return {
        "medication_id": f"{SUKL_ID_PREFIX}{entry.sukl_code}",
        "inn": entry.name,
        "trade_name": entry.name,
        "sukl_code": entry.sukl_code,
        "atc": entry.atc,
        "status": SUKL_ONLY,
        "regimens": [],
        "spc": None,
        "match": match,
        "patients_on_regimen": 0,
        "sukl": {
            "name": entry.name,
            "strength": entry.strength,
            "package": entry.package,
            "form": entry.form,
            "holder": entry.holder or None,
        },
    }


def _sukl_entry(medication_id: str) -> SuklEntry | None:
    """`SUKL-<7 Ziffern>` ⇒ Eintrag des SÚKL-Index, sonst `None`."""
    code = medication_id.removeprefix(SUKL_ID_PREFIX)
    if code == medication_id or len(code) != SUKL_LENGTH or not (code.isascii() and code.isdigit()):
        return None
    return next((e for e in sukl_index() if e.sukl_code == code), None)


def _patients_on(session: Session, regimen_ids: set[str]) -> int:
    """Anzahl (synthetischer) Patient:innen, deren aktuelle Therapie eines dieser Regime ist."""
    latest: dict[str, tuple[Any, str]] = {}
    for therapy in session.scalars(select(Therapy).order_by(Therapy.cycle_start, Therapy.id)):
        latest[therapy.patient_id] = (therapy.cycle_start, therapy.regimen_id)
    return sum(1 for _, regimen in latest.values() if regimen in regimen_ids)


def _spc(content: Content, source_id: str | None) -> dict[str, str] | None:
    if source_id is None:
        return None
    for regimen in content.regimens["regimens"]:
        for source in regimen.get("sources", []):
            if source["id"] == source_id:
                return {key: source[key] for key in ("title", "url", "locator") if source.get(key)}
    return None


def view(session: Session, content: Content, hit: Hit, lang: str) -> dict[str, Any]:
    """Antwortobjekt `Medication` (OpenAPI v2.3)."""
    med = hit.medication
    regimens = {r["id"]: r for r in content.regimens["regimens"]}
    return {
        "medication_id": med["id"],
        "inn": localize(med["inn"], lang),
        "trade_name": med.get("trade_name"),
        "sukl_code": med.get("sukl_code"),
        "atc": med["atc"],
        "status": med["status"],
        "regimens": [
            {
                "regimen_id": regimen_id,
                "label": localize(regimens[regimen_id]["label"], lang),
                "symptom_keys": list(regimens[regimen_id]["symptom_keys"]),
            }
            for regimen_id in med["regimen_ids"]
            if regimen_id in regimens
        ],
        "spc": _spc(content, med.get("spc_source_id")),
        "match": hit.match,
        "patients_on_regimen": _patients_on(session, set(med["regimen_ids"])),
    }


def search_view(
    session: Session,
    clock: Clock,
    principal: Principal,
    content: Content,
    raw_query: str,
    lang: str,
) -> list[dict[str, Any]]:
    kind, hits, extra = search_with_sukl(content, raw_query)
    details: dict[str, Any] = {"kind": kind, "results": len(hits) + len(extra)}
    if extra:
        details["sukl_only"] = len(extra)
    record_audit(
        session, clock, principal.actor, "medication_search", "medication", details=details
    )
    session.commit()
    curated = [view(session, content, hit, lang) for hit in hits]
    return curated + [sukl_view(h.entry, h.match) for h in extra]


def detail_view(
    session: Session,
    clock: Clock,
    principal: Principal,
    content: Content,
    medication_id: str,
    lang: str,
) -> dict[str, Any]:
    medications: list[dict[str, Any]] = (content.medications or {}).get("medications", [])
    med = next((m for m in medications if m["id"] == medication_id), None)
    entry = _sukl_entry(medication_id) if med is None else None
    if med is None and entry is None:
        raise not_found()
    answer = (
        view(session, content, Hit(med, "id", 0), lang)
        if med is not None
        else sukl_view(entry, "id")
        if entry is not None
        else {}
    )
    record_audit(
        session,
        clock,
        principal.actor,
        "medication_view",
        "medication",
        target_id=medication_id,
    )
    session.commit()
    return answer
