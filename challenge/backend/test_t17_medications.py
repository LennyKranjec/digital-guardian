"""T-17 (Vertrag v2.3): Arzneimittelsuche nach Name, kódSÚKL und ATC (Echtinhalt, Ankerzeit)."""

import dataclasses
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.persistence.models import AuditEvent
from conftest import login
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, ContentError, load_content
from waechter.models import Patient, Therapy
from waechter.services import medications as med_service

REAL = Path(__file__).resolve().parents[1] / "content"
SEARCH = "/api/v1/waechter/medications"


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


@pytest.fixture(scope="module")
def content() -> Content:
    return load_content(REAL)


def app_of(client: TestClient) -> FastAPI:
    application = client.app
    assert isinstance(application, FastAPI)
    return application


def found(client: TestClient, query: str, **params: str) -> list[dict[str, Any]]:
    reply = client.get(SEARCH, params={"q": query, **params})
    assert reply.status_code == 200, reply.text
    body: list[dict[str, Any]] = reply.json()
    return body


def names(hits: list[dict[str, Any]]) -> list[str]:
    return [h["medication_id"] for h in hits if h["status"] != "sukl_only"]  # T-33: kuratiert


# ---- Normalisierung und Art der Suche (reine Funktionen) -------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Kalcium-Folinát ", "kalcium-folinat"),
        ("KAPECITABIN", "kapecitabin"),
        ("Léčivo   Ž", "lecivo z"),
        ("Ǩ", "k"),
    ],
)
def test_normalize_strips_case_diacritics_and_spaces(raw: str, expected: str) -> None:
    assert med_service.normalize(raw) == expected


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("0239968", "sukl"),
        ("239968", "sukl"),
        ("12", "sukl"),
        ("l01bc", "atc"),
        ("l01bc02", "atc"),
        ("l01", "atc"),
        ("v03af03", "atc"),
        ("xeloda", "name"),
        ("kapecitabin", "name"),
        ("l01x", "atc"),  # Gruppe der 4. Ebene ist ein gültiger ATC-Präfix
        ("l0x", "name"),  # kein gültiges ATC-Muster ⇒ Name
        ("0239968abc", "name"),
        ("٣٤٥", "name"),  # nur Ziffern im ASCII-Sinn zählen als Nummer
    ],
)
def test_classify_the_kind_of_search(query: str, kind: str) -> None:
    assert med_service.classify(query) == kind


# ---- Suche über die API ---------------------------------------------------------------------
@pytest.mark.parametrize("query", ["0239968", "239968", " 239968 "])
def test_sukl_code_with_or_without_leading_zeros_finds_oxaliplatin(
    client: TestClient, query: str
) -> None:
    login(client, "doctor")
    hits = found(client, query)
    assert names(hits) == ["MED-OXALIPLATIN-ACCORD"]
    assert hits[0]["match"] == "sukl_code"
    assert hits[0]["sukl_code"] == "0239968"


def test_sukl_exact_comes_before_prefix_and_prefix_is_found(client: TestClient) -> None:
    login(client, "doctor")
    hits = found(client, "02399")
    assert names(hits) == ["MED-OXALIPLATIN-ACCORD"]
    assert hits[0]["match"] == "sukl_code"


def test_atc_prefix_finds_all_matching_preparations(client: TestClient) -> None:
    login(client, "doctor")
    hits = found(client, "L01BC")
    assert names(hits) == ["MED-FLUOROURACIL-ACCORD", "MED-XELODA"]
    assert {h["match"] for h in hits} == {"atc"}
    assert names(found(client, "l01bc06")) == ["MED-XELODA"]
    assert names(found(client, "L01XA03")) == ["MED-OXALIPLATIN-ACCORD"]


@pytest.mark.parametrize(
    "query", ["kapecitabin", "capecitabine", "xeloda", "KAPECITABIN", "Xelóda"]
)
def test_names_inn_cs_en_trade_name_case_and_diacritics_find_xeloda(
    client: TestClient, query: str
) -> None:
    login(client, "doctor")
    hits = found(client, query)
    assert names(hits) == ["MED-XELODA"]
    assert hits[0]["match"] == "name"


def test_synonym_finds_calcium_folinate_and_is_marked_as_synonym(client: TestClient) -> None:
    login(client, "doctor")
    for query in ("leukovorin", "Leucovorin", "kyselina folinova", "folinic acid"):
        hits = found(client, query)
        assert names(hits) == ["MED-CALCIUM-FOLINATE"], query
        assert hits[0]["match"] == "synonym"
    inn = found(client, "kalcium-folinát")
    assert inn[0]["match"] == "name"
    assert inn[0]["sukl_code"] is None
    assert inn[0]["spc"] is None  # kein SPC-Link im Katalog


def test_name_prefix_finds_oxaliplatin_and_nonsense_finds_nothing(client: TestClient) -> None:
    login(client, "doctor")
    assert names(found(client, "ox")) == ["MED-OXALIPLATIN-ACCORD"]
    assert found(client, "zz") == []
    assert found(client, "99999999") == []  # mehr als 7 Ziffern


def test_every_catalogue_entry_is_found_by_each_of_its_identifiers(
    client: TestClient, content: Content
) -> None:
    assert content.medications is not None
    login(client, "doctor")
    for med in content.medications["medications"]:
        ids = {med["id"]}
        assert med["id"] in names(found(client, med["inn"]["cs"]))
        assert med["id"] in names(found(client, med["inn"]["en"]))
        assert med["id"] in names(found(client, med["atc"]))
        if med.get("trade_name"):
            assert med["id"] in names(found(client, med["trade_name"]))
        if med.get("sukl_code"):
            assert ids == set(names(found(client, med["sukl_code"])))


def test_result_carries_regimen_with_symptoms_spc_and_patient_count(
    client: TestClient, content: Content
) -> None:
    login(client, "doctor")
    hit = found(client, "xeloda", lang="en")[0]
    assert hit["inn"] == "capecitabine"
    assert hit["trade_name"] == "Xeloda"
    assert hit["atc"] == "L01BC06"
    regimen = next(r for r in content.regimens["regimens"] if r["id"] == "CAPECITABINE")
    assert hit["regimens"] == [
        {
            "regimen_id": "CAPECITABINE",
            "label": regimen["label"]["en"],
            "symptom_keys": regimen["symptom_keys"],
        }
    ]
    source = next(s for s in regimen["sources"] if s["id"] == "SRC-SUKL-XELODA")
    assert hit["spc"] == {
        "title": source["title"],
        "url": source["url"],
        "locator": source["locator"],
    }
    with app_of(client).state.session_factory() as session:
        latest: dict[str, str] = {}
        for t in session.scalars(select(Therapy).order_by(Therapy.cycle_start, Therapy.id)):
            latest[t.patient_id] = t.regimen_id
    assert hit["patients_on_regimen"] == sum(1 for r in latest.values() if r == "CAPECITABINE")
    assert hit["patients_on_regimen"] >= 1


def test_inn_is_localized(client: TestClient) -> None:
    login(client, "doctor")
    assert found(client, "oxaliplatin", lang="en")[0]["inn"] == "oxaliplatin"
    assert found(client, "oxaliplatin", lang="cs")[0]["inn"] == "oxaliplatina"
    assert found(client, "oxaliplatin", lang="de")[0]["inn"]  # Rückfall auf Englisch


def test_detail_by_id(client: TestClient) -> None:
    login(client, "doctor")
    ok = client.get(f"{SEARCH}/MED-KEYTRUDA")
    assert ok.status_code == 200
    assert ok.json()["trade_name"] == "Keytruda"
    assert ok.json()["match"] == "id"  # gefunden über die ID (openapi v2.3)
    assert ok.json()["regimens"][0]["regimen_id"] == "PEMBROLIZUMAB"
    assert client.get(f"{SEARCH}/MED-NOPE").status_code == 404
    login(client, "admin")
    assert client.get(f"{SEARCH}/MED-KEYTRUDA").status_code == 200


# ---- Rechte, Eingabe, Audit ------------------------------------------------------------------
def test_access_and_validation(client: TestClient) -> None:
    assert client.get(SEARCH, params={"q": "xeloda"}).status_code == 401
    login(client, "patient")
    assert client.get(SEARCH, params={"q": "xeloda"}).status_code == 403
    assert client.get(f"{SEARCH}/MED-XELODA").status_code == 403
    login(client, "doctor")
    for bad in ("a", "", " a ", "x" * 61):
        assert client.get(SEARCH, params={"q": bad}).status_code == 422, repr(bad)
    assert client.get(SEARCH).status_code == 422
    assert client.get(SEARCH, params={"q": "xeloda", "lang": "xx"}).status_code == 422
    login(client, "admin")
    assert client.get(SEARCH, params={"q": "xeloda"}).status_code == 200


def test_audit_records_kind_and_count_but_never_the_search_text(client: TestClient) -> None:
    login(client, "doctor")
    found(client, "geheimsuche")
    found(client, "239968")
    with app_of(client).state.session_factory() as session:
        events = list(
            session.scalars(select(AuditEvent).where(AuditEvent.action == "medication_search"))
        )
        everything = repr(
            [
                (e.details_json, e.target_id, e.subject_id)
                for e in session.scalars(select(AuditEvent))
            ]
        )
    assert [e.details_json for e in events] == [
        {"kind": "name", "results": 0},
        {"kind": "sukl", "results": 1},
    ]
    assert "geheimsuche" not in everything
    assert "239968" not in str(events[-1].details_json)


def test_search_does_not_depend_on_patient_data(client: TestClient) -> None:
    """Identifikation, nie Regel: Ergebnis ändert sich nicht, wenn Patientendaten fehlen."""
    login(client, "doctor")
    before = [(h["medication_id"], h["match"]) for h in found(client, "l01")]
    with app_of(client).state.session_factory() as session:
        for patient in session.scalars(select(Patient)):
            patient.user_id = None
        session.commit()
    assert [(h["medication_id"], h["match"]) for h in found(client, "l01")] == before


# ---- Ordnung und Obergrenze (synthetischer Katalog) -------------------------------------------
def synthetic(content: Content, medications: list[dict[str, Any]]) -> Content:
    return dataclasses.replace(
        content, medications={"version": "medications-v1", "medications": medications}
    )


def med(ident: str, inn: str, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": f"MED-{ident}",
        "inn": {"cs": inn, "en": inn},
        "atc": "L01XA03",
        "regimen_ids": ["FOLFOX"],
        "status": "draft",
    }
    base.update(extra)
    return base


def test_result_order_is_name_start_then_word_start_then_substring(content: Content) -> None:
    catalogue = synthetic(
        content,
        [
            med("C", "kyselina plati"),  # Teilwort-Anfang
            med("D", "alplatinum"),  # Zeichenfolge im Wort
            med("B", "platina"),  # Namensanfang
            med("A", "platinum"),  # Namensanfang, vor B nach ID
        ],
    )
    _, hits = med_service.search(catalogue, "plati")
    assert [h.medication["id"] for h in hits] == ["MED-A", "MED-B", "MED-C", "MED-D"]
    assert [h.rank for h in hits] == [0, 0, 1, 2]
    _, short = med_service.search(catalogue, "la")  # unter 3 Zeichen keine Zeichenfolge im Wort
    assert [h.medication["id"] for h in short] == []


def test_number_search_prefers_exact_over_prefix(content: Content) -> None:
    catalogue = synthetic(
        content,
        [
            med("P", "p-med", sukl_code="1230000"),
            med("E", "e-med", sukl_code="0000123"),
        ],
    )
    _, exact = med_service.search(catalogue, "123")
    assert [(h.medication["id"], h.rank) for h in exact] == [("MED-E", 0)]
    _, prefix = med_service.search(catalogue, "1230")
    assert [(h.medication["id"], h.rank) for h in prefix] == [("MED-P", 1)]


def test_at_most_twenty_results(content: Content) -> None:
    catalogue = synthetic(content, [med(f"M{i:02d}", f"testmed {i:02d}") for i in range(30)])
    _, hits = med_service.search(catalogue, "testmed")
    assert len(hits) == 20
    assert [h.medication["id"] for h in hits] == [f"MED-M{i:02d}" for i in range(20)]


def test_missing_catalogue_gives_no_hits_and_short_query_is_still_an_error(
    content: Content,
) -> None:
    empty = dataclasses.replace(content, medications=None)
    assert med_service.search(empty, "xeloda")[1] == []
    with pytest.raises(Exception, match="Query too short"):
        med_service.search(empty, " x ")


# ---- Inhaltslader ----------------------------------------------------------------------------
@pytest.fixture
def real_copy(tmp_path: Path) -> Path:
    target = tmp_path / "content"
    shutil.copytree(REAL, target, ignore=shutil.ignore_patterns("__pycache__", "tools", "*.py"))
    return target


def edit(directory: Path, change: Any) -> list[str]:
    path = directory / "medications.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ContentError) as caught:
        load_content(directory)
    return [str(i) for i in caught.value.issues]


def test_real_catalogue_loads_and_is_optional(content: Content, real_copy: Path) -> None:
    assert content.medications is not None
    assert len(content.medications["medications"]) >= 6
    (real_copy / "medications.yaml").unlink()
    assert load_content(real_copy).medications is None


def test_catalogue_cross_references_are_checked(real_copy: Path) -> None:
    def regimen(data: dict[str, Any]) -> None:
        data["medications"][0]["regimen_ids"] = ["NOPE"]

    def source(data: dict[str, Any]) -> None:
        data["medications"][0]["spc_source_id"] = "SRC-NOPE"

    def code(data: dict[str, Any]) -> None:
        data["medications"][1]["sukl_code"] = data["medications"][0]["sukl_code"]

    def ident(data: dict[str, Any]) -> None:
        data["medications"][1]["id"] = data["medications"][0]["id"]

    for change, needle in (
        (regimen, "unknown regimen id"),
        (source, "unknown source id"),
        (code, "duplicate code"),
        (ident, "duplicate id"),
    ):
        fresh = real_copy.parent / f"c-{change.__name__}"
        shutil.copytree(real_copy, fresh)
        assert any("medications.yaml" in i and needle in i for i in edit(fresh, change)), needle
