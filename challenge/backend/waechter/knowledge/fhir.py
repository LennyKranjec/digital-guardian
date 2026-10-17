"""AE-Zeilen ⇒ FHIR R4: `Medication` + `MedicinalProductUndesirableEffect` + `Provenance` je Zeile.

Rein und deterministisch (ids per `uuid5`, keine Uhr: der Zeitpunkt wird übergeben). Verworfene
Zeilen kommen nie hierher; `unverified`-Zeilen werden als solche markiert (`meta.tag`). Alles trägt
den Entwurfs-Tag (klinisch nicht freigegeben). Die Medikation nennt ATC und kódSÚKL, sofern die
Wirkstoffliste sie kennt. Das Bundle ist `collection` (urn:uuid) oder `transaction` (PUT Typ/id).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from waechter.fhir import builder as fhir
from waechter.knowledge.verify import AeRow

DRAFT_TAG: Final = {
    "system": "urn:waechter:tag",
    "code": "draft",
    "display": "clinically unreleased",
}
VERIFICATION_SYSTEM: Final = "urn:waechter:verification"
FREQUENCY_SYSTEM: Final = "urn:waechter:frequency-class"  # ANNAHME: MedDRA-Konvention, kein URI
EXTRACTION_SYSTEM: Final = "urn:waechter:extraction"
DOCUMENT_SYSTEM: Final = "urn:waechter:smpc-document"
CTCAE_SYSTEM: Final = "urn:waechter:ctcae-term"
PARTICIPANT_SYSTEM: Final = "http://terminology.hl7.org/CodeSystem/provenance-participant-type"


@dataclass(frozen=True)
class Substance:
    substance_id: str
    inn: str
    atc: tuple[str, ...] = ()
    sukl_codes: tuple[str, ...] = ()


def _inn(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        for lang in ("en", "cs", "de"):
            if isinstance(value.get(lang), str) and value[lang].strip():
                return str(value[lang]).strip()
    return fallback


def _strings(value: Any) -> tuple[str, ...]:
    """Einzelwert oder Liste ⇒ Tupel nicht leerer Zeichenketten (Reihenfolge bleibt)."""
    items = value if isinstance(value, list) else [value]
    return tuple(str(i).strip() for i in items if i is not None and str(i).strip())


def _sukl_codes(entry: Mapping[str, Any]) -> tuple[str, ...]:
    """kódSÚKL aus `sukl_code` (einzeln) oder `sukl_products[].kod_sukl` (A1-Katalog)."""
    codes = list(_strings(entry.get("sukl_code")))
    products = entry.get("sukl_products")
    if isinstance(products, list):
        codes.extend(
            str(p["kod_sukl"]).strip()
            for p in products
            if isinstance(p, Mapping) and p.get("kod_sukl")
        )
    return tuple(dict.fromkeys(codes))


def load_substances(path: Path) -> dict[str, Substance]:
    """`substances.yaml` (A1): Liste `substances` mit id, inn, atc[], sukl_products[]."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    entries = data.get("substances") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("substances.yaml: list 'substances' expected")
    result: dict[str, Substance] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("substances.yaml: entry is not a mapping")
        key = str(entry.get("substance_id") or entry.get("id") or "").strip()
        if not key:
            raise ValueError("substances.yaml: entry without substance_id")
        result[key] = Substance(
            key,
            _inn(entry.get("inn"), key),
            _strings(entry.get("atc")),
            _sukl_codes(entry),
        )
    return result


def _tags(*extra: dict[str, str]) -> dict[str, Any]:
    return {"tag": [DRAFT_TAG, *extra]}


def medication(substance: Substance) -> dict[str, Any]:
    codings: list[dict[str, str]] = []
    codings.extend(
        {"system": fhir.ATC_SYSTEM, "code": code} for code in substance.atc
    )  # ohne display
    codings.extend({"system": fhir.SUKL_SYSTEM, "code": code} for code in substance.sukl_codes)
    return fhir.make_resource(
        "Medication",
        substance.substance_id,
        {
            "meta": _tags(),
            "identifier": [{"system": "urn:waechter:substance", "value": substance.substance_id}],
            "code": {"coding": codings, "text": substance.inn},
        },
        f"Active substance {substance.inn}",
    )


def row_key(row: AeRow) -> str:
    return "|".join(
        (
            row.substance_id,
            row.document,
            row.section,
            row.original_term.casefold(),
            row.frequency_class,
        )
    )


def _effect(row: AeRow, meddra: Mapping[str, tuple[str, str]]) -> dict[str, Any]:
    coding: list[dict[str, str]] = []
    if row.ctcae_v6_term:
        code, display = meddra.get(row.ctcae_v6_term.casefold(), ("", row.ctcae_v6_term))
        if code:
            coding.append({"system": fhir.MEDDRA_SYSTEM, "code": code, "display": display})
        coding.append({"system": CTCAE_SYSTEM, "code": row.ctcae_v6_term})
    verification = {"system": VERIFICATION_SYSTEM, "code": row.status}
    return fhir.make_resource(
        "MedicinalProductUndesirableEffect",
        row_key(row),
        {
            "meta": _tags(verification),
            "subject": [fhir.ref("Medication", row.substance_id)],
            "symptomConditionEffect": {"coding": coding, "text": row.original_term},
            "frequencyOfOccurrence": {
                "coding": [
                    {
                        "system": FREQUENCY_SYSTEM,
                        "code": row.frequency_class.replace(" ", "-"),
                        "display": row.frequency_class,
                    }
                ]
            },
        },
        f"{row.original_term} ({row.frequency_class}), {row.document} section {row.section}",
    )


def _provenance(row: AeRow, generated_at: str) -> dict[str, Any]:
    method = "manual" if row.extraction == "manual" else "llm"
    who = "manual (ae_matrix.csv)" if method == "manual" else row.extraction.removeprefix("llm:")
    source = f"{row.document}, section {row.section}, retrieved {row.retrieved}"
    if row.document_url:
        source += f"; {row.document_url}"
    entities: list[dict[str, Any]] = [
        {
            "role": "source",
            "what": {
                "identifier": {"system": DOCUMENT_SYSTEM, "value": row.document},
                "display": source,
            },
        }
    ]
    if row.evidence:
        entities.append({"role": "quotation", "what": {"display": row.evidence}})
    return fhir.make_resource(
        "Provenance",
        row_key(row),
        {
            "meta": _tags(),
            "target": [fhir.ref("MedicinalProductUndesirableEffect", row_key(row))],
            "recorded": generated_at,
            "activity": {"coding": [{"system": EXTRACTION_SYSTEM, "code": method}]},
            "agent": [
                {
                    "type": {"coding": [{"system": PARTICIPANT_SYSTEM, "code": "author"}]},
                    "who": {"display": who},
                }
            ],
            "entity": entities,
        },
        f"Provenance of the adverse effect '{row.original_term}' ({method})",
    )


def resources_for(
    rows: Iterable[AeRow],
    substances: Mapping[str, Substance],
    generated_at: str,
    meddra: Mapping[str, tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Medication je Wirkstoff (sortiert), dann Wirkung + Provenance je Zeile."""
    ordered = list(rows)
    wanted = sorted({r.substance_id for r in ordered})
    result = [medication(substances.get(s, Substance(s, s))) for s in wanted]
    seen: set[str] = set()
    for row in ordered:
        key = row_key(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(_effect(row, meddra or {}))
        result.append(_provenance(row, generated_at))
    return [fhir.prune(r) for r in result]


def build_bundle(
    rows: Iterable[AeRow],
    substances: Mapping[str, Substance],
    generated_at: str,
    bundle_type: str = "collection",
    meddra: Mapping[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    resources = resources_for(rows, substances, generated_at, meddra)
    bundle_id = fhir.uid("KnowledgeBundle", "|".join(r["id"] for r in resources))
    if bundle_type == "transaction":
        return fhir.transaction_from(resources, bundle_id, _tags())
    if bundle_type != "collection":
        raise ValueError(f"unknown bundle type: {bundle_type}")
    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": _tags(),
        "type": "collection",
        "timestamp": generated_at,
        "entry": [{"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources],
    }
