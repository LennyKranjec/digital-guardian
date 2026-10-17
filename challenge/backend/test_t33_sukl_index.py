"""T-33: Arzneimittelsuche ergänzt den kuratierten Katalog um den SÚKL-Index (Open Data DLP)."""

import csv
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import login
from waechter.constants import CONTENT_DIR_ENV
from waechter.services import medications as med_service

REAL = Path(__file__).resolve().parents[1] / "content"
INDEX = REAL / "sukl_index.csv"
SEARCH = "/api/v1/waechter/medications"

# Öffentliche Fassung ohne sukl_index.csv (Nutzungsbedingungen ungeprüft)
pytestmark = pytest.mark.skipif(
    not INDEX.is_file(), reason="sukl_index.csv not shipped in the public version"
)


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


def found(client: TestClient, query: str) -> list[dict[str, Any]]:
    reply = client.get(SEARCH, params={"q": query})
    assert reply.status_code == 200, reply.text
    body: list[dict[str, Any]] = reply.json()
    return body


def index_rows() -> list[dict[str, str]]:
    with INDEX.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_index_file_has_only_the_agreed_columns_and_is_small() -> None:
    assert INDEX.stat().st_size < 5 * 1024 * 1024
    rows = index_rows()
    assert len(rows) > 1000
    assert list(rows[0]) == ["sukl_code", "name", "strength", "package", "atc", "form", "holder"]
    assert all(len(r["sukl_code"]) == 7 and r["sukl_code"].isdigit() for r in rows)


def test_name_only_in_the_index_is_found_as_sukl_only(client: TestClient) -> None:
    login(client, "doctor")
    hits = found(client, "paralen")
    assert hits, "Paralen steht im SÚKL-Index"
    assert {h["status"] for h in hits} == {"sukl_only"}
    first = hits[0]
    assert first["medication_id"] == f"SUKL-{first['sukl_code']}"
    assert first["regimens"] == []
    assert first["spc"] is None
    assert first["patients_on_regimen"] == 0
    assert first["sukl"]["name"].upper().startswith("PARALEN")
    assert first["match"] == "name"
    assert found(client, "Ibuprofen")  # Wirkstoff-Name als Handelsname-Anfang


def test_sukl_code_search_with_and_without_leading_zeros(client: TestClient) -> None:
    login(client, "doctor")
    row = next(r for r in index_rows() if r["name"].startswith("PARALEN"))
    code = row["sukl_code"]
    for query in (code, code.lstrip("0")):
        hits = found(client, query)
        assert [h["sukl_code"] for h in hits] == [code], query
        assert hits[0]["match"] == "sukl_code"
    detail = client.get(f"{SEARCH}/SUKL-{code}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "sukl_only"
    assert detail.json()["match"] == "id"
    for bad in ("SUKL-9999999", "SUKL-12", "SUKL-abcdefg", f"sukl-{code}"):
        assert client.get(f"{SEARCH}/{bad}").status_code == 404, bad


def test_curated_first_then_sukl_sorted_and_capped(client: TestClient) -> None:
    login(client, "doctor")
    hits = found(client, "oxaliplatin")
    statuses = [h["status"] for h in hits]
    assert statuses[0] != "sukl_only"
    assert hits[0]["medication_id"] == "MED-OXALIPLATIN-ACCORD"
    first_sukl = statuses.index("sukl_only")
    assert all(s == "sukl_only" for s in statuses[first_sukl:])
    assert all(s != "sukl_only" for s in statuses[:first_sukl])
    curated_codes = {h["sukl_code"] for h in hits[:first_sukl]}
    assert not curated_codes & {h["sukl_code"] for h in hits[first_sukl:]}
    assert len(hits) <= 25
    many = found(client, "ib")
    assert len(many) == 25
    assert many == found(client, "ib")  # deterministisch
    _, _, extra = med_service.search_with_sukl(_content(), "ib")
    keys = [(h.rank, h.entry.norm_name, h.entry.sukl_code) for h in extra]
    assert keys == sorted(keys)


def test_atc_prefix_reaches_the_index(client: TestClient) -> None:
    login(client, "doctor")
    hits = found(client, "M01AE01")
    assert hits
    assert all(h["atc"] == "M01AE01" for h in hits)
    assert all(h["match"] == "atc" for h in hits)


def test_no_sukl_lookup_when_curated_has_ten_or_more() -> None:
    meds = [
        {"id": f"MED-T{i:02}", "inn": {"cs": f"ibtest{i}", "en": f"ibtest{i}"}, "atc": "X01"}
        for i in range(10)
    ]
    content = _content()
    from dataclasses import replace

    catalogue = replace(content, medications={"medications": meds})
    _, hits, extra = med_service.search_with_sukl(catalogue, "ibtest")
    assert len(hits) == 10
    assert extra == []


def _content() -> Any:
    from waechter.content import load_content

    return load_content(REAL)
