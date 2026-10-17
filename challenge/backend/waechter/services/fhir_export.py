"""FHIR-Export einer Patientin: Daten sammeln, Bundle bauen, Export auditieren.

Es werden nur Daten dieser Patientin gesammelt. Der Export enthält Pseudonym und Geburtsjahr, keine
Namen, keinen Diagnosetext. Ärztliche Notizen der CTCAE-Aufnahme stehen als `Observation.note`
(ärztliche Dokumentation); Notizen der Quittierung und Freitexte der Patientin gibt es nicht.
Zeiten in Europe/Prague, Texte in der Sprache der Patientin.
"""

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.services.audit import record_audit
from app.services.auth import Principal
from waechter.content import Content
from waechter.fhir import builder as fhir
from waechter.models import Alert, AlertAction, Answer, Assessment, FreeText, Patient, Response
from waechter.services.alert_queries import alert_view
from waechter.services.alerts import ACTION_ACKNOWLEDGE
from waechter.services.assessment_queries import assessment_view
from waechter.services.documents import confirmed_resources
from waechter.services.patient_views import get_patient, symptom_label
from waechter.services.questionnaire import (
    NO_GROUP,
    localize,
    max_value,
    option_labels,
    select_for_regimen,
)
from waechter.services.status import current_therapy
from waechter.services.summary_queries import latest_summary
from waechter.timeutil import iso_prague


def _scale_label(
    content: Content, attribute: str, value: int, lang: str, symptom_key: str | None = None
) -> str:
    labels = option_labels(content, attribute, symptom_key)
    if labels is None or value >= len(labels):
        return str(value)
    return localize(labels[value], lang)


def _questionnaire(
    content: Content, questionnaire_id: str, lang: str
) -> fhir.QuestionnaireData | None:
    items_version, _, rest = questionnaire_id.partition(":")
    regimen_id, _, group = rest.partition(":")
    selection = select_for_regimen(content, regimen_id, group if group != NO_GROUP else None)
    if selection is None:
        return None
    return fhir.QuestionnaireData(
        questionnaire_id=questionnaire_id,
        items_version=items_version,
        regimen_label=localize(selection.regimen["label"], lang),
        items=[
            fhir.QuestionnaireItemData(
                symptom_key=item["symptom_key"],
                label=localize(item["label"], lang),
                questions=[
                    fhir.QuestionData(
                        attribute=q["attribute"],
                        text=localize(q["question"], lang),
                        options=[
                            fhir.ChoiceOption(
                                v,
                                _scale_label(content, q["attribute"], v, lang, item["symptom_key"]),
                            )
                            for v in range(max_value(q["attribute"]) + 1)
                        ],
                    )
                    for q in item["attributes"]
                ],
            )
            for item, _ in selection.items
        ],
    )


def _sukl_code(content: Content, regimen_id: str, atc: str) -> str | None:
    """SÚKL-Kennung aus dem Arzneimittelkatalog (nur wenn Regime und ATC eindeutig passen)."""
    if content.medications is None:
        return None
    codes = {
        m["sukl_code"]
        for m in content.medications["medications"]
        if m.get("sukl_code") and m.get("atc") == atc and regimen_id in m.get("regimen_ids", [])
    }
    return next(iter(codes)) if len(codes) == 1 else None


def collect(session: Session, clock: Clock, content: Content, patient: Patient) -> fhir.ExportData:
    lang = patient.language
    therapy = current_therapy(session, patient.id)
    regimen = (
        next((r for r in content.regimens["regimens"] if r["id"] == therapy.regimen_id), None)
        if therapy is not None
        else None
    )
    responses = session.scalars(
        select(Response)
        .where(Response.patient_id == patient.id)
        .order_by(Response.recorded_at, Response.id)
    ).all()
    answers: dict[str, list[Answer]] = defaultdict(list)
    if responses:
        for answer in session.scalars(
            select(Answer)
            .where(Answer.response_id.in_([r.id for r in responses]))
            .order_by(Answer.symptom_key, Answer.attribute)
        ):
            answers[answer.response_id].append(answer)
    response_data = [
        fhir.ResponseData(
            response_id=r.id,
            questionnaire_id=r.questionnaire_id,
            recorded_at=iso_prague(r.recorded_at),
            channel=r.channel,
            entered_by=r.entered_by,
            lang=getattr(
                r, "lang", None
            ),  # Spalte legt T-22 (w008) an; fehlt sie noch, bleibt None
            recall=r.recall,
            answers=[
                fhir.AnswerData(
                    answer_id=a.id,
                    symptom_key=a.symptom_key,
                    attribute=a.attribute,
                    value=a.value,
                    wording=a.wording,
                    label=f"{symptom_label(content, a.symptom_key, lang)} ({a.attribute})",
                    option_label=(
                        None
                        if a.value is None
                        else _scale_label(content, a.attribute, a.value, lang, a.symptom_key)
                    ),
                )
                for a in answers[r.id]
            ],
        )
        for r in responses
    ]
    questionnaires = [
        q
        for qid in sorted({r.questionnaire_id for r in responses})
        if (q := _questionnaire(content, qid, lang)) is not None
    ]
    known = {q.questionnaire_id for q in questionnaires}
    response_data = [r for r in response_data if r.questionnaire_id in known]

    alert_rows = session.scalars(
        select(Alert).where(Alert.patient_id == patient.id).order_by(Alert.created_at, Alert.id)
    ).all()
    alert_data: list[fhir.AlertData] = []
    for alert in alert_rows:
        action = session.scalars(
            select(AlertAction)
            .where(AlertAction.alert_id == alert.id, AlertAction.action == ACTION_ACKNOWLEDGE)
            .order_by(AlertAction.at.desc(), AlertAction.id)
            .limit(1)
        ).first()
        view = alert_view(session, alert, content, lang)
        alert_data.append(
            fhir.AlertData(
                alert_id=alert.id,
                rule_id=alert.rule_id,
                level=alert.level,
                headline=view["headline"],
                created_at=iso_prague(alert.created_at),
                status=alert.status,
                acknowledgement_id=action.id if action is not None else None,
                acknowledged_at=iso_prague(action.at) if action is not None else None,
                decision=action.decision if action is not None else None,
            )
        )

    assessments = session.scalars(
        select(Assessment)
        .where(Assessment.patient_id == patient.id)
        .order_by(Assessment.assessed_at, Assessment.id)
    ).all()
    assessment_data = []
    for assessment in assessments:
        view = assessment_view(session, assessment, content)
        assessment_data.append(
            fhir.AssessmentData(
                assessment_id=assessment.id,
                assessed_at=view["assessed_at"],
                items=[
                    fhir.AssessmentItemData(
                        ctcae_term_id=i["ctcae_term_id"],
                        term_en=i["term_en"],
                        meddra_code=i["meddra_code"],
                        grade=i["grade"],
                        attribution=i["attribution"],
                        note=i["note"],
                    )
                    for i in view["items"]
                ],
            )
        )

    free_rows = session.scalars(
        select(FreeText)
        .where(FreeText.patient_id == patient.id)
        .order_by(FreeText.created_at, FreeText.id)
    ).all()
    free_texts = [
        fhir.FreeTextData(
            free_text_id=f.id,
            response_id=f.response_id,
            text=f.text,
            created_at=iso_prague(f.created_at),
            mapper=f.mapper,
            mode=f.mapper_mode,
            suggestions=[
                fhir.FreeTextSuggestionData(
                    s["symptom_key"], symptom_label(content, s["symptom_key"], lang), s["quote"]
                )
                for s in f.suggestions_json
            ],
        )
        for f in free_rows
    ]

    summary_row = latest_summary(session, patient.id)
    summary = None
    if summary_row is not None:
        body: dict[str, Any] = summary_row.body_json
        provenance = body["provenance"]
        text = "\n".join(f"{s['text']} [{', '.join(s['refs'])}]" for s in body["sentences"])
        summary = fhir.SummaryData(
            summary_id=summary_row.id,
            created_at=iso_prague(summary_row.created_at),
            generator=summary_row.generator,
            model=provenance.get("model"),
            mode=summary_row.mode,
            facts_hash=summary_row.facts_hash,
            prompt_version=provenance.get("prompt_version", ""),
            lang=provenance.get("lang", lang),
            text=text or "-",
        )

    return fhir.ExportData(
        patient_id=patient.id,
        pseudonym=patient.pseudonym,
        sex=patient.sex,
        birth_year=patient.birth_year,
        language=lang,
        therapy_id=therapy.id if therapy is not None else None,
        regimen_label=localize(regimen["label"], lang) if regimen is not None else "",
        cycle_start=iso_prague(therapy.cycle_start) if therapy is not None else None,
        drugs=(
            [
                fhir.DrugData(d["name"], d["atc"], _sukl_code(content, regimen["id"], d["atc"]))
                for d in regimen["drugs"]
            ]
            if regimen is not None
            else []
        ),
        generated_at=iso_prague(clock.now()),
        diagnosis_code=patient.diagnosis_code,
        questionnaires=questionnaires,
        responses=response_data,
        alerts=alert_data,
        assessments=assessment_data,
        free_texts=free_texts,
        summary=summary,
        extra_resources=confirmed_resources(session, patient.id),
    )


def transaction_bundle(
    session: Session, clock: Clock, content: Content, patient: Patient
) -> dict[str, Any]:
    """Transaction-Bundle (v2.8) ohne Audit; Export und Push auditieren selbst."""
    return fhir.build_transaction(collect(session, clock, content, patient))


def export_bundle(
    session: Session,
    clock: Clock,
    principal: Principal,
    patient_id: str,
    content: Content,
    bundle_type: str = "collection",
) -> dict[str, Any]:
    patient = get_patient(session, patient_id)
    if bundle_type == "transaction":
        bundle = transaction_bundle(session, clock, content, patient)
    else:
        bundle = fhir.build_bundle(collect(session, clock, content, patient))
    record_audit(
        session,
        clock,
        principal.actor,
        "export_fhir",
        "patient",
        target_id=patient.id,
        subject_id=patient.id,
        details={"resources": len(bundle["entry"])},
    )
    session.commit()
    return bundle
