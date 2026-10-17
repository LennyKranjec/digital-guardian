"""A3-Gegenproben zu T-17 (Besitz A3): Arzneimittelsuche gegen ein unabhängiges Orakel.

Das Orakel liest `medications.yaml` selbst und setzt `triage.md` §8 neu um (eigene Normalisierung,
Art der Suche, Rangfolge). Dazu Angriffe (Metazeichen, Länge, Unicode), Rechte, Audit/Protokoll ohne
Suchtext, Patientenzahl und SPC-Verweise.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import CSRF, login
from test_a3_t13 import api, real_template  # noqa: F401 - Fixtures
from waechter.models import Therapy

BASE = "/api/v1/waechter"
CONTENT = Path(__file__).resolve().parents[1] / "content"
CATALOG: dict[str, Any] = yaml.safe_load((CONTENT / "medications.yaml").read_text(encoding="utf-8"))
REGIMENS: dict[str, Any] = yaml.safe_load((CONTENT / "regimens.yaml").read_text(encoding="utf-8"))
MEDS: list[dict[str, Any]] = CATALOG["medications"]

#: Von A3 gegen die SÚKL-Schnittstelle (prehledy.sukl.cz/dlp/v1/lecive-pripravky/<kód>) geprüft,
#: ATC zusätzlich gegen den WHO-Index (V03AF03 calcium folinate), Stand 2026-10-16.
VERIFIED = {
    "MED-OXALIPLATIN-ACCORD": ("0239968", "L01XA03", "OXALIPLATIN ACCORD"),
    "MED-FLUOROURACIL-ACCORD": ("0242250", "L01BC02", "FLUOROURACIL ACCORD"),
    "MED-XELODA": ("0027023", "L01BC06", "XELODA"),
    "MED-KEYTRUDA": ("0209484", "L01FF02", "KEYTRUDA"),
    "MED-TAXOTERE": ("0167638", "L01CD02", "TAXOTERE"),
    # T-20: gegen die SÚKL-Open-Data (DLP20260925, Zeile je kódSÚKL) von A3 geprüft, 2026-10-17
    "MED-XTANDI": ("0194246", "L02BB04", "XTANDI"),
    "MED-ZYTIGA": ("0168443", "L02BX03", "ZYTIGA"),
    "MED-VOTRIENT": ("0167725", "L01EX03", "VOTRIENT"),
    "MED-OPDIVO": ("0210772", "L01FF01", "OPDIVO"),
}


def client_for(app: FastAPI, username: str) -> TestClient:
    client = TestClient(app, headers=CSRF)
    client.__enter__()
    login(client, username)
    return client


# --- Orakel ---
def norm(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", norm(text))


def oracle(q: str) -> list[tuple[str, str]]:
    """`[(medication_id, match)]` in Rangfolge laut triage.md §8 (eigene Umsetzung)."""
    query = norm(q)
    assert len(query) >= 2
    if query.isascii() and query.isdigit():
        padded = query.zfill(7)
        exact = [m for m in MEDS if m.get("sukl_code") == padded]
        if exact:
            return [(m["id"], "sukl_code") for m in sorted(exact, key=lambda m: m["id"])]
        pref = [m for m in MEDS if m.get("sukl_code", "").startswith(query)]
        return [(m["id"], "sukl_code") for m in sorted(pref, key=lambda m: m["id"])]
    if re.fullmatch(r"[a-z][0-9]{2}(?:[a-z]{1,2}(?:[0-9]{1,2})?)?", query):
        found = [m for m in MEDS if m["atc"].lower().startswith(query)]
        found.sort(key=lambda m: (0 if m["atc"].lower() == query else 1, m["id"]))
        return [(m["id"], "atc") for m in found]
    ranked: list[tuple[int, str, str]] = []
    for med in MEDS:
        names = [*med["inn"].values(), *([med["trade_name"]] if med.get("trade_name") else [])]

        def rank(candidate: str) -> int | None:
            text = norm(candidate)
            if text.startswith(query):
                return 0
            if any(w.startswith(query) for w in words(candidate)):
                return 1
            if len(query) >= 3 and query in text:
                return 2
            return None

        direct = [r for r in map(rank, names) if r is not None]
        if direct:
            ranked.append((min(direct), med["id"], "name"))
            continue
        synonyms = [r for r in map(rank, med.get("synonyms", [])) if r is not None]
        if synonyms:
            ranked.append((min(synonyms), med["id"], "synonym"))
    ranked.sort(key=lambda r: (r[0], r[1]))
    return [(i, m) for _, i, m in ranked]


def search(client: TestClient, q: str, **params: str) -> Any:
    return client.get(f"{BASE}/medications", params={"q": q, **params})


def curated(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """T-33: SÚKL-Ergänzungen (status sukl_only) stehen hinten; das Orakel prüft den Katalog."""
    return [m for m in rows if m["status"] != "sukl_only"]


def pairs(response: Any) -> list[tuple[str, str]]:
    assert response.status_code == 200, (response.status_code, response.text[:200])
    return [(m["medication_id"], m["match"]) for m in curated(response.json())]


# --- Katalog ---
def test_a3_catalog_codes_match_the_sukl_lookup() -> None:
    by_id = {m["id"]: m for m in MEDS}
    for med_id, (code, atc, _name) in VERIFIED.items():
        assert by_id[med_id]["sukl_code"] == code, med_id
        assert by_id[med_id]["atc"] == atc, med_id
    folinate = by_id["MED-CALCIUM-FOLINATE"]
    assert folinate["atc"] == "V03AF03"
    assert folinate.get("sukl_code") is None
    assert len({m["id"] for m in MEDS}) == len(MEDS)
    assert len({m["sukl_code"] for m in MEDS if m.get("sukl_code")}) == sum(
        1 for m in MEDS if m.get("sukl_code")
    )


# --- Suche gegen das Orakel ---
NAME_QUERIES = [
    "oxaliplatin",
    "OXALIPLATINA",
    "oxal",
    "ox",
    "pla",
    "tin",
    "Accord",
    "accord 5",
    "xeloda",
    "Xelóda",
    "XELÓDA",
    "x e",
    "kapecitabin",
    "kapec",
    "capecitabine",
    "pembro",
    "Keytruda",
    "key",
    "docetaxel",
    "Taxotere",
    "taxo",
    "fluorouracil",
    "fluor",
    "uracil",
    "kalcium",
    "kalcium-folinát",
    "kalcium folinat",
    "calcium folinate",
    "folinát",
    "folinat",
    "leukovorin",
    "Leucovorin",
    "kyselina folinová",
    "kyselina folinova",
    "folinic acid",
    "folinic",
    "  oxaliplatin  ",
    "OX  ALIPLATIN",
    "zz",
    "xyz123",
    "mg",
    "5 mg",
    "50 mg/ml",
    "ml",
    "la",
    "pl",
    "ta",
    "ke",
    "ĺ",
    "ďá",
    "čaj",
    "ž",
    "sulfa",
]
NUMBER_QUERIES = [
    "0239968",
    "239968",
    "0242250",
    "242250",
    "27023",
    "0027023",
    "209484",
    "0209484",
    "167638",
    "0167638",
    "02",
    "0239",
    "239",
    "00",
    "0027",
    "27",
    "99",
    "12345678",
    "00000000",
    "0000000",
    "02399680",
    "9999999",
    "0209",
]
ATC_QUERIES = [
    "L01",
    "l01",
    "L01X",
    "L01XA",
    "L01XA03",
    "l01xa03",
    "L01B",
    "L01BC",
    "L01BC0",
    "L01BC02",
    "L01BC06",
    "L01F",
    "L01FF02",
    "L01C",
    "L01CD02",
    "V03",
    "V03AF03",
    "v03af",
    "L02",
    "A01",
    "Z99",
    "L0",
    "L01XA3",
    "L1B",
]


@pytest.mark.parametrize("q", NAME_QUERIES + NUMBER_QUERIES + ATC_QUERIES)
def test_a3_search_equals_the_independent_oracle(api: Any, q: str) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "doctor")
    if len(norm(q)) < 2:
        assert search(client, q).status_code == 422
        return
    assert pairs(search(client, q)) == oracle(q), q


def test_a3_results_are_capped_deterministic_and_each_hit_contains_the_query(api: Any) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "admin")
    for q in ("o", "ox", "a", "i", "ac", "in", "ne"):
        if len(norm(q)) < 2:
            continue
        first = pairs(search(client, q))
        assert first == pairs(search(client, q))
        assert len(first) <= 20
        by_id = {m["id"]: m for m in MEDS}
        for med_id, match in first:
            med = by_id[med_id]
            haystack = norm(
                " ".join(
                    [*med["inn"].values(), med.get("trade_name", ""), *med.get("synonyms", [])]
                )
            )
            assert norm(q) in haystack or match in {"atc", "sukl_code"}, (q, med_id)


# --- Angriffe ---
HOSTILE = [
    "%",
    "%%",
    "_",
    "__",
    "' OR 1=1 --",
    "'; DROP TABLE wa_patients; --",
    '" OR ""="',
    ".*",
    "(a+)+$",
    "[a-z]+",
    "\\",
    "\\x00",
    "a\nb",
    "ab\r\ncd",
    "\t\tox",
    "<script>alert(1)</script>",
    "{{7*7}}",
    "${7*7}",
    "‮oxaliplatin",
    "öx",
    "😀😀",
    "ΧΕΛΟΔΑ",
    "".join(chr(0xFF41 + i) for i in (14, 23, 0, 11)),
    "".join(chr(0xFF10 + int(d)) for d in "0239968"),
    "ﬁ",
    "ǆ",
    "x" * 60,
]


@pytest.mark.parametrize("q", HOSTILE)
def test_a3_hostile_queries_never_crash_and_match_the_oracle(api: Any, q: str) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "doctor")
    response = search(client, q)
    assert response.status_code in (200, 422), (q, response.status_code, response.text[:200])
    if response.status_code == 200:
        assert pairs(response) == oracle(q), q
    # nach dem Angriff funktioniert die Suche normal
    assert pairs(search(client, "xeloda")) == [("MED-XELODA", "name")]


def test_a3_length_and_parameter_validation(api: Any) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "doctor")
    assert search(client, "x" * 61).status_code == 422
    assert search(client, "x" * 60).status_code == 200
    assert client.get(f"{BASE}/medications").status_code == 422
    assert search(client, "oxal", lang="xx").status_code == 422
    assert search(client, " a ").status_code == 422
    assert search(client, "   ").status_code == 422
    for lang in ("cs", "en", "de"):
        assert search(client, "oxal", lang=lang).status_code == 200
    assert client.get(f"{BASE}/medications", params=[("q", "ox"), ("q", "xe")]).status_code in (
        200,
        422,
    )


# --- Rechte, Audit, Protokoll ---
def test_a3_roles(api: Any) -> None:  # noqa: F811
    app, _ = api
    assert search(client_for(app, "doctor"), "xeloda").status_code == 200
    assert search(client_for(app, "admin"), "xeloda").status_code == 200
    for user in ("patient", "patient2", "user"):
        assert search(client_for(app, user), "xeloda").status_code == 403, user
        detail = client_for(app, user).get(f"{BASE}/medications/MED-XELODA")
        assert detail.status_code == 403, user
    anonymous = TestClient(app, headers=CSRF)
    assert search(anonymous, "xeloda").status_code == 401
    assert anonymous.get(f"{BASE}/medications/MED-XELODA").status_code == 401


def test_a3_search_text_is_neither_audited_nor_logged(
    api: Any,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, _ = api
    client = client_for(app, "doctor")
    needle = "Novakova-Jana-1975"
    with caplog.at_level(logging.DEBUG):
        search(client, needle)
        search(client, "xeloda")
    with app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "medication_search")
        ).all()
    assert len(events) == 2
    for event in events:
        assert set(event.details_json or {}) <= {"kind", "results"}
        assert needle.lower() not in str(event.details_json).lower()
        assert needle.lower() not in str(event.target_id).lower()
    server = " | ".join(
        r.getMessage() for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))
    ).lower()  # Protokoll des Servers (der Testclient protokolliert seine eigene URL)
    assert server, "kein Serverprotokoll aufgefangen"
    assert needle.lower() not in server
    assert "novakova" not in server


# --- Antwortinhalt ---
def test_a3_patient_count_spc_and_regimens_match_the_data(api: Any) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "doctor")
    with app.state.session_factory() as session:
        latest: dict[str, tuple[Any, str]] = {}
        for t in session.scalars(select(Therapy).order_by(Therapy.cycle_start, Therapy.id)):
            latest[t.patient_id] = (t.cycle_start, t.regimen_id)
    sources = {s["id"]: s for r in REGIMENS["regimens"] for s in r.get("sources", [])}
    regimens = {r["id"]: r for r in REGIMENS["regimens"]}
    rows = {m["medication_id"]: m for m in curated(search(client, "an").json())}  # trifft mehrere
    queries = (
        "oxal",
        "fluor",
        "xel",
        "pem",
        "doc",
        "kalc",
        "xtandi",
        "zytiga",
        "votrient",
        "opdivo",
    )
    for q in queries:
        rows.update({m["medication_id"]: m for m in curated(search(client, q).json())})
    assert set(rows) == {m["id"] for m in MEDS}
    for med in MEDS:
        row = rows[med["id"]]
        want = sum(1 for _, regimen in latest.values() if regimen in med["regimen_ids"])
        assert row["patients_on_regimen"] == want, med["id"]
        assert [r["regimen_id"] for r in row["regimens"]] == med["regimen_ids"]
        for regimen in row["regimens"]:
            assert regimen["symptom_keys"] == regimens[regimen["regimen_id"]]["symptom_keys"]
        if med.get("spc_source_id"):
            source = sources[med["spc_source_id"]]
            assert row["spc"]["url"] == source["url"], med["id"]
            assert row["spc"]["locator"] == source["locator"], med["id"]
        else:
            assert row["spc"] is None
        assert row["status"] == med["status"]
        assert row["atc"] == med["atc"]


def test_a3_detail_equals_the_search_hit_and_is_audited(api: Any) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "doctor")
    for med in MEDS:
        detail = client.get(f"{BASE}/medications/{med['id']}")
        assert detail.status_code == 200, med["id"]
        hit = next(
            h for h in search(client, med["inn"]["en"]).json() if h["medication_id"] == med["id"]
        )
        assert {k: v for k, v in detail.json().items() if k != "match"} == {
            k: v for k, v in hit.items() if k != "match"
        }
    for bad in ("nope", "MED-", "../etc/passwd", "MED-XELODA%20", "med-xeloda", "%00", "a" * 300):
        assert client.get(f"{BASE}/medications/{bad}").status_code in (404, 422), bad
    with app.state.session_factory() as session:
        views = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "medication_view")
        ).all()
    assert len(views) == len(MEDS)
    assert all(not (v.details_json or {}) for v in views)


@pytest.mark.parametrize("lang", ["cs", "en", "de"])
def test_a3_inn_is_localized_with_fallback_and_never_empty(api: Any, lang: str) -> None:  # noqa: F811
    app, _ = api
    client = client_for(app, "doctor")
    row = search(client, "kapecitabin" if lang == "cs" else "capecitabine", lang=lang).json()[0]
    assert row["inn"]
    assert row["inn"] == ({"cs": "kapecitabin", "de": "capecitabin"}.get(lang, "capecitabine"))
