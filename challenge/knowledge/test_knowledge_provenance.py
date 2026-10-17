# ruff: noqa: E501, PT006, PT018
"""Tests der Wissensbasis C61/C64 (T-KB, Owner A1; Vertrag v2.7, README §12).

Prüfen Herkunft (Provenienz), Abdeckung von CLINICAL_TODO, CTCAE-Terme gegen die PDF-Liste, statisch „kein Datensatz-/Netzzugriff“ und
deterministische Aggregation. Sie prüfen Softwareverhalten und Datenformat, **nicht** die fachliche Güte der Inhalte.
Teillauf: python -m pytest -q challenge/knowledge (im Ordner platform/backend: ../../challenge/knowledge).
"""

from __future__ import annotations

import ast
import builtins
import csv
import importlib.util
import io
import re
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent


def _load_aggregate():
    spec = importlib.util.spec_from_file_location("kb_aggregate", HERE / "aggregate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kb_aggregate"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


agg = _load_aggregate()


def _rows() -> list[dict[str, str]]:
    with open(HERE / "ae_matrix.csv", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _text(name: str) -> str:
    with open(HERE / name, encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def _ctcae_terms() -> set[str]:
    out = set()
    for line in _text("ctcae_v6_terms.txt").splitlines():
        if line.strip() and not line.startswith("#"):
            out.add(line.split("\t")[0])
    return out


FREQ = {"very common", "common", "uncommon", "rare", "very rare", "not known"}


# --------------------------------------------------------------------------------------------- Format und Provenienz


def test_ae_matrix_columns_exactly_as_contract():
    with open(HERE / "ae_matrix.csv", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == [
        "substance_id",
        "document",
        "document_url",
        "section",
        "retrieved",
        "original_term",
        "frequency_class",
        "ctcae_v6_term",
        "patient_reportable",
        "pro_item",
        "status",
        "extraction",
    ]


def test_ae_matrix_enums_and_extraction_format():
    rows = _rows()
    assert len(rows) > 0
    for r in rows:
        assert r["frequency_class"] in FREQ, r
        assert r["patient_reportable"] in {"yes", "no"}, r
        assert r["status"] in {"verified", "unverified"}, r
        assert r["extraction"] == "manual" or re.fullmatch(
            r"llm:[A-Za-z0-9._-]+", r["extraction"]
        ), r


def test_pro_item_present_iff_patient_reportable():
    for r in _rows():
        if r["patient_reportable"] == "yes":
            assert r["pro_item"] != "", r
        else:
            assert r["pro_item"] == "", r


def test_every_verified_row_has_full_provenance():
    verified = [r for r in _rows() if r["status"] == "verified"]
    assert verified, "keine verifizierte Zeile"
    for r in verified:
        assert r["document"].strip(), r
        assert re.match(r"^https://", r["document_url"]), r
        assert "4.8" in r["section"] and "PDF S." in r["section"], r
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["retrieved"]), r
        assert r["original_term"].strip(), r
        assert r["ctcae_v6_term"].strip(), "verified verlangt einen CTCAE-v6-Term aus der PDF-Liste"


def test_rows_without_ctcae_term_are_never_verified():
    for r in _rows():
        if not r["ctcae_v6_term"]:
            assert r["status"] == "unverified", r


def test_ctcae_terms_are_subset_of_pdf_term_list():
    pdf_terms = _ctcae_terms()
    assert len(pdf_terms) > 800  # Heuristik-Extraktion, siehe CLINICAL_TODO CT-005
    used = {r["ctcae_v6_term"] for r in _rows() if r["ctcae_v6_term"]}
    assert used, "kein CTCAE-Term verwendet"
    assert used <= pdf_terms, sorted(used - pdf_terms)


def test_substance_ids_exist_in_catalog():
    subs = agg.load_substances()
    for r in _rows():
        assert r["substance_id"] in subs, r["substance_id"]


# ------------------------------------------------------------------------------------------------------ Katalog


def test_substances_yaml_format_and_draft_status():
    with open(HERE / "drugs" / "substances.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    subs = data["substances"]
    ids = [s["id"] for s in subs]
    assert len(ids) == len(set(ids))
    assert {
        "ENZALUTAMIDE",
        "ABIRATERONE",
        "BICALUTAMIDE",
        "PAZOPANIB",
        "NIVOLUMAB",
        "SUNITINIB",
    } <= set(ids)
    for s in subs:
        assert set(s) >= {"id", "inn", "atc", "modules", "mapping_status", "source", "ref"}, s["id"]
        assert s["mapping_status"] in {"draft", "placeholder", "unverified"}, s["id"]
        assert s["modules"] == []
        assert isinstance(s["atc"], list) and s["atc"], s["id"]
        for code in s["atc"]:
            assert re.fullmatch(r"[A-Z]\d{2}[A-Z]{2}\d{2}", code), code
        for p in s["sukl_products"]:
            assert re.fullmatch(r"\d{7}", p["kod_sukl"]), p
        assert set(s["diagnosis_groups"]) <= {"C61", "C64"}


@pytest.mark.parametrize("fname,dx", [("c61.yaml", "C61"), ("c64.yaml", "C64")])
def test_regimen_files_reference_catalog_and_are_draft(fname, dx):
    subs = agg.load_substances()
    with open(HERE / "regimens" / fname, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    ids = [r["id"] for r in data["regimens"]]
    assert len(ids) == len(set(ids)) and ids
    for r in data["regimens"]:
        assert r["composition_status"] == "draft"
        assert r["label_de"] == "TODO"
        assert r["core_profile"] == []
        assert r["substances"] and set(r["substances"]) <= set(subs)
        for sid in r["substances"]:
            assert dx in subs[sid]["diagnosis_groups"]


# ------------------------------------------------------------------------------------- CLINICAL_TODO deckt Lücken ab


def _todo_sections() -> dict[str, str]:
    text = _text("CLINICAL_TODO.md")
    assert agg.TODO_BEGIN in text and agg.TODO_END in text
    block = text.split(agg.TODO_BEGIN, 1)[1].split(agg.TODO_END, 1)[0]
    sections: dict[str, str] = {}
    current = None
    for line in block.splitlines():
        m = re.match(r"^### (CT-U-[A-Z0-9-]+) ", line)
        if m:
            current = m.group(1)
            sections[current] = ""
        elif current:
            sections[current] += line + "\n"
    return sections


def test_every_unverified_row_is_listed_in_clinical_todo():
    sections = _todo_sections()
    for r in _rows():
        if r["status"] != "unverified":
            continue
        body = sections.get("CT-U-" + r["substance_id"], "")
        assert f"- {r['original_term']} (" in body, (r["substance_id"], r["original_term"])


def test_substances_without_ae_rows_are_listed_in_clinical_todo():
    sections = _todo_sections()
    with_rows = {r["substance_id"] for r in _rows()}
    body = sections.get("CT-U-OHNE-AE", "")
    for sid in agg.load_substances():
        if sid not in with_rows:
            assert f"- {sid}\n" in body, sid


def test_manual_todo_ids_are_unique_and_documented():
    text = _text("CLINICAL_TODO.md")
    ids = re.findall(r"^\| (CT-\d{3}) \|", text, flags=re.M)
    assert len(ids) == len(set(ids)) >= 10
    # in den Dateien referenzierte Punkte müssen existieren
    for name in (
        "drugs/substances.yaml",
        "regimens/c61.yaml",
        "regimens/c64.yaml",
        "items_draft.yaml",
        "staff_context.yaml",
        "SOURCES.md",
    ):
        for ref in re.findall(r"\bCT-\d{3}\b", _text(name)):
            assert ref in ids, (name, ref)


def test_clinical_todo_generated_block_is_current():
    text = _text("CLINICAL_TODO.md")
    block = (
        agg.TODO_BEGIN + text.split(agg.TODO_BEGIN, 1)[1].split(agg.TODO_END, 1)[0] + agg.TODO_END
    )
    assert block == agg.render_todo_block()


# ------------------------------------------------------------- statisch: kein Datensatz- oder Netzzugriff (README §12)

_NET_MODULES = {
    "socket",
    "ssl",
    "urllib",
    "urllib3",
    "http",
    "httpx",
    "requests",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "subprocess",
    "ctypes",
    "webbrowser",
    "xmlrpc",
    "asyncio",
}
# Marker werden zusammengesetzt, damit diese Datei sich nicht selbst trifft.
_DATASET_MARKERS = [
    "tex" + "ty",
    "lec" + "ba",
    "PAC" + "-",
    "Down" + "loads",
    "C:" + "\\",
    "C:" + "/",
    "\\\\" + "wsl",
]
_FILE_CALLS = {
    "open",
    "Path",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "glob",
    "rglob",
    "listdir",
    "scandir",
}


def _py_files() -> list[Path]:
    return sorted(p for p in HERE.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_no_network_or_process_imports_in_knowledge_code():
    for p in _py_files():
        bad = _imports(ast.parse(p.read_text(encoding="utf-8"))) & _NET_MODULES
        assert not bad, (p.name, bad)


def test_no_dataset_paths_or_foreign_file_access_in_knowledge_code():
    files = _py_files()
    assert {"aggregate.py", "test_knowledge_provenance.py"} <= {p.name for p in files}
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for marker in _DATASET_MARKERS:
                    assert marker not in node.value, (p.name, marker, node.value[:80])
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name not in _FILE_CALLS:
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        s = arg.value
                        assert not (
                            s.startswith(("/", "~"))
                            or re.match(r"^[A-Za-z]:", s)
                            or ".." in s.split("/")
                        ), (p.name, s)


def test_runtime_file_access_stays_inside_knowledge_folder(monkeypatch):
    opened: list[str] = []
    real_open = builtins.open

    def spy(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    agg.build()
    agg.render_todo_block()
    assert opened
    root = HERE.resolve()
    for f in opened:
        assert Path(f).resolve().is_relative_to(root), f


# ------------------------------------------------------------------------------------------- deterministische Aggregation


def test_aggregation_is_deterministic_and_matches_committed_files():
    first = agg.build()
    second = agg.build()
    assert first == second
    for name, data in first.items():
        rendered = agg.render(name, data)  # type: ignore[arg-type]
        assert rendered == agg.render(name, second[name])  # type: ignore[arg-type]
        assert rendered == _text(name), (
            f"{name} ist nicht aktuell: python challenge/knowledge/aggregate.py"
        )


def test_aggregation_counts_are_consistent():
    rows = _rows()
    out = agg.build()
    by_ctcae = out["ae_by_ctcae.csv"]
    keys = [
        (r["ctcae_v6_term"], r["original_terms_cs"] if not r["ctcae_v6_term"] else "")
        for r in by_ctcae
    ]
    assert len(keys) == len(set(keys))  # je CTCAE-Term genau eine Zeile
    assert sum(int(r["n_source_rows"]) for r in by_ctcae) == len(rows)
    assert sum(int(r["n_verified_rows"]) for r in by_ctcae) == sum(
        1 for r in rows if r["status"] == "verified"
    )
    reportable = [r for r in rows if r["patient_reportable"] == "yes"]
    assert sum(int(r["n_source_rows"]) for r in out["symptom_class_matrix.csv"]) == len(reportable)
    assert sum(i["source_rows"] for i in out["items_draft.yaml"]) == len(reportable)
    assert sum(e["source_rows"] for e in out["staff_context.yaml"]) == len(rows) - len(reportable)


def test_patient_items_and_staff_context_are_separated():
    out = agg.build()
    item_terms = {t for i in out["items_draft.yaml"] for t in i["original_terms_cs"]}
    staff_terms = {t for e in out["staff_context.yaml"] for t in e["original_terms_cs"]}
    assert item_terms and staff_terms
    assert not item_terms & staff_terms
    for i in out["items_draft.yaml"]:
        assert i["text_cs"] == i["text_de"] == i["text_en"] == "TODO_OFFICIAL_WORDING"
        assert i["label_de"] == "TODO"


# ------------------------------------------------ Randfälle der Aggregation mit synthetischen Eingaben (Softwareverhalten)


def _syn_row(sid, term, freq, ctcae, rep="yes", item="custom", status="verified"):
    return {
        "substance_id": sid,
        "document": "d",
        "document_url": "https://x",
        "section": "4.8 PDF S. 1",
        "retrieved": "2026-01-01",
        "original_term": term,
        "frequency_class": freq,
        "ctcae_v6_term": ctcae,
        "patient_reportable": rep,
        "pro_item": item,
        "status": status,
        "extraction": "manual",
    }


def test_aggregation_edge_cases_with_synthetic_rows(monkeypatch):
    rows = [
        _syn_row("A", "únava", "common", "Fatigue", item="fatigue"),
        _syn_row(
            "B", "Únava", "very common", "Fatigue", item="fatigue"
        ),  # Dedupe auf CTCAE-Term, höchste Klasse gewinnt
        _syn_row(
            "A", "kožní léze", "not known", "", status="unverified"
        ),  # ohne CTCAE-Term: eigener Schlüssel, 'not known'
        _syn_row("B", "kožní léze", "rare", "", status="unverified"),  # 'rare' > 'not known'
        _syn_row("A", "hypokalemie", "uncommon", "Hypokalemia", rep="no", item=""),
    ]
    subs = {"A": {"id": "A", "class_de": "K1"}, "B": {"id": "B", "class_de": "K2"}}
    monkeypatch.setattr(agg, "load_rows", lambda: rows)
    monkeypatch.setattr(agg, "load_substances", lambda: subs)
    out = agg.build()
    by = {r["ctcae_v6_term"] or r["original_terms_cs"]: r for r in out["ae_by_ctcae.csv"]}
    assert by["Fatigue"]["max_frequency_class"] == "very common"
    assert by["Fatigue"]["substance_ids"] == "A;B" and by["Fatigue"]["n_source_rows"] == "2"
    assert by["kožní léze"]["max_frequency_class"] == "rare"
    assert by["kožní léze"]["n_verified_rows"] == "0"
    matrix = {(r["symptom_key"], r["class_de"]): r for r in out["symptom_class_matrix.csv"]}
    assert matrix[("fatigue", "K1")]["max_frequency_class"] == "common"
    assert matrix[("fatigue", "K2")]["max_frequency_class"] == "very common"
    assert matrix[("custom:cs-kozni-leze", "K1")]["status"] == "unverified"
    assert [e["ctcae_v6_term"] for e in out["staff_context.yaml"]] == ["Hypokalemia"]
    only_unknown = agg.build()
    assert only_unknown == out  # Wiederholung identisch
