"""T-21: Dokumente ⇒ FHIR (Proof of Concept).

Prüft den deterministischen Prüfer (erfundene Zitate/Codes/Werte/Einheiten/Daten werden verworfen),
den Regex-Extraktor, den Sprachmodell-Pfad (gemocktes Modell, nie Netz), die Rollen (403/404/409),
Paralleltests (Upload, Entscheidung) und dass nur bestätigte Ressourcen im Patientenexport stehen.
Die HAPI-Prüfung läuft außerhalb von pytest (Befehl und Ergebnis im Handoff); mit
`T21_DUMP_DIR=<Ordner>` schreibt der Test `test_dump_bundles_for_validator` die Bundles dorthin.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.persistence.models import AuditEvent
from conftest import CSRF, login, run_parallel
from test_fhir import BASE, export, pid, references, resources, staff
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import Content, load_content
from waechter.documents import extractors
from waechter.documents.allowlists import AllowLists, from_content
from waechter.documents.candidates import RawCandidate
from waechter.documents.verify import check, check_all, dates_in
from waechter.knowledge.extract import ExtractionUnavailable
from waechter.models import Document, Patient
from waechter.services import documents as documents_service

REAL = Path(__file__).resolve().parents[1] / "content"
DEMO_DOCS = Path(__file__).resolve().parents[1] / "demo" / "docs"
LETTER = DEMO_DOCS / "arztbrief_SYN-0001.md"
LAB = DEMO_DOCS / "laborbefund_SYN-0001.csv"
DASH = chr(0x2013)  # Gedankenstrich der Demo-Dokumente
MAIN_DX = f"Hlavní diagnóza: C50.9 {DASH} karcinom prsu (syntetický příklad)."
SIDE_DX = f"Vedlejší diagnóza: I10 {DASH} hypertenze (syntetický příklad)."


@pytest.fixture(autouse=True)
def real_content(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Echter Inhalt: ICD-Präfixe und Arzneimittelkennungen stehen nur dort."""
    monkeypatch.setenv(CONTENT_DIR_ENV, str(REAL))
    return REAL


@pytest.fixture(scope="module")
def allow() -> AllowLists:
    content: Content = load_content(REAL)
    return from_content(content)


def letter() -> str:
    return LETTER.read_text(encoding="utf-8")


def lab() -> str:
    return LAB.read_text(encoding="utf-8")


def raw(kind: str, code: str, quote: str, **extra: str | None) -> RawCandidate:
    return RawCandidate(kind, code, quote, **extra)


# --- Prüfer ---------------------------------------------------------------------------------


def test_verifier_accepts_a_documented_diagnosis(allow: AllowLists) -> None:
    candidate, reasons = check(
        raw("Condition", "C50.9", MAIN_DX),
        letter(),
        allow,
    )
    assert reasons == []
    assert candidate is not None
    assert candidate.code == "C50.9"


def test_verifier_rejects_an_invented_quote(allow: AllowLists) -> None:
    candidate, reasons = check(
        raw("Condition", "C50.9", "Pacientka trpí karcinomem prsu C50.9 ve stadiu IV."),
        letter(),
        allow,
    )
    assert candidate is None
    assert reasons == ["quote_not_verbatim"]


def test_verifier_quote_comparison_ignores_whitespace_but_not_words(allow: AllowLists) -> None:
    text = "Diagnóza:\n  C50.9   karcinom\nprsu"
    ok, _ = check(raw("Condition", "C50.9", "Diagnóza: C50.9 karcinom prsu"), text, allow)
    assert ok is not None
    bad, reasons = check(raw("Condition", "C50.9", "Diagnóza: C50.9 karcinom plic"), text, allow)
    assert bad is None
    assert reasons == ["quote_not_verbatim"]


@pytest.mark.parametrize(
    ("code", "quote", "expected"),
    [
        ("C99.9", "Zhoubný nádor C99.9 (vymyšlený kód)", "code_not_allowed"),  # nicht in der Liste
        ("I10", SIDE_DX, "code_not_allowed"),
        ("C50.9", "Dříve podán docetaxel v rámci předchozí léčby.", "code_not_in_quote"),
        ("C5", MAIN_DX, "code_not_allowed"),
        ("", MAIN_DX, "code_not_allowed"),
    ],
)
def test_verifier_rejects_codes_outside_the_allow_list_or_the_quote(
    allow: AllowLists, code: str, quote: str, expected: str
) -> None:
    text = letter() + "\nZhoubný nádor C99.9 (vymyšlený kód)\n"
    candidate, reasons = check(raw("Condition", code, quote), text, allow)
    assert candidate is None
    assert reasons == [expected]


def test_verifier_medication_needs_a_known_code_that_the_quote_supports(allow: AllowLists) -> None:
    quote = "Dříve podán docetaxel v rámci předchozí léčby."
    ok, _ = check(raw("MedicationStatement", "L01CD02", quote), letter(), allow)
    assert ok is not None
    assert ok.display == "docetaxel"
    unknown, reasons = check(raw("MedicationStatement", "L01XX99", quote), letter(), allow)
    assert unknown is None
    assert reasons == ["code_not_allowed"]
    wrong, reasons = check(raw("MedicationStatement", "L01BC06", quote), letter(), allow)
    assert wrong is None
    assert reasons == ["code_not_in_quote"]


def test_verifier_accepts_sukl_code_and_normalizes_to_atc(allow: AllowLists) -> None:
    quote = "Aktuální léčba: kapecitabin (Xeloda, kód SÚKL 0027023, ATC L01BC06), 14denní cyklus"
    candidate, reasons = check(
        raw("MedicationStatement", "0027023", quote + " (syntetický příklad)."), letter(), allow
    )
    assert reasons == []
    assert candidate is not None
    assert candidate.code == "L01BC06"
    assert candidate.sukl_code == "0027023"


@pytest.mark.parametrize(
    ("loinc", "value", "unit", "quote", "expected"),
    [
        ("718-7", "118", "g/l", "Hemoglobin;108;g/l;120-160", "value_not_in_quote"),
        ("718-7", "108", "g/dl", "Hemoglobin;108;g/l;120-160", "unit_not_in_quote"),
        ("718-7", "108", "mmol/l", "Hemoglobin;108;g/l;120-160", "unit_not_allowed"),
        ("718-7", "abc", "g/l", "Hemoglobin;108;g/l;120-160", "value_invalid"),
        ("718-7", "108", "g/l", "Trombocyty;142;10^9/l;150-400", "name_not_in_quote"),
        ("777-3", "142", "g/l", "Trombocyty;142;10^9/l;150-400", "unit_not_allowed"),
        ("9999-9", "108", "g/l", "Hemoglobin;108;g/l;120-160", "code_not_allowed"),
        ("718-7", "8", "g/l", "Hemoglobin;108;g/l;120-160", "value_not_in_quote"),
    ],
)
def test_verifier_rejects_lab_values_that_the_quote_does_not_support(
    allow: AllowLists, loinc: str, value: str, unit: str, quote: str, expected: str
) -> None:
    candidate, reasons = check(
        raw("Observation", loinc, quote, value=value, unit=unit), lab(), allow
    )
    assert candidate is None
    assert reasons == [expected]


def test_verifier_lab_accepts_decimal_comma_and_unit_spellings(allow: AllowLists) -> None:
    text = "Datum: 2026-10-14\nLeukocyty 3,8 x10^9/L\nKreatinin 74 µmol/l\n"
    a, ra = check(
        raw("Observation", "6690-2", "Leukocyty 3,8 x10^9/L", value="3.8", unit="x10^9/L"),
        text,
        allow,
    )
    assert ra == []
    assert a is not None
    assert a.ucum == "10*9/L"
    assert a.value == "3.8"
    b, rb = check(
        raw("Observation", "2160-0", "Kreatinin 74 µmol/l", value="74", unit="umol/l"), text, allow
    )
    assert rb == []
    assert b is not None
    assert b.ucum == "umol/L"


def test_verifier_rejects_dates_that_are_not_in_the_document(allow: AllowLists) -> None:
    quote = MAIN_DX
    ok, _ = check(raw("Condition", "C50.9", quote, date="2026-10-14"), letter(), allow)
    assert ok is not None
    assert ok.date == "2026-10-14"
    missing, reasons = check(raw("Condition", "C50.9", quote, date="2026-10-15"), letter(), allow)
    assert missing is None
    assert reasons == ["date_not_in_document"]
    broken, reasons = check(raw("Condition", "C50.9", quote, date="2026-13-40"), letter(), allow)
    assert broken is None
    assert reasons == ["date_invalid"]


def test_dates_in_understands_iso_and_czech_german_notation() -> None:
    text = "vom 14.10.2026, Kontrolle 2026-11-02, falsch 31.02.2026 und 2026-02-30"
    assert dates_in(text) == ["2026-10-14", "2026-11-02"]


def test_verifier_rejects_unknown_resource_types_and_duplicates(allow: AllowLists) -> None:
    candidate, reasons = check(raw("Patient", "C50.9", "Hlavní diagnóza: C50.9"), letter(), allow)
    assert candidate is None
    assert reasons == ["resource_type_unknown"]
    quote = MAIN_DX
    accepted, rejected = check_all(
        [raw("Condition", "C50.9", quote), raw("Condition", "C50.9", quote)], letter(), allow
    )
    assert len(accepted) == 1
    assert rejected == []


# --- Extraktor ------------------------------------------------------------------------------


def test_template_extracts_the_demo_letter_deterministically(allow: AllowLists) -> None:
    first = extractors.extract(letter(), allow, "template")
    second = extractors.extract(letter(), allow, "template")
    assert first == second
    assert first.extractor == "template-regex-v1"
    assert first.mode == "template"
    accepted, rejected = check_all(first.raws, letter(), allow)
    kinds = sorted((c.resource_type, c.code) for c in accepted)
    assert kinds == [
        ("Condition", "C50.9"),
        ("MedicationStatement", "L01BC06"),
        ("MedicationStatement", "L01CD02"),
        ("Observation", "718-7"),
        ("Observation", "751-8"),
    ]
    assert [(r.code, r.reasons) for r in rejected] == [("I10", ("code_not_allowed",))]
    dated = {(c.code, c.date) for c in accepted}
    assert ("718-7", "2026-10-12") in dated  # Datum der Zeile
    assert ("C50.9", "2026-10-14") in dated  # Datum der Kopfzeile


def test_template_extracts_the_demo_lab_csv(allow: AllowLists) -> None:
    extraction = extractors.extract(lab(), allow, "template")
    accepted, rejected = check_all(extraction.raws, lab(), allow)
    assert rejected == []
    values = {c.code: (c.value, c.unit, c.date) for c in accepted}
    assert values == {
        "718-7": ("108", "g/l", "2026-10-14"),
        "777-3": ("142", "10^9/l", "2026-10-14"),
        "6690-2": ("3.8", "10^9/l", "2026-10-14"),
        "751-8": ("1.4", "10^9/l", "2026-10-14"),
        "2160-0": ("74", "µmol/l", "2026-10-14"),
        "1742-6": ("0.62", "µkat/l", "2026-10-14"),
        "1988-5": ("12", "mg/l", "2026-10-14"),
    }


def test_template_ignores_prose_and_unsupported_units(allow: AllowLists) -> None:
    text = "Alt 5 Tage nach Therapie. CRP <5 mg/l. Hemoglobin 108 furlong. Natrium 140 mmol/l"
    accepted, _ = check_all(extractors.extract_template(text, allow), text, allow)
    assert [c.code for c in accepted] == ["2951-2"]  # nur Natrium mit passender Einheit


class FakeModel:
    model = "fake-model-1"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


def use_model(monkeypatch: pytest.MonkeyPatch, model: FakeModel | Exception) -> None:
    def factory() -> FakeModel:
        if isinstance(model, Exception):
            raise model
        return model

    monkeypatch.setattr(extractors, "model_factory", factory)


def answer(*items: dict[str, Any]) -> str:
    return json.dumps({"candidates": list(items)})


def test_llm_candidates_are_only_drafts_the_checker_filters_invented_ones(
    monkeypatch: pytest.MonkeyPatch, allow: AllowLists
) -> None:
    genuine = {
        "resourceType": "Condition",
        "code": "C50.9",
        "quote": MAIN_DX,
        "date": "2026-10-14",
    }
    invented_quote = {**genuine, "quote": "Pacientka má metastázy v játrech (C50.9)."}
    invented_code = {**genuine, "code": "C79.9"}
    invented_med = {
        "resourceType": "MedicationStatement",
        "code": "L01XA03",
        "quote": "Dříve podán docetaxel v rámci předchozí léčby.",
    }
    invented_value = {
        "resourceType": "Observation",
        "code": "718-7",
        "value": "80",
        "unit": "g/l",
        "quote": "Poslední laboratoř (2026-10-12): Hemoglobin 108 g/l, Neutrofily 1,4 10^9/l.",
    }
    model = FakeModel(answer(genuine, invented_quote, invented_code, invented_med, invented_value))
    use_model(monkeypatch, model)
    extraction = extractors.extract(letter(), allow, "openai")
    assert extraction.mode == "llm"
    assert extraction.extractor == "openai:fake-model-1"
    accepted, rejected = check_all(extraction.raws, letter(), allow)
    assert [(c.resource_type, c.code) for c in accepted] == [("Condition", "C50.9")]
    assert sorted(r.reasons[0] for r in rejected) == [
        "code_not_allowed",
        "code_not_in_quote",
        "quote_not_verbatim",
        "value_not_in_quote",
    ]
    assert model.prompts
    assert letter() in model.prompts[0]
    assert "SYN-0001" in model.prompts[0]  # nur der Dokumenttext (Pseudonym steht im Dokument)


def test_llm_prompt_contains_only_the_document_text(
    monkeypatch: pytest.MonkeyPatch, allow: AllowLists
) -> None:
    model = FakeModel(answer())
    use_model(monkeypatch, model)
    extractors.extract("Datum: 2026-10-14\nCRP 12 mg/l", allow, "openai")
    prompt = model.prompts[0]
    assert prompt.endswith("TEXT:\nDatum: 2026-10-14\nCRP 12 mg/l\n")
    assert "patient" not in prompt.lower().replace("synthetischen medizinischen", "")


@pytest.mark.parametrize(
    "case",
    ["not-json", "wrong-schema", "unavailable", "crash"],
)
def test_llm_failure_falls_back_to_the_template_extractor(
    monkeypatch: pytest.MonkeyPatch, allow: AllowLists, case: str
) -> None:
    models: dict[str, FakeModel | Exception] = {
        "not-json": FakeModel("Das ist kein JSON"),
        "wrong-schema": FakeModel('{"rows": []}'),
        "unavailable": ExtractionUnavailable("openai adapter not configured"),
        "crash": RuntimeError("boom"),
    }
    use_model(monkeypatch, models[case])
    extraction = extractors.extract(lab(), allow, "openai")
    assert extraction.mode == "fallback"
    assert extraction.extractor == "template-regex-v1"
    assert extraction.fallback_reason in {"llm_unavailable", "llm_failed"}
    assert len(check_all(extraction.raws, lab(), allow)[0]) == 7


def test_default_model_factory_is_unavailable_without_gateway_configuration(
    monkeypatch: pytest.MonkeyPatch, allow: AllowLists
) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")  # ohne BASE_URL/API_KEY/MODEL ⇒ nicht verfügbar
    extraction = extractors.extract(lab(), allow, "openai")
    assert extraction.mode == "fallback"
    assert extraction.fallback_reason == "llm_unavailable"


def test_llm_fence_wrapped_answer_is_parsed(
    monkeypatch: pytest.MonkeyPatch, allow: AllowLists
) -> None:
    body = answer(
        {
            "resourceType": "Observation",
            "code": "1988-5",
            "value": 12,
            "unit": "mg/l",
            "quote": "CRP;12;mg/l;0-5",
        }
    )
    use_model(monkeypatch, FakeModel(f"```json\n{body}\n```"))
    extraction = extractors.extract(lab(), allow, "openai")
    accepted, _ = check_all(extraction.raws, lab(), allow)
    assert extraction.mode == "llm"
    assert [c.code for c in accepted] == ["1988-5"]


def test_documents_package_has_no_network_or_dataset_access() -> None:
    root = Path(__file__).resolve().parent / "waechter" / "documents"
    forbidden = ("socket", "urllib", "requests", "http.client", "subprocess", "sqlite3", "pandas")
    for module in root.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        for name in forbidden:
            assert f"import {name}" not in source, module.name
            assert f"from {name}" not in source, module.name


# --- API: Rollen, Grenzen, Upload -----------------------------------------------------------

DOCS = f"{BASE}/patients"


def upload(client: TestClient, patient: str, path: Path = LETTER, name: str | None = None) -> Any:
    return client.post(
        f"{DOCS}/{patient}/documents",
        json={"filename": name or path.name, "text": path.read_text(encoding="utf-8")},
    )


@pytest.fixture
def doctor(seeded_app: FastAPI) -> TestClient:
    return staff(seeded_app, "doctor")


@pytest.fixture
def syn1(seeded_app: FastAPI) -> str:
    return pid(seeded_app, "SYN-0001")


def test_anonymous_gets_401_and_other_roles_403(seeded_app: FastAPI, syn1: str) -> None:
    anon = TestClient(seeded_app, headers=CSRF)
    body = {"filename": "a.txt", "text": "C50.9"}
    assert anon.post(f"{DOCS}/{syn1}/documents", json=body).status_code == 401
    assert anon.get(f"{DOCS}/{syn1}/documents").status_code == 401
    for username in ("patient", "patient2", "user"):
        client = TestClient(seeded_app, headers=CSRF)
        login(client, username)
        assert client.post(f"{DOCS}/{syn1}/documents", json=body).status_code == 403, username
        assert client.get(f"{DOCS}/{syn1}/documents").status_code == 403, username
        decide_url = f"{DOCS}/{syn1}/documents/x/candidates/y"
        assert client.post(decide_url, json={"decision": "confirm"}).status_code == 403


def test_doctor_and_admin_can_upload(seeded_app: FastAPI, syn1: str) -> None:
    for username in ("doctor", "admin"):
        response = upload(staff(seeded_app, username), syn1, LAB, f"{username}.csv")
        assert response.status_code in {200, 201}, response.text


def test_unknown_patient_and_foreign_document_give_404(
    seeded_app: FastAPI, doctor: TestClient, syn1: str
) -> None:
    other = pid(seeded_app, "SYN-0002")
    assert upload(doctor, "no-such-patient").status_code == 404
    document = upload(doctor, syn1).json()
    own = f"{DOCS}/{syn1}/documents/{document['document_id']}"
    foreign = f"{DOCS}/{other}/documents/{document['document_id']}"
    assert doctor.get(own).status_code == 200
    assert doctor.get(foreign).status_code == 404
    assert doctor.get(f"{foreign}/bundle").status_code == 404
    candidate = document["candidates"][0]["candidate_id"]
    assert (
        doctor.post(f"{foreign}/candidates/{candidate}", json={"decision": "confirm"}).status_code
        == 404
    )
    assert doctor.get(f"{DOCS}/{syn1}/documents/unknown").status_code == 404
    assert doctor.post(f"{own}/candidates/unknown", json={"decision": "confirm"}).status_code == 404
    assert doctor.get(f"{DOCS}/{other}/documents").json() == []


def test_non_synthetic_patient_is_refused_with_409(
    seeded_app: FastAPI, doctor: TestClient, syn1: str
) -> None:
    with seeded_app.state.session_factory() as session:
        row = session.get(Patient, syn1)
        assert row is not None
        row.synthetic = False
        session.commit()
    response = upload(doctor, syn1)
    assert response.status_code == 409
    assert response.json()["code"] == "not_synthetic"


def test_size_format_and_content_limits(doctor: TestClient, syn1: str) -> None:
    url = f"{DOCS}/{syn1}/documents"
    big = "A" * 200_001
    assert doctor.post(url, json={"filename": "big.txt", "text": big}).status_code == 413
    limit = "Datum: 2026-10-14\n" + "x" * (200_000 - 18)
    assert doctor.post(url, json={"filename": "limit.txt", "text": limit}).status_code == 201
    umlauts = "ä" * 100_001  # 200.002 Bytes (UTF-8), aber nur 100.001 Zeichen
    assert doctor.post(url, json={"filename": "u.txt", "text": umlauts}).status_code == 413
    assert (
        doctor.post(url, json={"filename": "scan.pdf", "text": "%PDF"}).json()["code"]
        == "pdf_not_supported"
    )
    assert doctor.post(url, json={"filename": "x.exe", "text": "C50.9"}).status_code == 415
    assert doctor.post(url, json={"filename": "e.txt", "text": "  \n "}).status_code == 422
    assert doctor.post(url, json={"filename": "n.txt", "text": "a\x00b"}).status_code == 422
    assert doctor.post(url, json={"filename": "", "text": "x"}).status_code == 422
    assert doctor.post(url, json={"filename": "a.txt"}).status_code == 422
    assert doctor.post(url, json={"filename": "a.txt", "text": "x", "extra": 1}).status_code == 422


def test_upload_returns_checked_candidates_and_rejections(doctor: TestClient, syn1: str) -> None:
    response = upload(doctor, syn1)
    assert response.status_code == 201
    body = response.json()
    assert body["extractor"] == {
        "id": "template-regex-v1",
        "mode": "template",
        "fallback_reason": None,
    }
    assert body["counts"] == {"draft": 5, "confirmed": 0, "discarded": 0, "rejected": 1}
    assert body["sha256"] == hashlib.sha256(letter().encode("utf-8")).hexdigest()
    assert {c["state"] for c in body["candidates"]} == {"draft"}
    condition = next(c for c in body["candidates"] if c["resource_type"] == "Condition")
    assert condition["code"] == "C50.9"
    assert condition["system"] == "http://hl7.org/fhir/sid/icd-10"
    assert "C50.9" in condition["quote"]
    assert body["rejected"] == [
        {
            "resource_type": "Condition",
            "code": "I10",
            "quote": SIDE_DX,
            "reasons": ["code_not_allowed"],
        }
    ]
    assert "text" not in body  # der Dokumenttext wird nicht gespeichert noch ausgeliefert
    listed = doctor.get(f"{DOCS}/{syn1}/documents").json()
    assert [d["document_id"] for d in listed] == [body["document_id"]]


def test_same_document_twice_returns_the_existing_one(doctor: TestClient, syn1: str) -> None:
    first = upload(doctor, syn1, LAB)
    second = upload(doctor, syn1, LAB, "other-name.csv")
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["document_id"] == second.json()["document_id"]


def test_four_parallel_uploads_of_one_document_create_exactly_one(
    seeded_app: FastAPI, syn1: str
) -> None:
    clients = [staff(seeded_app) for _ in range(4)]
    results = run_parallel(lambda i: upload(clients[i], syn1, LAB), 4)
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201], [
        (r.status_code, r.text) for r in results
    ]
    assert len({r.json()["document_id"] for r in results}) == 1
    with seeded_app.state.session_factory() as session:
        stored = session.scalar(select(func.count()).select_from(Document))
    assert stored == 1


def test_llm_path_via_api_records_model_and_rejections(
    monkeypatch: pytest.MonkeyPatch, doctor: TestClient, syn1: str
) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")
    quote = MAIN_DX
    use_model(
        monkeypatch,
        FakeModel(
            answer(
                {"resourceType": "Condition", "code": "C50.9", "quote": quote},
                {"resourceType": "Condition", "code": "C50.9", "quote": "Vymyšlená věta C50.9."},
            )
        ),
    )
    body = upload(doctor, syn1).json()
    assert body["extractor"]["id"] == "openai:fake-model-1"
    assert body["extractor"]["mode"] == "llm"
    assert [c["code"] for c in body["candidates"]] == ["C50.9"]
    assert [r["reasons"] for r in body["rejected"]] == [["quote_not_verbatim"]]


def test_llm_unavailable_via_api_falls_back_and_says_so(
    monkeypatch: pytest.MonkeyPatch, doctor: TestClient, syn1: str
) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")  # kein Gateway konfiguriert
    body = upload(doctor, syn1, LAB).json()
    assert body["extractor"] == {
        "id": "template-regex-v1",
        "mode": "fallback",
        "fallback_reason": "llm_unavailable",
    }
    assert body["counts"]["draft"] == 7


# --- Bestätigung und Export -----------------------------------------------------------------


def candidate_of(document: dict[str, Any], code: str) -> dict[str, Any]:
    return next(c for c in document["candidates"] if c["code"] == code)


def decide(client: TestClient, patient: str, document: str, candidate: str, decision: str) -> Any:
    return client.post(
        f"{DOCS}/{patient}/documents/{document}/candidates/{candidate}",
        json={"decision": decision},
    )


def document_resources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        e["resource"]
        for e in bundle["entry"]
        if any(
            t.get("code") == "document-extraction"
            for t in e["resource"].get("meta", {}).get("tag", [])
        )
    ]


def test_upload_alone_does_not_change_the_patient_export(doctor: TestClient, syn1: str) -> None:
    before = {
        "collection": doctor.get(f"{BASE}/patients/{syn1}/fhir").content,
        "transaction": doctor.get(f"{BASE}/patients/{syn1}/fhir?type=transaction").content,
    }
    assert upload(doctor, syn1).status_code == 201
    assert upload(doctor, syn1, LAB).status_code == 201
    assert doctor.get(f"{BASE}/patients/{syn1}/fhir").content == before["collection"]
    assert (
        doctor.get(f"{BASE}/patients/{syn1}/fhir?type=transaction").content == before["transaction"]
    )


def test_only_confirmed_resources_reach_the_export_with_provenance(
    doctor: TestClient, syn1: str
) -> None:
    document = upload(doctor, syn1).json()
    doc_id = document["document_id"]
    baseline = export(doctor, syn1)
    condition = candidate_of(document, "C50.9")
    discarded = candidate_of(document, "L01CD02")
    response = decide(doctor, syn1, doc_id, condition["candidate_id"], "confirm")
    assert response.status_code == 200, response.text
    assert candidate_of(response.json(), "C50.9")["state"] == "confirmed"
    assert response.json()["counts"] == {"draft": 4, "confirmed": 1, "discarded": 0, "rejected": 1}
    assert decide(doctor, syn1, doc_id, discarded["candidate_id"], "discard").status_code == 200

    bundle = export(doctor, syn1)
    extra = document_resources(bundle)
    assert sorted(r["resourceType"] for r in extra) == ["Condition", "Provenance"]
    assert len(bundle["entry"]) == len(baseline["entry"]) + 2
    [cond] = [r for r in extra if r["resourceType"] == "Condition"]
    assert cond["code"]["coding"] == [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "C50.9"}]
    assert cond["verificationStatus"]["coding"][0]["code"] == "confirmed"
    assert cond["recordedDate"] == "2026-10-14"
    assert {"system": "urn:waechter:review", "code": "confirmed"} in cond["meta"]["tag"]
    [prov] = [r for r in extra if r["resourceType"] == "Provenance"]
    sha = hashlib.sha256(letter().encode("utf-8")).hexdigest()
    assert prov["target"] == [{"reference": f"urn:uuid:{cond['id']}"}]
    assert prov["agent"][0]["who"]["display"] == "template-regex-v1"
    assert prov["agent"][1]["type"]["coding"][0]["code"] == "verifier"
    assert prov["agent"][1]["who"] == {"display": "clinician"}  # Rolle, kein Name
    assert prov["entity"][0]["what"]["identifier"] == {
        "system": "urn:waechter:document-sha256",
        "value": sha,
    }
    assert prov["entity"][1]["what"]["display"] == condition["quote"]
    # alles andere (verworfen, unentschieden) fehlt
    codes = json.dumps(bundle)
    assert "L01CD02" not in codes
    assert "L01BC06" not in codes
    assert "718-7" not in codes


def test_confirmed_export_is_deterministic_and_references_resolve(
    doctor: TestClient, syn1: str
) -> None:
    document = upload(doctor, syn1, LAB).json()
    for candidate in document["candidates"][:3]:
        assert (
            decide(
                doctor, syn1, document["document_id"], candidate["candidate_id"], "confirm"
            ).status_code
            == 200
        )
    first = doctor.get(f"{BASE}/patients/{syn1}/fhir").content
    assert first == doctor.get(f"{BASE}/patients/{syn1}/fhir").content
    bundle = json.loads(first)
    ids = {e["fullUrl"] for e in bundle["entry"]}
    assert all(r in ids for r in references(bundle))
    observations = [r for r in document_resources(bundle) if r["resourceType"] == "Observation"]
    assert len(observations) == 3
    hemoglobin = next(o for o in observations if o["code"]["coding"][0]["code"] == "718-7")
    assert hemoglobin["status"] == "final"
    assert hemoglobin["valueQuantity"] == {
        "value": 108.0,
        "unit": "g/l",
        "system": "http://unitsofmeasure.org",
        "code": "g/L",
    }
    assert hemoglobin["effectiveDateTime"] == "2026-10-14"
    tx = json.loads(doctor.get(f"{BASE}/patients/{syn1}/fhir?type=transaction").content)
    puts = [
        e for e in tx["entry"] if e["resource"]["resourceType"] in {"Observation", "Provenance"}
    ]
    assert any(e["resource"]["id"] == hemoglobin["id"] for e in puts)
    assert all(e["request"]["method"] == "PUT" for e in tx["entry"])


def test_draft_bundle_is_preliminary_until_confirmed(doctor: TestClient, syn1: str) -> None:
    document = upload(doctor, syn1).json()
    doc_id = document["document_id"]
    url = f"{DOCS}/{syn1}/documents/{doc_id}/bundle"
    response = doctor.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/fhir+json")
    bundle = json.loads(response.content)
    assert bundle["type"] == "collection"
    assert bundle["entry"][0]["resource"]["resourceType"] == "Patient"
    extra = document_resources(bundle)
    assert len([r for r in extra if r["resourceType"] == "Provenance"]) == 5
    [cond] = [r for r in extra if r["resourceType"] == "Condition"]
    assert cond["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
    observation = next(r for r in extra if r["resourceType"] == "Observation")
    assert observation["status"] == "preliminary"
    assert all(
        {"system": "urn:waechter:review", "code": "unconfirmed"} in r["meta"]["tag"] for r in extra
    )
    ids = {e["fullUrl"] for e in bundle["entry"]}
    assert all(r in ids for r in references(bundle))
    # nach dem Verwerfen verschwindet der Kandidat aus dem Entwurf
    assert (
        decide(
            doctor, syn1, doc_id, candidate_of(document, "C50.9")["candidate_id"], "discard"
        ).status_code
        == 200
    )
    again = json.loads(doctor.get(url).content)
    assert "Condition" not in {r["resourceType"] for r in document_resources(again)}


def test_a_decision_cannot_be_changed_afterwards(doctor: TestClient, syn1: str) -> None:
    document = upload(doctor, syn1).json()
    candidate = candidate_of(document, "C50.9")["candidate_id"]
    doc_id = document["document_id"]
    assert decide(doctor, syn1, doc_id, candidate, "confirm").status_code == 200
    again = decide(doctor, syn1, doc_id, candidate, "discard")
    assert again.status_code == 409
    assert again.json()["code"] == "already_decided"
    assert decide(doctor, syn1, doc_id, candidate, "confirm").status_code == 409
    assert (
        doctor.post(
            f"{DOCS}/{syn1}/documents/{doc_id}/candidates/{candidate}", json={"decision": "maybe"}
        ).status_code
        == 422
    )


def test_four_parallel_confirmations_succeed_exactly_once(seeded_app: FastAPI, syn1: str) -> None:
    owner = staff(seeded_app)
    document = upload(owner, syn1).json()
    candidate = candidate_of(document, "C50.9")["candidate_id"]
    clients = [staff(seeded_app) for _ in range(4)]
    results = run_parallel(
        lambda i: decide(clients[i], syn1, document["document_id"], candidate, "confirm"), 4
    )
    assert sorted(r.status_code for r in results) == [200, 409, 409, 409], [
        (r.status_code, r.text) for r in results
    ]
    bundle = export(owner, syn1)
    assert len(resources(bundle, "Condition")) == 2  # Stammdiagnose + bestätigte Dokumentdiagnose
    with seeded_app.state.session_factory() as session:
        actions = session.scalars(
            select(AuditEvent.action).where(AuditEvent.action == "confirm_document_resource")
        ).all()
    assert len(actions) == 1


def test_parallel_decisions_on_different_resources_all_succeed(
    seeded_app: FastAPI, syn1: str
) -> None:
    owner = staff(seeded_app)
    document = upload(owner, syn1, LAB).json()
    candidates = [c["candidate_id"] for c in document["candidates"]][:4]
    clients = [staff(seeded_app) for _ in candidates]
    results = run_parallel(
        lambda i: decide(clients[i], syn1, document["document_id"], candidates[i], "confirm"), 4
    )
    assert [r.status_code for r in results] == [200, 200, 200, 200], [r.text for r in results]
    final = owner.get(f"{DOCS}/{syn1}/documents/{document['document_id']}").json()
    assert final["counts"]["confirmed"] == 4
    assert final["counts"]["draft"] == 3


def test_audit_records_the_actions_without_document_content(
    seeded_app: FastAPI, doctor: TestClient, syn1: str
) -> None:
    document = upload(doctor, syn1).json()
    candidate = candidate_of(document, "C50.9")
    decide(doctor, syn1, document["document_id"], candidate["candidate_id"], "confirm")
    with seeded_app.state.session_factory() as session:
        events = session.scalars(
            select(AuditEvent).where(AuditEvent.target_type == "document").order_by(AuditEvent.at)
        ).all()
    assert [e.action for e in events] == ["upload_document", "confirm_document_resource"]
    dump = json.dumps([e.details_json for e in events])
    assert "karcinom" not in dump
    assert "C50.9" not in dump
    assert "SYN-0001" not in dump
    assert events[0].details_json == {"candidates": 5, "rejected": 1, "mode": "template"}


def test_document_text_is_not_stored(seeded_app: FastAPI, doctor: TestClient, syn1: str) -> None:
    upload(doctor, syn1)
    with seeded_app.state.session_factory() as session:
        [row] = session.scalars(select(Document)).all()
        stored = json.dumps(
            [row.candidates_json, row.rejected_json, row.filename], ensure_ascii=False
        )
    assert "Pacientka: pseudonym" not in stored
    assert "Dříve podán" in stored


def test_service_layer_has_no_http_dependency() -> None:
    source = (Path(documents_service.__file__)).read_text(encoding="utf-8")
    assert "fastapi" not in source


def test_dump_bundles_for_validator(doctor: TestClient, syn1: str) -> None:
    """Schreibt Entwurf und Export (collection/transaction) nach `T21_DUMP_DIR` (HAPI-Lauf)."""
    target = os.environ.get("T21_DUMP_DIR")
    if not target:
        pytest.skip("T21_DUMP_DIR not set")
    folder = Path(target)
    folder.mkdir(parents=True, exist_ok=True)
    for path in (LETTER, LAB):
        document = upload(doctor, syn1, path).json()
        stem = path.stem
        draft = doctor.get(f"{DOCS}/{syn1}/documents/{document['document_id']}/bundle").content
        (folder / f"{stem}-draft.json").write_bytes(draft)
        for candidate in document["candidates"]:
            decide(doctor, syn1, document["document_id"], candidate["candidate_id"], "confirm")
    collection = doctor.get(f"{BASE}/patients/{syn1}/fhir").content
    transaction = doctor.get(f"{BASE}/patients/{syn1}/fhir?type=transaction").content
    (folder / "export-collection.json").write_bytes(collection)
    (folder / "export-transaction.json").write_bytes(transaction)


# --- A3-Befunde F-01 bis F-04 (Nachbesserung) --------------------------------------------------


def test_lab_value_must_belong_to_the_named_test_not_to_its_neighbour(allow: AllowLists) -> None:
    """F-01: 'Natrium 140; Kalium 4,2' ⇒ 4,2 gehört zu Kalium, nicht zu Natrium."""
    text = "Natrium 140 mmol/l; Kalium 4,2 mmol/l\n"
    wrong = raw("Observation", "2951-2", text.strip(), value="4,2", unit="mmol/l")
    assert check(wrong, text, allow) == (None, ["value_not_in_quote"])
    right = raw("Observation", "2823-3", text.strip(), value="4,2", unit="mmol/l")
    candidate, reasons = check(right, text, allow)
    assert reasons == []
    assert candidate is not None
    assert candidate.value == "4.2"


def test_lab_binding_with_a_shared_unit_family(allow: AllowLists) -> None:
    text = "Trombocyty 250 x10^9/l, Leukocyty 4,1 x10^9/l\n"
    wrong = raw("Observation", "777-3", text.strip(), value="4,1", unit="x10^9/l")
    assert check(wrong, text, allow)[0] is None
    right = raw("Observation", "6690-2", text.strip(), value="4,1", unit="x10^9/l")
    assert check(right, text, allow)[0] is not None


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("Bez známek malignity: C61 vyloučeno.", "context_negated"),
        ("Karzinom C61 wurde ausgeschlossen.", "context_negated"),
        ("No evidence of C34.9.", "context_negated"),
        ("Kein Nachweis von C50.9", "context_negated"),
        ("Rodinná anamnéza: matka C50.9.", "context_family"),
        ("Familienanamnese: Mutter mit C50.9", "context_family"),
        ("Family history: sister, C50.9", "context_family"),
    ],
)
def test_f02_codes_from_negated_or_family_lines_are_not_candidates(
    allow: AllowLists, line: str, reason: str
) -> None:
    text = line + "\n"
    accepted, rejected = check_all(extractors.extract_template(text, allow), text, allow)
    assert [c for c in accepted if c.resource_type == "Condition"] == []
    assert [r.reasons for r in rejected if r.resource_type == "Condition"] == [(reason,)]


def test_f02_negated_medication_is_not_a_candidate_but_a_plain_mention_is(
    allow: AllowLists,
) -> None:
    negated = "Kein Nachweis einer Gabe von Docetaxel."
    plain = "Dříve podán docetaxel v rámci předchozí léčby."
    for line, expected in ((negated, 0), (plain, 1)):
        text = line + "\n"
        accepted, _ = check_all(extractors.extract_template(text, allow), text, allow)
        assert len([c for c in accepted if c.resource_type == "MedicationStatement"]) == expected


def test_f02_normal_diagnosis_lines_are_still_proposed(allow: AllowLists) -> None:
    text = "Hlavní diagnóza: C50.9\nDiagnosis: C61, Zustand nach Operation\n"
    accepted, _ = check_all(extractors.extract_template(text, allow), text, allow)
    assert sorted(c.code for c in accepted) == ["C50.9", "C61"]


@pytest.mark.parametrize("value", ["1e999999999", "-1e999999999", "1e-999999999", "9" * 40])
def test_f03_extreme_values_are_rejected_without_an_exception(
    allow: AllowLists, value: str
) -> None:
    quote = "Hb 12 g/l"
    candidate, reasons = check(
        raw("Observation", "718-7", quote, value=value, unit="g/l"), quote, allow
    )
    assert candidate is None
    assert reasons == ["value_invalid"]


def test_f03_extreme_value_in_the_llm_answer_does_not_break_the_upload(
    monkeypatch: pytest.MonkeyPatch, doctor: TestClient, syn1: str
) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")
    body = answer(
        {
            "resourceType": "Observation",
            "code": "718-7",
            "value": "1e999999999",
            "unit": "g/l",
            "quote": "Hemoglobin;108;g/l;120-160",
        }
    )
    use_model(monkeypatch, FakeModel(body))
    response = upload(doctor, syn1, LAB)
    assert response.status_code == 201, response.text
    assert [r["reasons"] for r in response.json()["rejected"]] == [["value_invalid"]]


def test_f04_a_large_lab_csv_is_checked_in_linear_time(allow: AllowLists) -> None:
    rows = "".join(f"Hemoglobin {100 + i % 900} g/l\n" for i in range(8000))
    text = "Datum: 2026-10-17\n" + rows
    assert len(text.encode()) > 150_000
    started = time.perf_counter()
    raws = extractors.extract_template(text, allow)
    accepted, rejected = check_all(raws, text, allow)
    assert time.perf_counter() - started < 3.0
    assert len(accepted) == 200
    assert rejected[-1].reasons == ("too_many_candidates",)


def test_f04_verifier_normalizes_the_document_once_not_per_candidate(
    monkeypatch: pytest.MonkeyPatch, allow: AllowLists
) -> None:
    from waechter.documents import verify
    from waechter.knowledge.sources import normalize as original

    calls: list[int] = []

    def counting(text: str) -> str:
        calls.append(len(text))
        return original(text)

    monkeypatch.setattr(verify, "normalize", counting, raising=True)
    text = "Datum: 2026-10-17\n" + "".join(f"Hemoglobin {100 + i} g/l\n" for i in range(50))
    check_all(extractors.extract_template(text, allow), text, allow)
    assert sum(1 for size in calls if size >= len(text) - 1) == 1
