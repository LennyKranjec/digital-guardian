# ruff: noqa: E501, RUF001
"""Aggregation der AE-Matrix (T-KB Schritt 3, Vertrag v2.7, README §12). Owner: A1.

Liest ausschliesslich Dateien in diesem Ordner (ae_matrix.csv, drugs/substances.yaml) und schreibt:
  ae_by_ctcae.csv            Deduplikation auf CTCAE-Term (ueber Wirkstoffe)
  symptom_class_matrix.csv   Symptom x Wirkstoffklasse
  items_draft.yaml           (a) patientenberichtbar, Texte TODO_OFFICIAL_WORDING (cs/de/en)
  staff_context.yaml         (b) nur Labor/Personal, nicht im Fragebogen

Deterministisch (feste Sortierung, keine Zeitstempel, kein Zufall). Nur Standardbibliothek + PyYAML; kein Netz, kein Zugriff
auf Datensatz- oder andere Dateien ausserhalb von challenge/knowledge (Test test_knowledge_provenance.py prueft das statisch).
Aufruf zum Neuerzeugen: python challenge/knowledge/aggregate.py
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

AE_COLUMNS = [
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
# MedDRA-Konvention; "not known" = Haeufigkeit nicht bestimmbar (niedrigster Rang, nicht "selten")
FREQ_RANK = {
    "not known": 0,
    "very rare": 1,
    "rare": 2,
    "uncommon": 3,
    "common": 4,
    "very common": 5,
}
# Symptomschluessel, die in challenge/content/items.yaml (Stand 2026-10-17) bereits als Fragebogen-Items existieren.
EXISTING_ITEM_KEYS = frozenset(
    {
        "fatigue",
        "nausea",
        "diarrhea",
        "fever",
        "pain",
        "peripheral_neuropathy",
        "hand_foot",
        "mouth_sores",
        "vomiting",
        "rash",
        "shortness_of_breath",
        "decreased_appetite",
    }
)
TODO_WORDING = "TODO_OFFICIAL_WORDING"


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def load_rows() -> list[dict[str, str]]:
    with open(HERE / "ae_matrix.csv", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_substances() -> dict[str, dict]:
    with open(HERE / "drugs" / "substances.yaml", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return {s["id"]: s for s in data["substances"]}


def _max_freq(values: list[str]) -> str:
    return max(values, key=lambda v: FREQ_RANK[v])


def _symptom_key(row: dict[str, str]) -> str:
    item = row["pro_item"]
    if item and item != "custom":
        return item
    if row["ctcae_v6_term"]:
        return "custom:" + _slug(row["ctcae_v6_term"])
    return "custom:cs-" + _slug(row["original_term"])


def _group_key(row: dict[str, str]) -> str:
    """CTCAE-Term, sonst der Originalterm (Praefix ~, nicht dedupliziert ueber Begriffe)."""
    return row["ctcae_v6_term"] or "~" + row["original_term"].lower()


def build() -> dict[str, object]:
    rows = load_rows()
    subs = load_substances()
    cls_of = {sid: s["class_de"] for sid, s in subs.items()}

    # 1) Deduplikation auf CTCAE-Term
    groups: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        groups.setdefault(_group_key(r), []).append(r)
    by_ctcae_rows = []
    for key in sorted(groups):
        g = groups[key]
        by_ctcae_rows.append(
            {
                "ctcae_v6_term": g[0]["ctcae_v6_term"],
                "original_terms_cs": ";".join(sorted({r["original_term"].lower() for r in g})),
                "substance_ids": ";".join(sorted({r["substance_id"] for r in g})),
                "classes": ";".join(sorted({cls_of[r["substance_id"]] for r in g})),
                "max_frequency_class": _max_freq([r["frequency_class"] for r in g]),
                "patient_reportable": "yes"
                if any(r["patient_reportable"] == "yes" for r in g)
                else "no",
                "pro_items": ";".join(sorted({r["pro_item"] for r in g if r["pro_item"]})),
                "n_source_rows": str(len(g)),
                "n_verified_rows": str(sum(1 for r in g if r["status"] == "verified")),
            }
        )

    # 2) Symptom x Wirkstoffklasse (nur patientenberichtbar)
    sym: dict[tuple[str, str], list[dict[str, str]]] = {}
    for r in rows:
        if r["patient_reportable"] != "yes":
            continue
        sym.setdefault((_symptom_key(r), cls_of[r["substance_id"]]), []).append(r)
    matrix_rows = []
    for key, cls in sorted(sym):
        g = sym[(key, cls)]
        verified = sum(1 for r in g if r["status"] == "verified")
        matrix_rows.append(
            {
                "symptom_key": key,
                "existing_item": "yes" if key in EXISTING_ITEM_KEYS else "no",
                "class_de": cls,
                "substance_ids": ";".join(sorted({r["substance_id"] for r in g})),
                "ctcae_v6_terms": ";".join(
                    sorted({r["ctcae_v6_term"] for r in g if r["ctcae_v6_term"]})
                ),
                "max_frequency_class": _max_freq([r["frequency_class"] for r in g]),
                "n_source_rows": str(len(g)),
                "n_verified_rows": str(verified),
                "status": "draft" if verified else "unverified",
            }
        )

    # 3a) Items-Entwurf (patientenberichtbar); Wortlaut ausdruecklich offen
    by_sym: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        if r["patient_reportable"] == "yes":
            by_sym.setdefault(_symptom_key(r), []).append(r)
    items = []
    for key in sorted(by_sym):
        g = by_sym[key]
        verified = sum(1 for r in g if r["status"] == "verified")
        items.append(
            {
                "key": key,
                "existing_item": key in EXISTING_ITEM_KEYS,
                "ctcae_v6_terms": sorted({r["ctcae_v6_term"] for r in g if r["ctcae_v6_term"]}),
                "original_terms_cs": sorted({r["original_term"].lower() for r in g}),
                "label_de": "TODO",
                "text_cs": TODO_WORDING,
                "text_de": TODO_WORDING,
                "text_en": TODO_WORDING,
                "substances": sorted({r["substance_id"] for r in g}),
                "classes": sorted({cls_of[r["substance_id"]] for r in g}),
                "max_frequency_class": _max_freq([r["frequency_class"] for r in g]),
                "source_rows": len(g),
                "verified_rows": verified,
                "status": "draft" if verified else "unverified",
            }
        )

    # 3b) Personal-/Laborkontext (nicht im Fragebogen)
    staff = []
    for key in sorted(groups):
        g = [r for r in groups[key] if r["patient_reportable"] == "no"]
        if not g:
            continue
        verified = sum(1 for r in g if r["status"] == "verified")
        staff.append(
            {
                "ctcae_v6_term": g[0]["ctcae_v6_term"] or None,
                "original_terms_cs": sorted({r["original_term"].lower() for r in g}),
                "substances": sorted({r["substance_id"] for r in g}),
                "classes": sorted({cls_of[r["substance_id"]] for r in g}),
                "max_frequency_class": _max_freq([r["frequency_class"] for r in g]),
                "source_rows": len(g),
                "verified_rows": verified,
                "status": "draft" if verified else "unverified",
            }
        )
    return {
        "ae_by_ctcae.csv": by_ctcae_rows,
        "symptom_class_matrix.csv": matrix_rows,
        "items_draft.yaml": items,
        "staff_context.yaml": staff,
    }


CSV_HEADERS = {
    "ae_by_ctcae.csv": [
        "ctcae_v6_term",
        "original_terms_cs",
        "substance_ids",
        "classes",
        "max_frequency_class",
        "patient_reportable",
        "pro_items",
        "n_source_rows",
        "n_verified_rows",
    ],
    "symptom_class_matrix.csv": [
        "symptom_key",
        "existing_item",
        "class_de",
        "substance_ids",
        "ctcae_v6_terms",
        "max_frequency_class",
        "n_source_rows",
        "n_verified_rows",
        "status",
    ],
}

YAML_HEADERS = {
    "items_draft.yaml": (
        "# items_draft.yaml – Entwurf patientenberichtbarer Symptome C61/C64 (T-KB Schritt 3, README §12). Owner: A1.\n"
        "# MASCHINELL ERZEUGT aus ae_matrix.csv durch aggregate.py (nicht von Hand ändern). STATUS: draft/unverified – bis zur klinischen Freigabe.\n"
        "# text_cs/text_de/text_en: TODO_OFFICIAL_WORDING (kein Fragetext aus dem Gedächtnis, keine geschützten Instrumente kopiert;\n"
        "# offizieller Wortlaut offen). Zuordnung Symptom↔Item ist Annahme von A1 (CLINICAL_TODO CT-004). original_terms_cs = Wortlaut der SPC (cs).\n"
        "# existing_item: true = Schlüssel existiert bereits in challenge/content/items.yaml (Stand 2026-10-17).\n"
    ),
    "staff_context.yaml": (
        "# staff_context.yaml – Nebenwirkungen nur für Labor/Personal, NICHT im Patientenfragebogen (T-KB Schritt 3, README §12). Owner: A1.\n"
        "# MASCHINELL ERZEUGT aus ae_matrix.csv durch aggregate.py (nicht von Hand ändern). STATUS: draft/unverified – bis zur klinischen Freigabe.\n"
        "# Kontext für Ärzt:innen/Pflege, keine Diagnose, keine Handlungsempfehlung. patient_reportable=no ist Annahme von A1 (CLINICAL_TODO CT-004).\n"
    ),
}


def render(name: str, data: list[dict]) -> str:
    if name in CSV_HEADERS:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_HEADERS[name], lineterminator="\n")
        w.writeheader()
        w.writerows(data)
        return buf.getvalue()
    key = "items" if name == "items_draft.yaml" else "entries"
    body = yaml.safe_dump(
        {
            "version": "knowledge-" + name.split(".")[0].replace("_", "-") + "-v1",
            "status": "draft",
            key: data,
        },
        sort_keys=False,
        allow_unicode=True,
        width=200,
    )
    return YAML_HEADERS[name] + body


TODO_BEGIN = "<!-- BEGIN GENERATED (aggregate.py) -->"
TODO_END = "<!-- END GENERATED -->"


def render_todo_block() -> str:
    """Maschinell erzeugter Teil von CLINICAL_TODO.md: je Wirkstoff die unverifizierten AE-Zeilen + Wirkstoffe ohne AE-Zeilen."""
    rows = load_rows()
    subs = load_substances()
    lines = [TODO_BEGIN, ""]
    with_rows = sorted({r["substance_id"] for r in rows})
    for sid in with_rows:
        un = [r for r in rows if r["substance_id"] == sid and r["status"] == "unverified"]
        if not un:
            continue
        lines.append(f"### CT-U-{sid} – unverifizierte AE-Zeilen ({len(un)})")
        lines.append(
            "Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004."
        )
        for r in un:
            page = r["section"].rsplit("PDF S. ", 1)[-1]
            lines.append(f"- {r['original_term']} ({r['frequency_class']}; S. {page})")
        lines.append("")
    none = [sid for sid in sorted(subs) if sid not in with_rows]
    lines.append(f"### CT-U-OHNE-AE – Wirkstoffe ohne AE-Zeilen ({len(none)})")
    lines.append(
        "Grund: Schritt-2-Umfang war SmPC 4.8 für die 6 laut Datensatz häufigsten Wirkstoffe; alle weiteren sind `unverified` (keine AE-Zeile)."
    )
    for sid in none:
        lines.append(f"- {sid}")
    lines += ["", TODO_END]
    return "\n".join(lines)


def update_todo() -> None:
    path = HERE / "CLINICAL_TODO.md"
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    head, rest = text.split(TODO_BEGIN, 1)
    tail = rest.split(TODO_END, 1)[1]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(head + render_todo_block() + tail)


def main() -> None:
    for name, data in build().items():
        with open(HERE / name, "w", encoding="utf-8", newline="") as fh:
            fh.write(render(name, data))  # type: ignore[arg-type]
        print(name, len(data))  # type: ignore[arg-type]
    update_todo()


if __name__ == "__main__":
    main()
