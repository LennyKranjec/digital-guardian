"""Reiner Aufbau des FHIR-R4-Bundles (`type=collection`) aus Klartextdaten einer Patientin.

Keine DB, keine Uhr, kein Zufall: `fullUrl` und `id` sind `uuid5` aus den internen IDs, die
Reihenfolge der Einträge ist festgelegt. Gleiche Daten ⇒ gleiches Bundle. Referenzen verweisen nur
auf Einträge im Bundle (`urn:uuid:…`). Enthalten sind Pseudonym und Geburtsjahr, **keine Namen**.
Alle Zeiten ISO 8601 mit Zeitzone. Mapping: `challenge/contract/README.md` §5.
"""

import base64
import html
import uuid
from dataclasses import dataclass, field
from typing import Any, Final

NAMESPACE: Final = uuid.UUID("6d3f1f0e-7c1a-4f0b-9a55-0c1d2e3f4a5b")
SYNTHETIC_TAG: Final = {
    "system": "urn:waechter:tag",
    "code": "synthetic",
    "display": "synthetic data",
}
OBSERVATION_CATEGORY: Final = "http://terminology.hl7.org/CodeSystem/observation-category"
DATA_ABSENT: Final = "http://terminology.hl7.org/CodeSystem/data-absent-reason"
SCALE_SYSTEM: Final = "urn:waechter:pro-scale"
ITEM_SYSTEM: Final = "urn:waechter:pro-item"
ATC_SYSTEM: Final = "http://www.whocc.no/atc"
MEDDRA_SYSTEM: Final = "http://terminology.hl7.org/CodeSystem/mdr"
FACT_SYSTEM: Final = "urn:waechter:fact"
SUKL_SYSTEM: Final = "urn:waechter:sukl-code"  # ANNAHME: kein veröffentlichtes System-URI bekannt
ICD10_SYSTEM: Final = "http://hl7.org/fhir/sid/icd-10"
ENTRY_ORDER: Final = (
    "Patient",
    "Condition",
    "MedicationStatement",
    "Questionnaire",
    "QuestionnaireResponse",
    "Observation",
    "Flag",
    "DocumentReference",
    "Provenance",
    "AuditEvent",
)


@dataclass(frozen=True)
class ChoiceOption:
    value: int
    label: str


@dataclass(frozen=True)
class QuestionData:
    attribute: str
    text: str
    options: list[ChoiceOption]


@dataclass(frozen=True)
class QuestionnaireItemData:
    symptom_key: str
    label: str
    questions: list[QuestionData]


@dataclass(frozen=True)
class QuestionnaireData:
    questionnaire_id: str
    items_version: str
    regimen_label: str
    items: list[QuestionnaireItemData]


@dataclass(frozen=True)
class AnswerData:
    answer_id: str
    symptom_key: str
    attribute: str
    value: int | None
    label: str
    option_label: str | None
    #: T-23: official | adapted_recall | own (None = unbekannt, ältere Zeilen)
    wording: str | None = None


@dataclass(frozen=True)
class ResponseData:
    response_id: str
    questionnaire_id: str
    recorded_at: str
    channel: str
    entered_by: str
    answers: list[AnswerData]
    #: T-23: Sprache und Rückblick (initial_7d | daily_24h) der Frage (None = unbekannt)
    lang: str | None = None
    recall: str | None = None


@dataclass(frozen=True)
class AlertData:
    alert_id: str
    rule_id: str
    level: str
    headline: str
    created_at: str
    status: str
    acknowledgement_id: str | None = None
    acknowledged_at: str | None = None
    decision: str | None = None


@dataclass(frozen=True)
class AssessmentItemData:
    ctcae_term_id: str
    term_en: str
    meddra_code: str
    grade: int
    attribution: str
    note: str | None


@dataclass(frozen=True)
class AssessmentData:
    assessment_id: str
    assessed_at: str
    items: list[AssessmentItemData]


@dataclass(frozen=True)
class FreeTextSuggestionData:
    symptom_key: str
    label: str
    quote: str


@dataclass(frozen=True)
class FreeTextData:
    free_text_id: str
    response_id: str
    text: str
    created_at: str
    mapper: str
    mode: str
    suggestions: list[FreeTextSuggestionData]


@dataclass(frozen=True)
class SummaryData:
    summary_id: str
    created_at: str
    generator: str
    model: str | None
    mode: str
    facts_hash: str
    prompt_version: str
    lang: str
    text: str


@dataclass(frozen=True)
class DrugData:
    name: str
    atc: str
    sukl_code: str | None = None


@dataclass
class ExportData:
    patient_id: str
    pseudonym: str
    sex: str
    birth_year: int
    language: str
    therapy_id: str | None
    regimen_label: str
    cycle_start: str | None
    drugs: list[DrugData]
    generated_at: str
    diagnosis_code: str | None = None
    questionnaires: list[QuestionnaireData] = field(default_factory=list)
    responses: list[ResponseData] = field(default_factory=list)
    alerts: list[AlertData] = field(default_factory=list)
    assessments: list[AssessmentData] = field(default_factory=list)
    summary: SummaryData | None = None
    free_texts: list[FreeTextData] = field(default_factory=list)
    #: fertige, bereits bestätigte Zusatzressourcen (T-21: Dokumente); leer ⇒ Export unverändert
    extra_resources: list[dict[str, Any]] = field(default_factory=list)


def uid(kind: str, internal_id: str) -> str:
    """Deterministische UUID (uuid5) für Ressourcen-`id` und `fullUrl`."""
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{internal_id}"))


def ref(kind: str, internal_id: str) -> dict[str, str]:
    return {"reference": f"urn:uuid:{uid(kind, internal_id)}"}


def _meta(*tags: dict[str, str]) -> dict[str, Any]:
    return {"tag": [SYNTHETIC_TAG, *tags]}


WORDING_TAG_SYSTEM = "urn:waechter:question-wording"


def _wording_tags(wordings: list[str | None]) -> list[dict[str, str]]:
    """T-23: Herkunft des Wortlauts als meta.tag (die HAPI-Prüfung kennt keine eigene Extension);
    an der QuestionnaireResponse je vorkommender Wert, an der Observation der Wert der Antwort."""
    return [
        {"system": WORDING_TAG_SYSTEM, "code": code}
        for code in sorted({w for w in wordings if w is not None})
    ]


def _variant_tags(response: ResponseData) -> list[dict[str, str]]:
    """T-23: mit welcher Variante gefragt wurde (Sprache, Rückblick); fehlt bei älteren Zeilen."""
    tags = []
    if response.lang is not None:
        tags.append({"system": "urn:waechter:question-language", "code": response.lang})
    if response.recall is not None:
        tags.append({"system": "urn:waechter:recall-period", "code": response.recall})
    return tags


def _identifier(fact_id: str) -> list[dict[str, str]]:
    return [{"system": FACT_SYSTEM, "value": fact_id}]


def narrative(text: str, lang: str = "") -> dict[str, str]:
    """Kurze generierte Beschreibung (dom-6: Ressourcen sollten ein Narrativ tragen)."""
    attributes = f' lang="{lang}" xml:lang="{lang}"' if lang else ""
    return {
        "status": "generated",
        "div": f'<div xmlns="http://www.w3.org/1999/xhtml"{attributes}>{html.escape(text)}</div>',
    }


def make_resource(
    kind: str, internal_id: str, body: dict[str, Any], text: str = ""
) -> dict[str, Any]:
    language = str(body.get("language", ""))
    return {
        "resourceType": kind,
        "id": uid(kind, internal_id),
        "text": narrative(text or f"{kind} {internal_id[:8]}", language),
        **body,
    }


def patient(data: ExportData) -> dict[str, Any]:
    return make_resource(
        "Patient",
        data.patient_id,
        {
            "meta": _meta(),
            "identifier": [{"system": "urn:waechter:pseudonym", "value": data.pseudonym}],
            "active": True,
            "gender": data.sex,
            "birthDate": str(data.birth_year),
            "communication": [
                {
                    "language": {"coding": [{"system": "urn:ietf:bcp:47", "code": data.language}]},
                    "preferred": True,
                }
            ],
        },
        f"Synthetic patient {data.pseudonym}, born {data.birth_year}",
    )


def condition(data: ExportData) -> list[dict[str, Any]]:
    """Diagnose (ICD-10, synthetisch) aus `diagnosis_code`; ohne Code keine Ressource."""
    if not data.diagnosis_code:
        return []
    return [
        make_resource(
            "Condition",
            data.patient_id,
            {
                "meta": _meta(),
                "clinicalStatus": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                            "code": "active",
                        }
                    ]
                },
                "code": {"coding": [{"system": ICD10_SYSTEM, "code": data.diagnosis_code}]},
                "subject": ref("Patient", data.patient_id),
            },
            f"Synthetic diagnosis {data.diagnosis_code}",
        )
    ]


def medication_statements(data: ExportData) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, drug in enumerate(data.drugs):
        coding = [{"system": ATC_SYSTEM, "code": drug.atc, "display": drug.name}]
        if drug.sukl_code:
            coding.append({"system": SUKL_SYSTEM, "code": drug.sukl_code, "display": drug.name})
        body: dict[str, Any] = {
            "meta": _meta(),
            "status": "active",
            "medicationCodeableConcept": {"coding": coding, "text": drug.name},
            "subject": ref("Patient", data.patient_id),
        }
        if data.cycle_start is not None:
            body["effectivePeriod"] = {"start": data.cycle_start}
        result.append(
            make_resource("MedicationStatement", f"{data.therapy_id}:{index}", body, drug.name)
        )
    return result


def questionnaire_url(questionnaire_id: str) -> str:
    return f"urn:waechter:questionnaire:{questionnaire_id}"


def questionnaire(data: ExportData, source: QuestionnaireData) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for group in source.items:
        children = [
            {
                "linkId": f"{group.symptom_key}.{q.attribute}",
                "text": q.text,
                "type": "choice",
                "answerOption": [
                    {
                        "valueCoding": {
                            "system": SCALE_SYSTEM,
                            "code": str(option.value),
                            "display": option.label,
                        }
                    }
                    for option in q.options
                ],
            }
            for q in group.questions
        ]
        items.append(
            {"linkId": group.symptom_key, "text": group.label, "type": "group", "item": children}
        )
    return make_resource(
        "Questionnaire",
        f"{source.questionnaire_id}:{data.language}",
        {
            "meta": _meta(),
            "url": questionnaire_url(source.questionnaire_id),
            "version": source.items_version,
            "name": "WaechterSymptomQuestionnaire",
            "title": source.regimen_label,
            "status": "active",
            "language": data.language,
            "subjectType": ["Patient"],
            "item": items,
        },
        source.regimen_label,
    )


def questionnaire_response(data: ExportData, response: ResponseData) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for answer in response.answers:
        entry: dict[str, Any] = {"linkId": f"{answer.symptom_key}.{answer.attribute}"}
        if answer.value is not None:
            entry["answer"] = [
                {
                    "valueCoding": {
                        "system": SCALE_SYSTEM,
                        "code": str(answer.value),
                        "display": answer.option_label or str(answer.value),
                    }
                }
            ]
        groups.setdefault(answer.symptom_key, []).append(entry)
    body: dict[str, Any] = {
        "meta": _meta(
            {"system": "urn:waechter:channel", "code": response.channel},
            {"system": "urn:waechter:entered-by", "code": response.entered_by},
            *_variant_tags(response),
            *_wording_tags([a.wording for a in response.answers]),
        ),
        "identifier": {"system": FACT_SYSTEM, "value": f"resp-{response.response_id}"},
        "questionnaire": questionnaire_url(response.questionnaire_id),
        "status": "completed",
        "subject": ref("Patient", data.patient_id),
        "authored": response.recorded_at,
        "item": [{"linkId": key, "item": children} for key, children in groups.items()],
    }
    if response.entered_by == "self":
        body["source"] = ref("Patient", data.patient_id)
    return make_resource(
        "QuestionnaireResponse",
        response.response_id,
        body,
        f"Questionnaire response {response.recorded_at}",
    )


def pro_observation(data: ExportData, response: ResponseData, answer: AnswerData) -> dict[str, Any]:
    body: dict[str, Any] = {
        "meta": _meta(*_variant_tags(response), *_wording_tags([answer.wording])),
        "identifier": _identifier(f"obs-{answer.answer_id}"),
        "status": "final",
        "category": [{"coding": [{"system": OBSERVATION_CATEGORY, "code": "survey"}]}],
        "code": {
            "coding": [
                {
                    "system": ITEM_SYSTEM,
                    "code": f"{answer.symptom_key}.{answer.attribute}",
                    "display": answer.label,
                }
            ],
            "text": answer.label,
        },
        "subject": ref("Patient", data.patient_id),
        "effectiveDateTime": response.recorded_at,
        "performer": (
            [ref("Patient", data.patient_id)]
            if response.entered_by == "self"
            else [{"display": response.entered_by}]
        ),
        "derivedFrom": [ref("QuestionnaireResponse", response.response_id)],
    }
    if answer.value is None:
        body["dataAbsentReason"] = {"coding": [{"system": DATA_ABSENT, "code": "asked-declined"}]}
    else:
        body["valueInteger"] = answer.value
    shown = "not answered" if answer.value is None else str(answer.value)
    return make_resource("Observation", f"pro:{answer.answer_id}", body, f"{answer.label}: {shown}")


def flag(data: ExportData, alert: AlertData) -> dict[str, Any]:
    period: dict[str, str] = {"start": alert.created_at}
    if alert.acknowledged_at is not None:
        period["end"] = alert.acknowledged_at
    return make_resource(
        "Flag",
        alert.alert_id,
        {
            "meta": _meta(),
            "identifier": _identifier(f"alert-{alert.alert_id}"),
            "status": "active" if alert.status == "open" else "inactive",
            "category": [{"coding": [{"system": "urn:waechter:flag-level", "code": alert.level}]}],
            "code": {
                "coding": [{"system": "urn:waechter:rule", "code": alert.rule_id}],
                "text": alert.headline,
            },
            "subject": ref("Patient", data.patient_id),
            "period": period,
        },
        alert.headline,
    )


def ctcae_observations(data: ExportData, assessment: AssessmentData) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in assessment.items:
        attribution = {"coding": [{"system": "urn:waechter:attribution", "code": item.attribution}]}
        body: dict[str, Any] = {
            "meta": _meta(),
            "identifier": _identifier(f"assess-{assessment.assessment_id}"),
            "status": "final",
            "category": [{"coding": [{"system": OBSERVATION_CATEGORY, "code": "exam"}]}],
            "code": {
                "coding": [
                    {"system": MEDDRA_SYSTEM, "code": item.meddra_code, "display": item.term_en},
                    {"system": "urn:waechter:ctcae", "code": item.ctcae_term_id},
                ],
                "text": item.term_en,
            },
            "subject": ref("Patient", data.patient_id),
            "effectiveDateTime": assessment.assessed_at,
            "performer": [{"display": "clinician"}],
            "valueCodeableConcept": {
                "coding": [
                    {
                        "system": "urn:waechter:ctcae-grade",
                        "code": str(item.grade),
                        "display": f"Grade {item.grade}",
                    }
                ]
            },
            "component": [
                {
                    "code": {
                        "coding": [
                            {"system": "urn:waechter:ctcae-component", "code": "attribution"}
                        ]
                    },
                    "valueCodeableConcept": attribution,
                }
            ],
        }
        if item.note:
            body["note"] = [{"text": item.note}]
        result.append(
            make_resource(
                "Observation",
                f"ctcae:{assessment.assessment_id}:{item.ctcae_term_id}",
                body,
                f"{item.term_en}: grade {item.grade}",
            )
        )
    return result


def free_text_resources(data: ExportData, free_text: FreeTextData) -> list[dict[str, Any]]:
    """Freitext der Patientin als Observation `valueString` plus Provenance (T-22).

    Der Text ist von der Patientin; die Zuordnungen sind nur Vorschläge (Provenance: Gerät mit
    Adapter/Modus, Zitate als `quotation`), nie Bewertungen.
    """
    exported = {r.response_id for r in data.responses}
    body: dict[str, Any] = {
        "meta": _meta(),
        "identifier": _identifier(f"ft-{free_text.free_text_id}"),
        "status": "final",
        "category": [{"coding": [{"system": OBSERVATION_CATEGORY, "code": "survey"}]}],
        "code": {
            "coding": [{"system": ITEM_SYSTEM, "code": "free-text", "display": "Other complaints"}],
            "text": "Other complaints (free text)",
        },
        "subject": ref("Patient", data.patient_id),
        "effectiveDateTime": free_text.created_at,
        "performer": [ref("Patient", data.patient_id)],
        "valueString": free_text.text,
    }
    if free_text.response_id in exported:
        body["derivedFrom"] = [ref("QuestionnaireResponse", free_text.response_id)]
    observation = make_resource(
        "Observation", f"ft:{free_text.free_text_id}", body, "Patient free text"
    )
    agents: list[dict[str, Any]] = [
        {
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                        "code": "author",
                    }
                ]
            },
            "who": ref("Patient", data.patient_id),
        }
    ]
    entities: list[dict[str, Any]] = []
    if free_text.suggestions:
        agents.append(
            {"who": {"type": "Device", "display": f"{free_text.mapper} ({free_text.mode})"}}
        )
        entities = [
            {
                "role": "quotation",
                "what": {"display": f"{s.quote} -> {s.symptom_key} (suggestion, not rated)"},
            }
            for s in free_text.suggestions
        ]
    provenance_body: dict[str, Any] = {
        "meta": _meta(),
        "target": [ref("Observation", f"ft:{free_text.free_text_id}")],
        "recorded": free_text.created_at,
        "agent": agents,
    }
    if entities:  # keine leeren Elemente (ele-1)
        provenance_body["entity"] = entities
    provenance = make_resource(
        "Provenance",
        f"ft:{free_text.free_text_id}",
        provenance_body,
        "Provenance of the patient free text",
    )
    return [observation, provenance]


def summary_resources(data: ExportData, summary: SummaryData) -> list[dict[str, Any]]:
    document = make_resource(
        "DocumentReference",
        summary.summary_id,
        {
            "meta": _meta(),
            "identifier": _identifier(f"summary-{summary.summary_id}"),
            "status": "current",
            "docStatus": "preliminary",
            "type": {"coding": [{"system": "urn:waechter:document-type", "code": "ai-summary"}]},
            "subject": ref("Patient", data.patient_id),
            "date": summary.created_at,
            "author": [{"display": summary.generator}],
            "description": "AI draft (decision support); check the cited facts",
            "content": [
                {
                    "attachment": {
                        "contentType": "text/plain",
                        "language": summary.lang,
                        "data": base64.b64encode(summary.text.encode("utf-8")).decode("ascii"),
                        "title": "AI summary",
                    }
                }
            ],
        },
        "AI draft summary (decision support)",
    )
    provenance = make_resource(
        "Provenance",
        summary.summary_id,
        {
            "meta": _meta(),
            "target": [ref("DocumentReference", summary.summary_id)],
            "recorded": summary.created_at,
            "agent": [
                {
                    "type": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                                "code": "author",
                            }
                        ]
                    },
                    "who": {"type": "Device", "display": summary.generator},
                }
            ],
            "entity": [
                {
                    "role": "source",
                    "what": {
                        "identifier": {
                            "system": "urn:waechter:facts-hash",
                            "value": summary.facts_hash,
                        },
                        "display": f"mode={summary.mode}; prompt={summary.prompt_version}",
                    },
                }
            ],
        },
        f"Provenance of the AI summary ({summary.generator})",
    )
    return [document, provenance]


def audit_events(data: ExportData) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for alert in data.alerts:
        if alert.acknowledgement_id is None or alert.acknowledged_at is None:
            continue
        result.append(
            make_resource(
                "AuditEvent",
                alert.acknowledgement_id,
                {
                    "meta": _meta(),
                    "type": {
                        "system": "http://terminology.hl7.org/CodeSystem/audit-event-type",
                        "code": "rest",
                        "display": "RESTful Operation",
                    },
                    "subtype": [
                        {"system": "urn:waechter:audit-action", "code": "acknowledge_alert"}
                    ],
                    "action": "U",
                    "recorded": alert.acknowledged_at,
                    "outcome": "0",
                    "agent": [{"requestor": True, "who": {"display": "clinician"}}],
                    "source": {"observer": {"display": "waechter-backend"}},
                    "entity": [
                        {
                            "what": ref("Flag", alert.alert_id),
                            "description": f"decision={alert.decision or 'n/a'}",
                        }
                    ],
                },
                "Alert acknowledged by clinician",
            )
        )
    return result


def _resources(data: ExportData) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = [
        patient(data),
        *condition(data),
        *medication_statements(data),
    ]
    resources.extend(questionnaire(data, q) for q in data.questionnaires)
    for response in data.responses:
        resources.append(questionnaire_response(data, response))
        resources.extend(pro_observation(data, response, a) for a in response.answers)
    resources.extend(flag(data, a) for a in data.alerts)
    for assessment in data.assessments:
        resources.extend(ctcae_observations(data, assessment))
    for free_text in data.free_texts:
        resources.extend(free_text_resources(data, free_text))
    if data.summary is not None:
        resources.extend(summary_resources(data, data.summary))
    resources.extend(audit_events(data))
    resources.extend(data.extra_resources)
    order = {kind: index for index, kind in enumerate(ENTRY_ORDER)}
    resources.sort(key=lambda r: order[r["resourceType"]])  # stabil: Reihenfolge innerhalb der Art
    return resources


def build_bundle(data: ExportData) -> dict[str, Any]:
    resources = _resources(data)
    return {
        "resourceType": "Bundle",
        "id": uid("Bundle", data.patient_id),
        "meta": _meta(),
        "identifier": {"system": "urn:waechter:bundle", "value": data.pseudonym},
        "type": "collection",
        "timestamp": data.generated_at,
        "entry": [{"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources],
    }


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str | list | dict) and len(value) == 0)


def prune(node: Any) -> Any:
    """Entfernt leere Elemente (`None`, `""`, `[]`, `{}`); `0` und `False` bleiben (FHIR: ele-1)."""
    if isinstance(node, dict):
        cleaned = {k: prune(v) for k, v in node.items()}
        return {k: v for k, v in cleaned.items() if not _is_empty(v)}
    if isinstance(node, list):
        return [v for v in (prune(i) for i in node) if not _is_empty(v)]
    return node


def relative_references(node: Any, kinds: dict[str, str]) -> Any:
    """`urn:uuid:<id>` → `<Typ>/<id>` für Referenzen auf Ressourcen dieses Bundles."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "reference" and isinstance(value, str) and value.startswith("urn:uuid:"):
                target = value.removeprefix("urn:uuid:")
                out[key] = f"{kinds[target]}/{target}" if target in kinds else value
            else:
                out[key] = relative_references(value, kinds)
        return out
    if isinstance(node, list):
        return [relative_references(i, kinds) for i in node]
    return node


def transaction_from(
    resources: list[dict[str, Any]], bundle_id: str, meta: dict[str, Any]
) -> dict[str, Any]:
    """Transaction-Bundle aus fertigen Ressourcen: je Eintrag `PUT {Typ}/{id}`, Referenzen `Typ/id`.

    Jeder Eintrag `PUT {Typ}/{id}` mit der deterministischen `uuid5`-id ⇒ wiederholter Upload
    ersetzt dieselben Ressourcen (idempotent). Keine leeren Elemente, kein Zeitstempel (gleiche
    Daten ⇒ gleiche Bytes). `fullUrl` bleibt `urn:uuid:<id>` (der HAPI-Validator verlangt eine
    absolute URL).
    """
    kinds = {r["id"]: r["resourceType"] for r in resources}
    entries: list[dict[str, Any]] = []
    for resource in resources:
        body = prune(relative_references(resource, kinds))
        target = f"{body['resourceType']}/{body['id']}"
        entries.append(
            {
                "fullUrl": f"urn:uuid:{body['id']}",
                "resource": body,
                "request": {"method": "PUT", "url": target},
            }
        )
    return {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": meta,
        "type": "transaction",
        "entry": entries,
    }


def build_transaction(data: ExportData) -> dict[str, Any]:
    """Transaction-Bundle im Format der Klinik-Exporte (Vertrag v2.8)."""
    return transaction_from(_resources(data), uid("Transaction", data.patient_id), _meta())
