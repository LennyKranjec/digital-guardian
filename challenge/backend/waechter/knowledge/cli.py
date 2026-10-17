"""Kommandozeile der Wissensbasis-Pipeline.

    python -m waechter.knowledge.cli to-fhir --matrix challenge/knowledge/ae_matrix.csv \\
        [--substances challenge/knowledge/drugs/substances.yaml] [--sources <ordner>] \\
        [--type collection|transaction] [--generated-at <ISO>] --out bundle.json
    python -m waechter.knowledge.cli extract --source smpc.txt --document-id SMPC-X \\
        --substance-id X --retrieved 2026-10-16 [--url <URL>] [--section 4.8] --out rows.csv

Exit-Codes: 0 ok, 2 Eingabefehler oder verworfene Zeilen im Strikt-Modus, 3 Sprachmodell nicht
verfügbar (LLM-Lauf NOT RUN). Gelesen werden nur die genannten Dateien; kein Netz, kein Datensatz.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from waechter.knowledge import extract as extraction
from waechter.knowledge import fhir as knowledge_fhir
from waechter.knowledge.sources import SourceDocument, SourceError, load_source, normalize
from waechter.knowledge.verify import (
    AeRow,
    read_matrix,
    section_number,
    verify_manual,
    with_status,
    write_matrix,
)
from waechter.timeutil import iso_prague

CHALLENGE = Path(__file__).resolve().parents[3]
DEFAULT_CTCAE = CHALLENGE / "content" / "ctcae.yaml"


def load_ctcae(path: Path) -> tuple[set[str], dict[str, tuple[str, str]]]:
    """Erlaubte CTCAE-Begriffe (Name, id) und MedDRA-Zuordnung aus `ctcae.yaml` oder `.txt`."""
    if path.suffix.lower() == ".txt":
        lines = path.read_text(encoding="utf-8").splitlines()
        names = {line.split(chr(9))[0].strip() for line in lines}  # Spalte 1 (Begriff), Rest Seite
        return {n for n in names if n and not n.startswith("#")}, {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    allowed: set[str] = set()
    meddra: dict[str, tuple[str, str]] = {}
    for term in data["terms"]:
        allowed.update({term["id"], term["term_en"]})
        for key in (term["id"], term["term_en"]):
            meddra[key.casefold()] = (str(term["meddra_code"]), term["term_en"])
    return allowed, meddra


def _source_texts(directory: Path | None, rows: Sequence[AeRow]) -> dict[tuple[str, str], str]:
    """Abschnittstexte je (Dokument, Abschnitt) aus `<ordner>/<document>.txt|html|htm`."""
    if directory is None:
        return {}
    texts: dict[tuple[str, str], str] = {}
    wanted = {(r.document, section_number(r.section) or r.section) for r in rows}
    for document, section in sorted(wanted):
        for suffix in (".txt", ".html", ".htm"):
            candidate = directory / f"{document}{suffix}"
            if candidate.is_file():
                try:
                    source = load_source(candidate, document)
                    texts[(document, section)] = source.section(section).text
                except SourceError as error:
                    print(f"warning: {document} {section}: {error}", file=sys.stderr)
                break
    return texts


def to_fhir(args: argparse.Namespace) -> int:
    try:
        rows = read_matrix(Path(args.matrix))
        substances = (
            knowledge_fhir.load_substances(Path(args.substances)) if args.substances else {}
        )
        allowed, meddra = load_ctcae(Path(args.ctcae))
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    texts = _source_texts(Path(args.sources) if args.sources else None, rows)
    skipped = 0
    accepted: list[AeRow] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        number = section_number(row.section) or row.section
        verdict = verify_manual(row, allowed, texts.get((row.document, number)))
        if verdict.status == "rejected":
            rejected.append({"original_term": row.original_term, "reasons": list(verdict.reasons)})
            continue
        if args.only_verified and verdict.status != "verified":
            skipped += 1
            continue
        accepted.append(with_status(row, verdict))
    generated_at = args.generated_at or iso_prague(datetime.now().astimezone())
    bundle = knowledge_fhir.build_bundle(accepted, substances, generated_at, args.type, meddra)
    out = Path(args.out)
    out.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "rows": len(rows),
                "converted": len(accepted),
                "skipped_unverified": skipped,
                "rejected": rejected,
                "resources": len(bundle["entry"]),
                "bundle": out.name,
            },
            ensure_ascii=False,
        )
    )
    return 2 if rejected and args.strict else 0


def extract(args: argparse.Namespace) -> int:
    try:
        allowed, _ = load_ctcae(Path(args.ctcae))
        document: SourceDocument = load_source(
            Path(args.source),
            args.document_id,
            title=args.document_id,
            url=args.url,
            retrieved=args.retrieved,
        )
        model = extraction.AdapterModel()
        result = extraction.run_extraction(
            document, args.section, args.substance_id, model, allowed
        )
    except extraction.ExtractionUnavailable as error:
        print(f"NOT RUN: {error}", file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, yaml.YAMLError, SourceError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    write_matrix(Path(args.out), result.rows)
    report = {
        "model": result.model,
        "prompt_version": result.prompt_version,
        "prompt_sha256": result.prompt_sha256,
        "rows": len(result.rows),
        "rejected": [
            {"original_term": r.original_term, "reasons": list(r.reasons)} for r in result.rejected
        ],
        "parse_errors": list(result.parse_errors),
        "section_chars": len(normalize(document.section(args.section).text)),
    }
    print(json.dumps(report, ensure_ascii=False))
    return 2 if args.strict and (result.rejected or result.parse_errors) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waechter.knowledge.cli", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    convert = sub.add_parser("to-fhir", help="ae_matrix.csv ⇒ FHIR-Bundle")
    convert.add_argument("--matrix", required=True)
    convert.add_argument("--substances")
    convert.add_argument("--sources", help="Ordner mit <document>.txt|html für die Quellprüfung")
    convert.add_argument("--ctcae", default=str(DEFAULT_CTCAE))
    convert.add_argument("--type", choices=("collection", "transaction"), default="collection")
    convert.add_argument("--generated-at", help="ISO-Zeitpunkt (Standard: jetzt, Europe/Prague)")
    convert.add_argument(
        "--only-verified", action="store_true", help="nur Zeilen mit Status verified nach FHIR"
    )
    convert.add_argument(
        "--strict", action="store_true", help="Exit 2, wenn Zeilen verworfen wurden"
    )
    convert.add_argument("--out", required=True)
    convert.set_defaults(handler=to_fhir)
    pull = sub.add_parser(
        "extract", help="SmPC-Text ⇒ Modell ⇒ Prüfer ⇒ CSV (nur mit WAECHTER_LLM=openai)"
    )
    pull.add_argument("--source", required=True)
    pull.add_argument("--document-id", required=True)
    pull.add_argument("--substance-id", required=True)
    pull.add_argument("--retrieved", required=True)
    pull.add_argument("--url", default="")
    pull.add_argument("--section", default="4.8")
    pull.add_argument("--ctcae", default=str(DEFAULT_CTCAE))
    pull.add_argument("--strict", action="store_true")
    pull.add_argument("--out", required=True)
    pull.set_defaults(handler=extract)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
