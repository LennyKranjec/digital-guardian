"""T-19: Wissensbasis-Pipeline SmPC ⇒ Extraktion ⇒ deterministischer Prüfer ⇒ FHIR R4.

Alles offline: Quelltexte und Matrix sind erfundene Testfixtures (`fixtures/knowledge/`), das
Sprachmodell ist ein Fake (oder ein gesperrtes Gateway). Echter Modelllauf: NOT RUN (kein
`MODEL_DEPLOYMENT`). Die HAPI-Prüfung läuft außerhalb von pytest (siehe Handoff).
"""

import ast
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from waechter.fhir import builder as fhir_builder
from waechter.knowledge import cli, sources, verify
from waechter.knowledge import extract as extraction
from waechter.knowledge import fhir as kfhir
from waechter.knowledge.verify import AeRow

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "knowledge"
BACKEND = Path(__file__).resolve().parent
PACKAGE = BACKEND / "waechter" / "knowledge"
CTCAE = {"Nausea", "Fatigue", "Diarrhea", "CTCAE-NAUSEA"}
GENERATED_AT = "2026-10-17T09:00:00+02:00"


def document(suffix: str = "txt") -> sources.SourceDocument:
    return sources.load_source(
        FIXTURES / f"TESTDOC-A.{suffix}",
        "TESTDOC-A",
        url="https://example.invalid/a",
        retrieved="2026-10-16",
    )


def section_text() -> str:
    return document().section("4.8").text


def row(**changes: str) -> AeRow:
    base: dict[str, str] = {
        "substance_id": "TESTSTOFF-A",
        "document": "TESTDOC-A",
        "document_url": "https://example.invalid/a",
        "section": "4.8",
        "retrieved": "2026-10-16",
        "original_term": "Nausea",
        "frequency_class": "very common",
        "ctcae_v6_term": "Nausea",
        "status": "verified",
        "extraction": "manual",
    }
    base.update(changes)
    return AeRow(**base)


def llm_row(**changes: str) -> AeRow:
    base = {
        "original_term": "Nausea",
        "frequency_class": "very common",
        "ctcae_v6_term": "",
        "status": "unverified",
        "extraction": "llm:fake-1",
        "evidence": "Very common (≥ 1/10): Nausea, fatigue",
    }
    base.update(changes)
    return row(**base)


# --- Quellen ----------------------------------------------------------------------------------


def test_section_4_8_is_cut_before_4_9_and_after_the_real_heading() -> None:
    text = section_text()
    assert text.startswith("4.8 Undesirable effects\nSummary of the safety profile")
    assert "Very common" in text
    assert "Overdose" not in text
    assert "Rare events" not in text
    assert "ability to drive" not in text


def test_table_of_contents_entry_is_not_taken_for_the_section() -> None:
    text = section_text()
    assert "12\n" not in text.split("\n")[0]  # nicht die Inhaltsverzeichniszeile "…effects 12"
    assert len(text) > 200


def test_html_and_text_give_the_same_normalized_section() -> None:
    a = sources.normalize(document("txt").section("4.8").text)
    b = sources.normalize(document("html").section("4.8").text)
    assert a == b
    assert "var x" not in b
    assert "color: red" not in b


def test_hyphenation_at_line_end_is_resolved() -> None:
    assert "Diarrhoea, rash" in sources.normalize(section_text())


def test_normalize_unifies_whitespace_but_keeps_case() -> None:
    assert sources.normalize("Very\u00a0common  (≥\n1/10)") == "Very common (≥ 1/10)"
    assert sources.normalize("nausea") != sources.normalize("Nausea")


def test_missing_section_and_unsupported_format_are_errors(tmp_path: Path) -> None:
    with pytest.raises(sources.SourceError, match="not found"):
        document().section("5.1")
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with pytest.raises(sources.SourceError, match="unsupported"):
        sources.load_source(pdf, "X")
    with pytest.raises(sources.SourceError, match="not readable"):
        sources.load_source(tmp_path / "missing.txt", "X")
    with pytest.raises(sources.SourceError, match="invalid section"):
        sources.find_section("text", "four")


# --- Prüfer: Modellzeilen ---------------------------------------------------------------------


def test_a_correct_model_row_is_verified_with_confirmed_frequency() -> None:
    verdict = verify.verify_extracted(llm_row(), section_text(), CTCAE)
    assert verdict.status == "verified"
    assert verdict.checks == {
        "evidence": "found",
        "term": "in_evidence",
        "frequency_enum": "valid",
        "frequency_context": "confirmed",
    }


def test_evidence_with_line_break_and_double_spaces_still_matches() -> None:
    evidence = "Common (≥ 1/100 to < 1/10):  Diarrhoea,\nrash"
    verdict = verify.verify_extracted(
        llm_row(original_term="Diarrhoea", frequency_class="common", evidence=evidence),
        section_text(),
        CTCAE,
    )
    assert verdict.status == "verified"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"evidence": "Very common (≥ 1/10): Vomiting, fatigue"}, "evidence_not_in_source"),
        ({"evidence": "very common (≥ 1/10): nausea, fatigue"}, "evidence_not_in_source"),  # Fall
        ({"evidence": ""}, "evidence_not_in_source"),
        ({"evidence": "Nausea, fatigue"}, None),  # echte Teilmenge des Textes ⇒ Beleg ok
        ({"original_term": "Vomiting"}, "term_not_in_evidence"),
        ({"original_term": ""}, "term_not_in_evidence"),
        ({"frequency_class": "often"}, "frequency_class_invalid"),
        ({"frequency_class": "Very common"}, "frequency_class_invalid"),  # nur Aufzählungswerte
        ({"frequency_class": "rare"}, "frequency_contradicts_source"),
        ({"frequency_class": "common"}, "frequency_contradicts_source"),
    ],
)
def test_the_checker_rejects_unsupported_rows(changes: dict[str, str], reason: str | None) -> None:
    verdict = verify.verify_extracted(llm_row(**changes), section_text(), CTCAE)
    if reason is None:
        assert verdict.status == "verified"
    else:
        assert verdict.status == "rejected"
        assert reason in verdict.reasons


def test_frequency_check_uses_the_nearest_heading_before_the_evidence() -> None:
    # "Palpitations" steht unter "Frequency not known", nicht unter "Uncommon"
    evidence = "Frequency not known: Palpitations"
    ok = llm_row(original_term="Palpitations", frequency_class="not known", evidence=evidence)
    bad = llm_row(original_term="Palpitations", frequency_class="uncommon", evidence=evidence)
    assert verify.verify_extracted(ok, section_text(), CTCAE).status == "verified"
    assert verify.verify_extracted(bad, section_text(), CTCAE).status == "rejected"


def test_frequency_context_is_not_checkable_without_a_heading() -> None:
    text = "4.8 Undesirable effects\nNausea, vomiting"
    verdict = verify.verify_extracted(llm_row(evidence="Nausea, vomiting"), text, CTCAE)
    assert verdict.status == "verified"
    assert verdict.checks["frequency_context"] == "not_checkable"


def test_a_term_inside_prose_is_not_a_list_item_and_is_rejected() -> None:
    """Begriffe zählen nur als ganzer Aufzählungspunkt (T-19G): Fließtext liefert keinen Beleg."""
    text = "4.8 Undesirable effects\nPatients reported Nausea in studies."
    verdict = verify.verify_extracted(llm_row(evidence="reported Nausea in studies"), text, CTCAE)
    assert verdict.status == "rejected"
    assert "term_not_in_evidence" in verdict.reasons


BOLEST = (
    "4.8 Nežádoucí účinky\n"
    "Velmi časté: neutropenie, bolest břicha\n"
    "Časté: bolest hlavy, bolest\n"
    "Méně časté: pankreatitida\n"
)


def bolest(term: str, cls: str, evidence: str) -> verify.Verdict:
    candidate = llm_row(original_term=term, frequency_class=cls, evidence=evidence)
    return verify.verify_extracted(candidate, BOLEST, set())


def test_a_term_does_not_borrow_the_frequency_of_a_longer_term() -> None:
    """A3 F-02: `bolest` steht eigenständig unter Časté, `bolest břicha` unter Velmi časté."""
    assert bolest("bolest", "very common", "bolest břicha").status == "rejected"
    assert bolest("bolest břicha", "very common", "bolest břicha").status == "verified"
    assert bolest("bolest", "common", "bolest hlavy, bolest").status == "verified"


def test_the_frequency_is_read_where_the_term_stands_not_at_the_first_evidence_hit() -> None:
    """Belegstelle `bolest` kommt auch in `bolest břicha` (Velmi časté) vor; zählt nur der Punkt."""
    assert bolest("bolest", "common", "bolest").checks["frequency_context"] == "confirmed"
    wrong = bolest("bolest", "very common", "bolest")
    assert wrong.status == "rejected"
    assert "frequency_contradicts_source" in wrong.reasons


def test_a_quote_may_join_lines_with_a_space_but_boundaries_come_from_the_source() -> None:
    joined = bolest("bolest", "common", "Časté: bolest hlavy, bolest Méně časté: pankreatitida")
    assert joined.status == "verified"
    # ein Zitat darf einen Begriff nicht durch Abschneiden zum ganzen Punkt machen
    assert bolest("bolest", "common", "bolest h").status == "rejected"


def test_the_manual_path_uses_whole_items_and_the_term_location_too() -> None:
    manual = row(original_term="bolest", frequency_class="very common", ctcae_v6_term="")
    assert verify.verify_manual(manual, set(), BOLEST).status == "rejected"
    ok = row(original_term="bolest", frequency_class="common", ctcae_v6_term="")
    assert verify.verify_manual(ok, set(), BOLEST).status == "verified"
    alone = row(original_term="bolest břicha", frequency_class="very common", ctcae_v6_term="")
    assert verify.verify_manual(alone, set(), BOLEST).status == "verified"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Velmi časté: nauzea", "very common"),
        ("Časté: průjem", "common"),
        ("Méně časté: alergie", "uncommon"),
        ("Vzácné: x", "rare"),
        ("Velmi vzácné: x", "very rare"),
        ("Není známo: x", "not known"),
        ("Sehr häufig: Übelkeit", "very common"),
        ("Häufig: Durchfall", "common"),
        ("Gelegentlich: x", "uncommon"),
        ("Selten: x", "rare"),
        ("Sehr selten: x", "very rare"),
        ("Nicht bekannt: x", "not known"),
        ("Very common: x", "very common"),
        ("Uncommon: x", "uncommon"),  # nicht "common"
        ("Very rare: x", "very rare"),  # nicht "rare"
        ("Frequency not known: x", "not known"),
        ("keine Überschrift hier", None),
        ("Uncommonly reported", None),  # Wortgrenze
    ],
)
def test_frequency_headings_in_three_languages(text: str, expected: str | None) -> None:
    assert verify.frequency_in_context(text, len(text)) == expected


def test_ctcae_term_outside_the_list_makes_the_row_unverified_and_drops_the_mapping() -> None:
    candidate = llm_row(ctcae_v6_term="Invented term")
    verdict = verify.verify_extracted(candidate, section_text(), CTCAE)
    assert verdict.status == "unverified"
    assert verdict.reasons == ("ctcae_not_in_list",)
    assert verify.with_status(candidate, verdict).ctcae_v6_term == ""
    known = verify.verify_extracted(llm_row(ctcae_v6_term="nausea"), section_text(), CTCAE)
    assert known.status == "verified"  # Groß-/Kleinschreibung der Listenbegriffe egal


# --- Prüfer: manuelle Zeilen und CSV ---------------------------------------------------------


def test_manual_rows_of_the_fixture_matrix_pass() -> None:
    rows = verify.read_matrix(FIXTURES / "ae_matrix_fixture.csv")
    assert len(rows) == 5
    verdicts = [verify.verify_manual(r, CTCAE) for r in rows]
    # die ersten drei Zeilen sind verified (CTCAE-Begriff in der Liste), die letzten zwei
    # sind in der Matrix als unverified geführt und bleiben es
    assert [v.status for v in verdicts] == [
        "verified",
        "verified",
        "verified",
        "unverified",
        "unverified",
    ]
    assert verdicts[0].checks["source_text"] == "not_checked"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"substance_id": ""}, "missing_substance_id"),
        ({"original_term": " "}, "missing_original_term"),
        ({"frequency_class": "often"}, "frequency_class_invalid"),
        ({"section": "4,8"}, "section_invalid"),
        ({"retrieved": "16.10.2026"}, "retrieved_invalid"),
        ({"status": "ok"}, "status_invalid"),
        ({"extraction": "auto"}, "extraction_invalid"),
        ({"extraction": "llm:"}, "extraction_invalid"),
        ({"patient_reportable": "maybe"}, "patient_reportable_invalid"),
    ],
)
def test_manual_row_schema_violations_are_rejected(changes: dict[str, str], reason: str) -> None:
    verdict = verify.verify_manual(row(**changes), CTCAE)
    assert verdict.status == "rejected"
    assert reason in verdict.reasons


def test_manual_row_accepts_llm_extraction_marker_and_keeps_unverified_status() -> None:
    assert verify.verify_manual(row(extraction="llm:gpt-test-1"), CTCAE).status == "verified"
    assert verify.verify_manual(row(status="unverified"), CTCAE).status == "unverified"


def test_manual_row_is_checked_against_the_source_text_when_given() -> None:
    text = section_text()
    assert verify.verify_manual(row(), CTCAE, text).checks["source_text"] == "term_found"
    missing = verify.verify_manual(row(original_term="Vomiting"), CTCAE, text)
    assert missing.status == "rejected"
    assert "term_not_in_source" in missing.reasons
    wrong = verify.verify_manual(row(frequency_class="rare"), CTCAE, text)
    assert wrong.status == "rejected"
    assert "frequency_contradicts_source" in wrong.reasons
    lower = verify.verify_manual(row(original_term="fatigue"), CTCAE, text)
    assert lower.status == "verified"  # Begriff lokalisiert (Groß-/Kleinschreibung egal)


def test_matrix_round_trip_and_column_checks(tmp_path: Path) -> None:
    rows = verify.read_matrix(FIXTURES / "ae_matrix_fixture.csv")
    target = tmp_path / "m.csv"
    verify.write_matrix(target, rows)
    assert verify.read_matrix(target) == rows
    assert target.read_text(encoding="utf-8").splitlines()[0].split(",") == list(verify.COLUMNS)
    broken = tmp_path / "b.csv"
    broken.write_text("substance_id,original_term\nX,Y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        verify.read_matrix(broken)
    extra = tmp_path / "e.csv"
    header = ",".join([*verify.COLUMNS, "surprise"])
    extra.write_text(f"{header}\n" + "," * len(verify.COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown columns"):
        verify.read_matrix(extra)


# --- Extraktion mit Fake-Modell ---------------------------------------------------------------


class FakeModel:
    model = "fake-1"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answer


def answer(*rows: dict[str, Any]) -> str:
    return json.dumps({"rows": list(rows)}, ensure_ascii=False)


GOOD = {
    "original_term": "Nausea",
    "frequency_class": "very common",
    "evidence": "Very common (≥ 1/10): Nausea, fatigue",
    "ctcae_v6_term": None,
}


def test_run_extraction_keeps_verified_rows_and_reports_rejections() -> None:
    hallucinated = {**GOOD, "original_term": "Hair loss", "evidence": "Common: Hair loss"}
    wrong_class = {
        **GOOD,
        "original_term": "Rash",
        "frequency_class": "rare",
        "evidence": "Common (≥ 1/100 to < 1/10): Diarrhoea, rash",
    }
    duplicate = dict(GOOD)
    mapped = {**GOOD, "original_term": "Fatigue", "ctcae_v6_term": "Fatigue"}
    mapped["evidence"] = "Very common (≥ 1/10): Nausea, fatigue"
    model = FakeModel(answer(GOOD, hallucinated, wrong_class, duplicate, mapped))
    result = extraction.run_extraction(document(), "4.8", "TESTSTOFF-A", model, CTCAE)
    assert [r.original_term for r in result.rows] == ["Nausea", "Fatigue"]  # Duplikat entfällt
    assert {r.original_term: r.reasons for r in result.rejected} == {
        "Hair loss": ("evidence_not_in_source",),
        "Rash": ("frequency_contradicts_source",),
    }
    fatigue = result.rows[1]  # Begriff im Beleg klein geschrieben, Zuordnung steht in der Liste
    assert (fatigue.original_term, fatigue.ctcae_v6_term, fatigue.status) == (
        "Fatigue",
        "Fatigue",
        "verified",
    )
    kept = result.rows[0]
    assert kept.extraction == "llm:fake-1"
    assert kept.document == "TESTDOC-A"
    assert kept.section == "4.8"
    assert kept.retrieved == "2026-10-16"
    assert kept.status == "verified"
    assert kept.evidence == GOOD["evidence"]
    assert result.model == "fake-1"
    assert result.prompt_version == extraction.PROMPT_VERSION
    assert len(model.prompts) == 1


def test_prompt_contains_only_the_section_and_the_closed_schema() -> None:
    model = FakeModel(answer())
    extraction.run_extraction(document(), "4.8", "TESTSTOFF-A", model, CTCAE)
    prompt = model.prompts[0]
    assert "Very common (≥ 1/10): Nausea, fatigue" in prompt
    assert "Overdose" not in prompt
    assert "ability to drive" not in prompt
    for value in verify.FREQUENCY_CLASSES:
        assert f'"{value}"' in prompt
    assert re.search(r"SYN-\d{4}|patient", prompt, re.IGNORECASE) is None
    once = extraction.run_extraction(document(), "4.8", "TESTSTOFF-A", FakeModel(answer()), CTCAE)
    twice = extraction.run_extraction(document(), "4.8", "TESTSTOFF-A", FakeModel(answer()), CTCAE)
    assert once.prompt_sha256 == twice.prompt_sha256  # deterministisch


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("not json at all", "answer_not_json"),
        ("[1, 2]", "answer_schema_invalid"),
        ('{"rows": "x"}', "answer_schema_invalid"),
        ('{"rows": [], "extra": 1}', "answer_schema_invalid"),
    ],
)
def test_unparseable_answers_yield_no_rows_and_an_error(text: str, error: str) -> None:
    candidates, errors = extraction.parse_answer(text)
    assert candidates == []
    assert errors == [error]


def test_parse_answer_accepts_a_fenced_block_and_drops_malformed_rows_individually() -> None:
    fenced = (
        "```json\n"
        + answer(
            GOOD,
            {**GOOD, "surprise": "x"},  # unbekanntes Feld
            {"original_term": "x"},  # Pflichtfelder fehlen
            {**GOOD, "frequency_class": 3},  # falscher Typ
            {**GOOD, "evidence": "x" * (extraction.MAX_EVIDENCE + 1)},
            {**GOOD, "ctcae_v6_term": 7},
        )
        + "\n```"
    )
    candidates, errors = extraction.parse_answer(fenced)
    assert [c.original_term for c in candidates] == ["Nausea"]
    assert errors == [
        "row_1_schema_invalid",
        "row_2_schema_invalid",
        "row_3_types_invalid",
        "row_4_evidence_invalid",
        "row_5_types_invalid",
    ]


def test_parse_answer_limits_the_number_of_rows() -> None:
    many = answer(*([GOOD] * (extraction.MAX_ROWS + 5)))
    candidates, errors = extraction.parse_answer(many)
    assert len(candidates) == extraction.MAX_ROWS
    assert errors == ["too_many_rows"]


# --- Adapter-Brücke (kein Netz) ---------------------------------------------------------------


@pytest.mark.parametrize("mode", [None, "template", "cached", "unknown"])
def test_without_the_openai_mode_the_llm_run_is_not_run(
    monkeypatch: pytest.MonkeyPatch, mode: str | None
) -> None:
    monkeypatch.delenv("WAECHTER_LLM", raising=False)
    if mode:
        monkeypatch.setenv("WAECHTER_LLM", mode)
    with pytest.raises(extraction.ExtractionUnavailable, match="NOT RUN"):
        extraction.AdapterModel()


def test_openai_mode_without_configuration_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")
    for name in ("BASE_URL", "API_KEY", "MODEL"):
        monkeypatch.delenv(f"WAECHTER_LLM_{name}", raising=False)
    with pytest.raises(extraction.ExtractionUnavailable, match="not configured"):
        extraction.AdapterModel()


class Gateway:
    """Ersetzt `adapters._urlopen`: liefert eine Chat/Responses-Antwort ohne Netz."""

    def __init__(self, text: str | None) -> None:
        self.text = text
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float = 0) -> Any:
        import urllib.error

        self.requests.append(request)
        if self.text is None:
            raise urllib.error.HTTPError(request.full_url, 404, "DeploymentNotFound", None, None)  # type: ignore[arg-type]
        body = json.dumps({"output_text": self.text}).encode()

        class Response(io.BytesIO):
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return Response(body)


def configure_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAECHTER_LLM", "openai")
    monkeypatch.setenv("WAECHTER_LLM_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("WAECHTER_LLM_API_KEY", "schluessel-123")
    monkeypatch.setenv("WAECHTER_LLM_MODEL", "fake-deployment")


def test_adapter_model_runs_the_pipeline_through_a_mocked_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from waechter.llm import adapters

    configure_openai(monkeypatch)
    gateway = Gateway(answer(GOOD))
    monkeypatch.setattr(adapters, "_urlopen", gateway)
    model = extraction.AdapterModel()
    assert model.model == "fake-deployment"
    result = extraction.run_extraction(document(), "4.8", "TESTSTOFF-A", model, CTCAE)
    assert [r.extraction for r in result.rows] == ["llm:fake-deployment"]
    assert len(gateway.requests) >= 1
    assert "schluessel-123" not in repr(model)
    assert "schluessel-123" not in str(result)


def test_gateway_failure_means_not_run_instead_of_a_silent_substitute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from waechter.llm import adapters

    configure_openai(monkeypatch)
    monkeypatch.setattr(adapters, "_urlopen", Gateway(None))  # 404 DeploymentNotFound
    model = extraction.AdapterModel()
    with pytest.raises(extraction.ExtractionUnavailable, match="model call failed"):
        extraction.run_extraction(document(), "4.8", "TESTSTOFF-A", model, CTCAE)


# --- FHIR -------------------------------------------------------------------------------------


def fixture_rows() -> list[AeRow]:
    return [
        verify.with_status(r, verify.verify_manual(r, CTCAE))
        for r in verify.read_matrix(FIXTURES / "ae_matrix_fixture.csv")
    ]


def substances() -> dict[str, kfhir.Substance]:
    return kfhir.load_substances(FIXTURES / "substances_fixture.yaml")


def bundle(bundle_type: str = "collection") -> dict[str, Any]:
    return kfhir.build_bundle(fixture_rows(), substances(), GENERATED_AT, bundle_type)


def of_type(data: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e["resource"] for e in data["entry"] if e["resource"]["resourceType"] == kind]


def refs(node: Any) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "reference" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(refs(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(refs(value))
    return found


def test_bundle_has_one_medication_and_effect_plus_provenance_per_row() -> None:
    data = bundle()
    assert data["type"] == "collection"
    assert data["timestamp"] == GENERATED_AT
    assert len(of_type(data, "Medication")) == 1
    assert len(of_type(data, "MedicinalProductUndesirableEffect")) == 5
    assert len(of_type(data, "Provenance")) == 5
    assert len(data["entry"]) == 11
    ids = [e["resource"]["id"] for e in data["entry"]]
    assert len(ids) == len(set(ids))
    assert all(e["fullUrl"] == f"urn:uuid:{e['resource']['id']}" for e in data["entry"])


def test_medication_names_sukl_from_the_substance_file() -> None:
    (medication,) = of_type(bundle(), "Medication")
    codings = {c["system"]: c["code"] for c in medication["code"]["coding"]}
    assert codings == {fhir_builder.SUKL_SYSTEM: "0000000"}  # Fixture führt bewusst keinen ATC
    assert medication["code"]["text"] == "teststoff-a"


def test_medication_carries_atc_and_sukl_when_both_are_known() -> None:
    both = {
        "TESTSTOFF-A": kfhir.Substance("TESTSTOFF-A", "teststoff-a", ("L01XA03",), ("0000000",))
    }
    data = kfhir.build_bundle(fixture_rows(), both, GENERATED_AT)
    (medication,) = of_type(data, "Medication")
    codings = {c["system"]: c["code"] for c in medication["code"]["coding"]}
    assert codings == {fhir_builder.ATC_SYSTEM: "L01XA03", fhir_builder.SUKL_SYSTEM: "0000000"}


def test_effect_carries_original_term_frequency_and_ctcae_coding() -> None:
    effects = {
        e["symptomConditionEffect"]["text"]: e
        for e in of_type(bundle(), "MedicinalProductUndesirableEffect")
    }
    nausea = effects["Nausea"]
    assert nausea["frequencyOfOccurrence"]["coding"] == [
        {"system": kfhir.FREQUENCY_SYSTEM, "code": "very-common", "display": "very common"}
    ]
    assert nausea["symptomConditionEffect"]["coding"] == [
        {"system": kfhir.CTCAE_SYSTEM, "code": "Nausea"}
    ]
    assert "coding" not in effects["Palpitations"]["symptomConditionEffect"]  # keine Zuordnung
    assert effects["Palpitations"]["frequencyOfOccurrence"]["coding"][0]["code"] == "not-known"


def test_meddra_coding_is_added_when_the_ctcae_table_knows_the_term() -> None:
    meddra = {"nausea": ("10028813", "Nausea")}
    data = kfhir.build_bundle(fixture_rows(), substances(), GENERATED_AT, "collection", meddra)
    nausea = next(
        e
        for e in of_type(data, "MedicinalProductUndesirableEffect")
        if e["symptomConditionEffect"]["text"] == "Nausea"
    )
    systems = [c["system"] for c in nausea["symptomConditionEffect"]["coding"]]
    assert systems == [fhir_builder.MEDDRA_SYSTEM, kfhir.CTCAE_SYSTEM]


def test_every_effect_has_a_provenance_with_document_section_and_agent() -> None:
    data = bundle()
    effects = {e["id"] for e in of_type(data, "MedicinalProductUndesirableEffect")}
    provenances = of_type(data, "Provenance")
    targets = {p["target"][0]["reference"].removeprefix("urn:uuid:") for p in provenances}
    assert targets == effects
    first = provenances[0]
    assert first["recorded"] == GENERATED_AT
    assert first["agent"][0]["who"]["display"] == "manual (ae_matrix.csv)"
    source = first["entity"][0]
    assert source["role"] == "source"
    assert source["what"]["identifier"] == {"system": kfhir.DOCUMENT_SYSTEM, "value": "TESTDOC-A"}
    assert "section 4.8" in source["what"]["display"]
    assert "retrieved 2026-10-16" in source["what"]["display"]
    assert "https://example.invalid/testdoc-a" in source["what"]["display"]
    assert first["activity"]["coding"][0]["code"] == "manual"


def test_llm_rows_name_the_model_and_quote_the_evidence() -> None:
    result = extraction.run_extraction(
        document(), "4.8", "TESTSTOFF-A", FakeModel(answer(GOOD)), CTCAE
    )
    data = kfhir.build_bundle(result.rows, substances(), GENERATED_AT)
    (provenance,) = of_type(data, "Provenance")
    assert provenance["agent"][0]["who"]["display"] == "fake-1"
    assert provenance["activity"]["coding"][0]["code"] == "llm"
    roles = [e["role"] for e in provenance["entity"]]
    assert roles == ["source", "quotation"]
    assert provenance["entity"][1]["what"]["display"] == GOOD["evidence"]


def test_all_resources_are_tagged_as_draft_and_unverified_rows_are_marked() -> None:
    data = bundle()
    assert all(kfhir.DRAFT_TAG in e["resource"]["meta"]["tag"] for e in data["entry"])
    assert not any(
        t.get("code") == "synthetic" for e in data["entry"] for t in e["resource"]["meta"]["tag"]
    )
    verification = {
        e["symptomConditionEffect"]["text"]: [
            t["code"] for t in e["meta"]["tag"] if t["system"] == kfhir.VERIFICATION_SYSTEM
        ]
        for e in of_type(data, "MedicinalProductUndesirableEffect")
    }
    assert verification["Nausea"] == ["verified"]
    assert verification["Hypersensitivity"] == ["unverified"]


def test_references_resolve_and_there_are_no_empty_elements() -> None:
    data = bundle()
    known = {e["fullUrl"] for e in data["entry"]}
    found = refs(data["entry"])
    assert found
    assert all(r in known for r in found)

    def empty(node: Any) -> bool:
        if isinstance(node, dict):
            return any(v in (None, "", [], {}) or empty(v) for v in node.values())
        if isinstance(node, list):
            return any(v in (None, "", [], {}) or empty(v) for v in node)
        return False

    assert not empty(data["entry"])


def test_bundle_is_deterministic_and_collapses_duplicate_rows() -> None:
    assert json.dumps(bundle()) == json.dumps(bundle())
    doubled = [*fixture_rows(), *fixture_rows()]
    data = kfhir.build_bundle(doubled, substances(), GENERATED_AT)
    assert len(of_type(data, "MedicinalProductUndesirableEffect")) == 5


def test_unknown_substance_still_gets_a_medication_with_the_id_as_text() -> None:
    data = kfhir.build_bundle(fixture_rows(), {}, GENERATED_AT)
    (medication,) = of_type(data, "Medication")
    assert medication["code"] == {"text": "TESTSTOFF-A"}


def test_transaction_bundle_uses_put_type_slash_id_and_relative_references() -> None:
    data = bundle("transaction")
    assert data["type"] == "transaction"
    assert "timestamp" not in data
    for entry in data["entry"]:
        resource = entry["resource"]
        assert entry["request"] == {
            "method": "PUT",
            "url": f"{resource['resourceType']}/{resource['id']}",
        }
    known = {e["request"]["url"] for e in data["entry"]}
    found = refs(data["entry"])
    assert found
    assert all(r in known for r in found)
    ids_collection = [e["resource"]["id"] for e in bundle()["entry"]]
    assert ids_collection == [e["resource"]["id"] for e in data["entry"]]


def test_unknown_bundle_type_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown bundle type"):
        kfhir.build_bundle(fixture_rows(), substances(), GENERATED_AT, "batch")


def test_substances_file_errors_are_reported(tmp_path: Path) -> None:
    for text in ("substances: 3\n", "substances: [1]\n", "substances: [{inn: x}]\n"):
        target = tmp_path / "s.yaml"
        target.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=r"substances\.yaml"):
            kfhir.load_substances(target)


# --- Kommandozeile ----------------------------------------------------------------------------


def run_cli(*args: str) -> int:
    return cli.main(list(args))


def test_cli_to_fhir_writes_the_bundle_and_reports_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "bundle.json"
    code = run_cli(
        "to-fhir",
        "--matrix",
        str(FIXTURES / "ae_matrix_fixture.csv"),
        "--substances",
        str(FIXTURES / "substances_fixture.yaml"),
        "--generated-at",
        GENERATED_AT,
        "--out",
        str(out),
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["rows"] == 5
    assert summary["converted"] == 5
    assert summary["rejected"] == []
    assert summary["resources"] == 11
    written = json.loads(out.read_text(encoding="utf-8"))
    _, meddra = cli.load_ctcae(cli.DEFAULT_CTCAE)
    expected = kfhir.build_bundle(fixture_rows(), substances(), GENERATED_AT, "collection", meddra)
    assert written == expected
    assert "10028813" in json.dumps(written)  # MedDRA-Code von Nausea aus ctcae.yaml
    assert "\r" not in out.read_text(encoding="utf-8")


def test_cli_transaction_type_and_source_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "tx.json"
    code = run_cli(
        "to-fhir",
        "--matrix",
        str(FIXTURES / "ae_matrix_fixture.csv"),
        "--sources",
        str(FIXTURES),
        "--type",
        "transaction",
        "--generated-at",
        GENERATED_AT,
        "--out",
        str(out),
    )
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["type"] == "transaction"
    assert json.loads(capsys.readouterr().out)["rejected"] == []


def test_cli_rejects_rows_that_the_source_does_not_support(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    matrix = tmp_path / "m.csv"
    rows = verify.read_matrix(FIXTURES / "ae_matrix_fixture.csv")
    invented = row(original_term="Hair loss", ctcae_v6_term="")
    verify.write_matrix(matrix, [*rows, invented])
    out = tmp_path / "b.json"
    args = [
        "to-fhir",
        "--matrix",
        str(matrix),
        "--sources",
        str(FIXTURES),
        "--generated-at",
        GENERATED_AT,
        "--out",
        str(out),
    ]
    assert run_cli(*args) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["rejected"] == [
        {"original_term": "Hair loss", "reasons": ["term_not_in_source"]}
    ]
    assert summary["converted"] == 5
    assert "Hair loss" not in out.read_text(encoding="utf-8")  # nicht belegt ⇒ nicht in FHIR
    assert run_cli(*args, "--strict") == 2


def test_cli_input_errors_exit_with_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("to-fhir", "--matrix", str(tmp_path / "none.csv"), "--out", str(tmp_path / "o"))
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_cli_extract_without_a_model_is_not_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WAECHTER_LLM", raising=False)
    code = run_cli(
        "extract",
        "--source",
        str(FIXTURES / "TESTDOC-A.txt"),
        "--document-id",
        "TESTDOC-A",
        "--substance-id",
        "TESTSTOFF-A",
        "--retrieved",
        "2026-10-16",
        "--out",
        str(tmp_path / "r"),
    )
    assert code == 3
    assert "NOT RUN" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


def test_cli_extract_with_a_model_writes_checked_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extraction, "AdapterModel", lambda: FakeModel(answer(GOOD)))
    out = tmp_path / "rows.csv"
    code = run_cli(
        "extract",
        "--source",
        str(FIXTURES / "TESTDOC-A.txt"),
        "--document-id",
        "TESTDOC-A",
        "--substance-id",
        "TESTSTOFF-A",
        "--retrieved",
        "2026-10-16",
        "--url",
        "https://example.invalid/a",
        "--out",
        str(out),
    )
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["model"] == "fake-1"
    assert report["rows"] == 1
    assert report["rejected"] == []
    (written,) = list(csv.DictReader(out.open(encoding="utf-8")))
    assert written["extraction"] == "llm:fake-1"
    assert written["status"] == "verified"
    assert written["evidence"] == GOOD["evidence"]
    # die geschriebene CSV läuft durch dieselbe Pipeline nach FHIR
    final = tmp_path / "b.json"
    assert (
        run_cli(
            "to-fhir",
            "--matrix",
            str(out),
            "--sources",
            str(FIXTURES),
            "--generated-at",
            GENERATED_AT,
            "--out",
            str(final),
        )
        == 0
    )
    assert len(json.loads(final.read_text(encoding="utf-8"))["entry"]) == 3


def test_cli_is_runnable_as_a_module(tmp_path: Path) -> None:
    out = tmp_path / "m.json"
    env_path = [str(BACKEND), *[p for p in sys.path if p]]
    result = subprocess.run(  # noqa: S603 - fester Interpreter, feste Argumente
        [
            sys.executable,
            "-m",
            "waechter.knowledge.cli",
            "to-fhir",
            "--matrix",
            str(FIXTURES / "ae_matrix_fixture.csv"),
            "--generated-at",
            GENERATED_AT,
            "--out",
            str(out),
        ],
        cwd=BACKEND,
        env={"PYTHONPATH": ";".join(env_path) if sys.platform == "win32" else ":".join(env_path)},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["resourceType"] == "Bundle"


# --- Statische Prüfung: kein Netz, kein Datensatzzugriff --------------------------------------

FORBIDDEN_MODULES = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "httpx",
    "ftplib",
    "smtplib",
    "subprocess",
    "sqlite3",
    "sqlalchemy",
    "pandas",
}


def python_files() -> list[Path]:
    files = sorted(PACKAGE.glob("*.py"))
    assert {f.name for f in files} >= {"sources.py", "extract.py", "verify.py", "fhir.py", "cli.py"}
    return files


@pytest.mark.parametrize("path", python_files(), ids=lambda p: p.name)
def test_package_has_no_network_database_or_process_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN_MODULES), imported & FORBIDDEN_MODULES


@pytest.mark.parametrize("path", python_files(), ids=lambda p: p.name)
def test_package_contains_no_dataset_paths_or_loaders(path: Path) -> None:
    """Kein Code greift auf Rakathon-Datensätze zu: keine festen Pfade, Lader oder Dateinamen."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    pattern = re.compile(
        r"(?i)dataset|datensatz|rakathon|(?<![a-z])[a-z]:[\\/]|\\\\|^/|\.parquet|\.sqlite"
    )
    literals = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]
    offenders = [v for v in literals if pattern.search(v) and not v.startswith(("```", "/"))]
    assert not [o for o in offenders if len(o) < 120 and "\n" not in o], offenders


# --- Echte A1-Dateien (challenge/knowledge, T-KB) ---------------------------------------------

KNOWLEDGE = BACKEND.parent / "knowledge"
REAL_MATRIX = KNOWLEDGE / "ae_matrix.csv"
REAL_SUBSTANCES = KNOWLEDGE / "drugs" / "substances.yaml"
REAL_CTCAE = KNOWLEDGE / "ctcae_v6_terms.txt"


def test_section_may_carry_a_table_and_page_suffix() -> None:
    long_form = "4.8 Nežádoucí účinky; Tabulka 1; Poruchy krve; PDF S. 9"
    assert verify.section_number(long_form) == "4.8"
    assert verify.section_number("4.8") == "4.8"
    assert verify.section_number("Tabulka 1") is None
    assert verify.verify_manual(row(section=long_form), CTCAE).status == "verified"
    assert "section_invalid" in verify.verify_manual(row(section="Tabulka 1"), CTCAE).reasons


def test_substances_file_in_the_catalog_format(tmp_path: Path) -> None:
    target = tmp_path / "substances.yaml"
    target.write_text(
        "\n".join(
            [
                "substances:",
                "- id: X",
                "  inn: xylon",
                "  atc: [L01AA01, L01AA02]",
                "  sukl_products:",
                "  - {kod_sukl: '0000001', name: A}",
                "  - {kod_sukl: '0000002', name: B}",
                "  - {kod_sukl: '0000001', name: C}",
                "- id: Y",
                "  inn: ypsilon",
                "  atc: []",
                "  sukl_products: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = kfhir.load_substances(target)
    assert loaded["X"] == kfhir.Substance(
        "X", "xylon", ("L01AA01", "L01AA02"), ("0000001", "0000002")
    )
    assert loaded["Y"] == kfhir.Substance("Y", "ypsilon")
    (medication,) = of_type(
        kfhir.build_bundle([row(substance_id="X")], loaded, GENERATED_AT), "Medication"
    )
    assert [c["code"] for c in medication["code"]["coding"]] == [
        "L01AA01",
        "L01AA02",
        "0000001",
        "0000002",
    ]


def test_ctcae_list_file_uses_the_first_tab_column(tmp_path: Path) -> None:
    target = tmp_path / "terms.txt"
    target.write_text("# Kopf\nNausea\t12\nFatigue\t3\n\n", encoding="utf-8")
    allowed, meddra = cli.load_ctcae(target)
    assert allowed == {"Nausea", "Fatigue"}
    assert meddra == {}


def test_only_verified_filter_skips_unverified_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "v.json"
    code = run_cli(
        "to-fhir",
        "--matrix",
        str(FIXTURES / "ae_matrix_fixture.csv"),
        "--only-verified",
        "--generated-at",
        GENERATED_AT,
        "--out",
        str(out),
    )
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert (summary["converted"], summary["skipped_unverified"]) == (3, 2)
    terms = [
        e["symptomConditionEffect"]["text"]
        for e in of_type(
            json.loads(out.read_text(encoding="utf-8")), "MedicinalProductUndesirableEffect"
        )
    ]
    assert terms == ["Nausea", "fatigue", "Diarrhoea"]


def test_the_real_matrix_runs_through_the_pipeline_without_rejections(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = verify.read_matrix(REAL_MATRIX)
    assert len(rows) > 0
    out = tmp_path / "real.json"
    code = run_cli(
        "to-fhir",
        "--matrix",
        str(REAL_MATRIX),
        "--substances",
        str(REAL_SUBSTANCES),
        "--ctcae",
        str(REAL_CTCAE),
        "--only-verified",
        "--strict",
        "--generated-at",
        GENERATED_AT,
        "--out",
        str(out),
    )
    summary = json.loads(capsys.readouterr().out)
    assert code == 0, summary["rejected"][:3]
    assert summary["rejected"] == []
    verified = [r for r in rows if r.status == "verified"]
    assert summary["converted"] == len(verified)
    assert summary["skipped_unverified"] == len(rows) - len(verified)
    bundle_data = json.loads(out.read_text(encoding="utf-8"))
    effects = of_type(bundle_data, "MedicinalProductUndesirableEffect")
    assert len(effects) == len({kfhir.row_key(r) for r in verified})
    assert len(of_type(bundle_data, "Provenance")) == len(effects)
    assert {m["identifier"][0]["value"] for m in of_type(bundle_data, "Medication")} == {
        r.substance_id for r in verified
    }
    assert all(any(t["code"] == "verified" for t in e["meta"]["tag"]) for e in effects)


def test_a_term_that_is_only_the_tail_of_a_longer_item_is_rejected() -> None:
    """Auch der linke Rand zählt: `vyrážka` ist kein Treffer in `kožní vyrážka`."""
    text = "4.8 Nežádoucí účinky\nČasté: kožní vyrážka, svědění\n"
    tail = llm_row(
        original_term="vyrážka", frequency_class="common", evidence="kožní vyrážka, svědění"
    )
    assert verify.verify_extracted(tail, text, set()).status == "rejected"
    whole = llm_row(
        original_term="kožní vyrážka", frequency_class="common", evidence="kožní vyrážka, svědění"
    )
    assert verify.verify_extracted(whole, text, set()).status == "verified"
