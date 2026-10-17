import { z } from 'zod';

import {
  API_BASE,
  ApiClientError,
  apiGet,
  apiPost,
  apiPut,
  type FieldError,
} from '../../../../platform/frontend/src/shared/api/client';

export type FieldErrorLike = FieldError;

/**
 * Typen und Laufzeitprüfung nach challenge/contract/openapi.yaml (Vertrag v1.1).
 * Pfade relativ zu /api/v1; Fehler im Plattformformat (ApiClientError).
 */

export const ATTRIBUTES = ['frequency', 'severity', 'interference', 'presence', 'amount'] as const;
export const attributeSchema = z.enum(ATTRIBUTES);
export type Attribute = z.infer<typeof attributeSchema>;

export const LANGS = ['cs', 'en', 'de'] as const;
export type Lang = (typeof LANGS)[number];

const optionSchema = z.object({ value: z.number().int(), label: z.string() });

const questionSchema = z.object({
  attribute: attributeSchema,
  text: z.string(),
  options: z.array(optionSchema),
});

const itemSchema = z.object({
  symptom_key: z.string(),
  label: z.string(),
  source: z.enum(['core', 'regimen']).nullish(),
  questions: z.array(questionSchema),
});

export const questionnaireSchema = z.object({
  questionnaire_id: z.string(),
  items_version: z.string(),
  regimen_id: z.string(),
  lang: z.string(),
  recall_period: z.string(),
  recall: z.enum(['initial_7d', 'daily_24h']).nullish(),
  selection_reason: z.string().nullish(),
  items: z.array(itemSchema),
});
export type Questionnaire = z.infer<typeof questionnaireSchema>;
export type QuestionnaireItem = Questionnaire['items'][number];
export type QuestionnaireQuestion = QuestionnaireItem['questions'][number];

export interface SubmitAnswer {
  symptom_key: string;
  attribute: Attribute;
  /** 0–4; `null` = übersprungen (wird als fehlend gespeichert, nie imputiert) */
  value: number | null;
}

export interface ResponseSubmit {
  client_submission_id: string;
  questionnaire_id: string;
  channel: 'web';
  entered_by: 'self';
  answers: SubmitAnswer[];
  /** T-23: Variante der angezeigten Fassung (sonst berechnet der Server sie) */
  recall?: 'initial_7d' | 'daily_24h';
}

/** v1.9/v1.10 „Rady pacientovi“: Tipps je gemeldetem Symptom mit Quellen; nie Ampel/Grad. */
export const adviceBlockSchema = z.object({
  /** Regelkennung (ADV-…, Vertrag v2.1): gehört in die Befundkarte der Ärztin, wird Patientinnen nie angezeigt */
  rule_id: z.string().nullish(),
  symptom_key: z.string(),
  label: z.string(),
  tips: z.array(z.string()),
  sources: z
    .array(
      z.object({
        id: z.string().nullish(),
        title: z.string().nullish(),
        url: z.string().nullish(),
      }),
    )
    .nullish(),
});
export type AdviceBlock = z.infer<typeof adviceBlockSchema>;

/** `acute` = Akut-Hinweis (Ambulanz / 155) zuerst und hervorgehoben; `general` = allgemeiner Hinweis. */
export const escalationSchema = z.object({
  level: z.enum(['acute', 'general']),
  text: z.string(),
  ambulance_phone: z.string().nullish(),
});
export type Escalation = z.infer<typeof escalationSchema>;

export const submitReceiptSchema = z.object({
  response_id: z.string(),
  recorded_at: z.string(),
  answered: z.number().int().nullish(),
  skipped: z.number().int().nullish(),
  message_key: z.string(),
  advice: z.array(adviceBlockSchema).nullish(),
  escalation: escalationSchema.nullish(),
});
export type SubmitReceipt = z.infer<typeof submitReceiptSchema>;

/* ---------- v2.0 adaptiver Check-in (POST /me/sessions, …/answers) ---------- */

export const sessionQuestionSchema = z.object({
  symptom_key: z.string(),
  attribute: attributeSchema,
  label: z.string(),
  text: z.string(),
  options: z.array(optionSchema),
  kind: z.enum(['gate', 'cascade', 'escalation', 'slot']),
  safety: z.boolean().nullish(),
});
export type SessionQuestion = z.infer<typeof sessionQuestionSchema>;

/** Nächste Fälligkeit (schedule.yaml); `due` ist im Vertrag nur als Objekt beschrieben, alles optional. */
export const dueSchema = z
  .object({
    next_due_at: z.string().nullish(),
    overdue: z.boolean().nullish(),
    interval_days: z.number().int().nullish(),
  })
  .passthrough();
export type Due = z.infer<typeof dueSchema>;

export const sessionStepSchema = z.object({
  session_id: z.string(),
  next: sessionQuestionSchema.nullish(),
  /** `max` ist nur eine Obergrenze der Fragen, kein Versprechen */
  progress: z.object({ asked: z.number().int(), max: z.number().int() }),
  stop: z
    .object({
      reason: z.enum(['decided', 'burden_cap', 'complete']),
      incomplete: z.boolean().nullish(),
    })
    .nullish(),
  receipt: submitReceiptSchema.nullish(),
  selection_reason: z.string().nullish(),
  due: dueSchema.nullish(),
});
export type SessionStep = z.infer<typeof sessionStepSchema>;

export function startSession(clientSessionId: string, lang: Lang): Promise<SessionStep> {
  return apiPost(
    '/waechter/me/sessions',
    { client_session_id: clientSessionId, lang },
    sessionStepSchema,
  );
}

/** v2.5: aktueller Stand der eigenen Sitzung (offen: nächste Frage; beendet: stop + receipt); fremd/unbekannt ⇒ 404. */
export function getSession(sessionId: string, signal?: AbortSignal): Promise<SessionStep> {
  return apiGet(
    `/waechter/me/sessions/${encodeURIComponent(sessionId)}`,
    sessionStepSchema,
    signal,
  );
}

export interface SessionAnswer {
  symptom_key: string;
  attribute: Attribute;
  /** 0–4; `null` = übersprungen */
  value: number | null;
}

export function answerSession(sessionId: string, body: SessionAnswer): Promise<SessionStep> {
  return apiPost(
    `/waechter/me/sessions/${encodeURIComponent(sessionId)}/answers`,
    body,
    sessionStepSchema,
  );
}

/**
 * T-31: letzte Antwort(en) der offenen Sitzung zurücknehmen (Zurück-Pfeil). `steps` ist der aktuelle
 * Stand `progress.asked` (Schutz vor Doppelklick); Antwort wie bei `answerSession`.
 */
export function undoSession(sessionId: string, steps: number): Promise<SessionStep> {
  return apiPost(
    `/waechter/me/sessions/${encodeURIComponent(sessionId)}/undo`,
    { steps },
    sessionStepSchema,
  );
}

/** Vertrag: `lang` ∈ {cs, en, de}; alles andere (z. B. „de-DE“) wird auf die Basissprache abgebildet. */
export function toLang(language: string | undefined): Lang {
  const base = (language ?? '').slice(0, 2).toLowerCase();
  return (LANGS as readonly string[]).includes(base) ? (base as Lang) : 'cs';
}

/**
 * Das Backend lokalisiert Meldungstexte, Begriffsnamen und Regime-Bezeichnungen nach `?lang=`
 * (Standard cs). Das Frontend schickt deshalb auf jeder Ärztin-Abfrage die aktive UI-Sprache mit.
 */
export function withLang(path: string, lang: Lang): string {
  return `${path}${path.includes('?') ? '&' : '?'}lang=${encodeURIComponent(lang)}`;
}

export function getMyQuestionnaire(lang: Lang, signal?: AbortSignal): Promise<Questionnaire> {
  return apiGet(
    `/waechter/me/questionnaire?lang=${encodeURIComponent(lang)}`,
    questionnaireSchema,
    signal,
  );
}

export function submitMyResponse(body: ResponseSubmit): Promise<SubmitReceipt> {
  return apiPost('/waechter/me/responses', body, submitReceiptSchema);
}

/** UUID v4 für `client_submission_id`; Rückfall, falls `crypto.randomUUID` fehlt (unsicherer Kontext). */
export function newSubmissionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/* ---------- Ärztinnenseite (Arbeitsliste, Benachrichtigungen) ---------- */

export const TRAFFIC_LIGHTS = ['red', 'yellow', 'grey', 'green'] as const;
export const trafficLightSchema = z.enum(TRAFFIC_LIGHTS);
export type TrafficLightLevel = z.infer<typeof trafficLightSchema>;

export const alertLevelSchema = z.enum(['red', 'yellow', 'grey']);
export type AlertLevel = z.infer<typeof alertLevelSchema>;

const alertBriefSchema = z.object({
  alert_id: z.string().nullish(),
  rule_id: z.string().nullish(),
  level: alertLevelSchema.nullish(),
  symptom_key: z.string().nullish(),
  headline: z.string().nullish(),
  created_at: z.string().nullish(),
});

export const worklistRowSchema = z.object({
  patient_id: z.string(),
  pseudonym: z.string(),
  display_name: z.string(),
  age: z.number().int().nullish(),
  regimen_id: z.string(),
  regimen_label: z.string().nullish(),
  cycle_day: z.number().int().nullish(),
  traffic_light: trafficLightSchema,
  open_alerts: z.number().int(),
  persisting: z.boolean().nullish(),
  evaluation_pending: z.boolean().nullish(),
  days_without_response: z.number().int().nullish(),
  top_alert: alertBriefSchema.nullish(),
  last_response_at: z.string().nullish(),
  next_visit_at: z.string().nullish(),
  synthetic: z.boolean().nullish(),
  /** T-22: Zahl unbestätigter Freitext-Zuordnungen (Hinweis, kein Alarm); fehlt bei ausgeschaltetem Freitext */
  free_text_unconfirmed: z.number().int().nonnegative().nullish(),
});
export type WorklistRow = z.infer<typeof worklistRowSchema>;

export const notificationSchema = z.object({
  notification_id: z.string(),
  at: z.string(),
  patient_id: z.string(),
  alert_id: z.string(),
  level: alertLevelSchema,
  channel: z.string().nullish(),
  text: z.string(),
});
export type Notification = z.infer<typeof notificationSchema>;

/** Reihenfolge der Antwort (rot > gelb > grau > grün, dann älteste Meldung) bestimmt der Server. */
export function getWorklist(lang: Lang, signal?: AbortSignal): Promise<WorklistRow[]> {
  return apiGet(withLang('/waechter/patients', lang), z.array(worklistRowSchema), signal);
}

export function getNotifications(lang: Lang, signal?: AbortSignal): Promise<Notification[]> {
  return apiGet(withLang('/waechter/notifications', lang), z.array(notificationSchema), signal);
}

/* ---------- Patienten-Cockpit (Übersicht, Meldungen mit Erklärung, KI-Kurzfassung, Belege) ---------- */

/* Triage-Stufen und Begründungen (v2.0/v2.8) – hier, weil Meldungen sie in `explanation.triage` tragen */
export const TRIAGE_LEVELS = ['GREEN', 'YELLOW', 'RED'] as const;
export const triageLevelSchema = z.enum(TRIAGE_LEVELS);
export type TriageLevel = z.infer<typeof triageLevelSchema>;

export const reasonCodeSchema = z.object({
  code: z.string(),
  text: z.string(),
  items: z.array(z.string()).nullish(),
  kind: z.enum(['shield', 'path', 'incomplete', 'leaf']).nullish(),
});
export type ReasonCode = z.infer<typeof reasonCodeSchema>;

/** v2.8: Triage-Entscheidung an der Meldung (R-TRI-RED/YEL bzw. an Bestandsmeldung angehängt). */
export const alertTriageSchema = z.object({
  level: triageLevelSchema,
  level_lo: triageLevelSchema.nullish(),
  level_hi: triageLevelSchema.nullish(),
  incomplete: z.boolean().nullish(),
  response_id: z.string().nullish(),
  tree_version: z.string().nullish(),
  // T-16G: Objekte laut Vertrag; ein Altbestand aus reinen Codes darf die Übersicht nie kippen.
  reason_codes: z
    .array(
      z.union([
        reasonCodeSchema,
        z.string().transform((code): ReasonCode => ({ code, text: code })),
      ]),
    )
    .nullish(),
});
export type AlertTriage = z.infer<typeof alertTriageSchema>;

export const explanationSchema = z.object({
  kind: z.enum(['threshold', 'baseline_delta', 'trend', 'missing', 'triage']),
  triage: alertTriageSchema.nullish(),
  params: z.record(z.string(), z.number()).default({}),
  observed: z.record(z.string(), z.number().nullable()).default({}),
  baseline_window: z
    .object({ from: z.string().nullish(), to: z.string().nullish() })
    .nullable()
    .nullish(),
  /** T-25: Das Baseline-Fenster beginnt beim Start des aktuellen Therapieschemas */
  baseline_limit: z
    .object({ reason: z.string(), regimen_id: z.string(), since: z.string() })
    .nullish(),
  cycle_day: z.number().int().nullish(),
  evidence: z.array(z.string()).default([]),
  rationale: z.string().nullish(),
});
export type Explanation = z.infer<typeof explanationSchema>;

export const alertSchema = z.object({
  alert_id: z.string(),
  patient_id: z.string(),
  rule_id: z.string(),
  rule_version: z.string(),
  level: alertLevelSchema,
  symptom_key: z.string().nullish(),
  attribute: z.string().nullish(),
  headline: z.string().nullish(),
  status: z.enum(['open', 'acknowledged']),
  created_at: z.string(),
  notified: z.boolean().nullish(),
  explanation: explanationSchema,
  acknowledgement: z
    .object({
      by: z.string().nullish(),
      at: z.string().nullish(),
      decision: z
        .enum(['contact_patient', 'visit_scheduled', 'no_action_needed', 'other'])
        .nullish(),
      note: z.string().nullish(),
    })
    .nullable()
    .nullish(),
});
export type Alert = z.infer<typeof alertSchema>;

export const summarySentenceSchema = z.object({
  text: z.string(),
  refs: z.array(z.string()).default([]),
  verified: z.boolean(),
});

export const summarySchema = z.object({
  summary_id: z.string(),
  generated_at: z.string(),
  generator: z.string(),
  mode: z.enum(['live', 'cached', 'fallback']),
  sentences: z.array(summarySentenceSchema),
  dropped_sentences: z.number().int(),
  unknown_topics: z.array(z.string()).nullish(),
  fact_count: z.number().int().nullish(),
  disclaimer_key: z.string(),
  provenance_id: z.string().nullish(),
});
export type Summary = z.infer<typeof summarySchema>;

export const sinceLastVisitRowSchema = z.object({
  symptom_key: z.string(),
  label: z.string(),
  attribute: z.string().nullish(),
  first: z.number().int().nullish(),
  last: z.number().int().nullish(),
  max: z.number().int().nullish(),
  direction: z.enum(['up', 'down', 'flat', 'unknown']).nullish(),
  alerts: z.number().int().nullish(),
  missing_days: z.number().int().nullish(),
});
export type SinceLastVisitRow = z.infer<typeof sinceLastVisitRowSchema>;

/** CTCAE-Subraum des aktuellen Fragebogens (T-25): Begriffe, die die Ärztin aufnehmen kann */
export const trackedSymptomSchema = z.object({
  ctcae_term_id: z.string(),
  term_en: z.string(),
  label: z.string(),
});
export type TrackedSymptom = z.infer<typeof trackedSymptomSchema>;

export const overviewSchema = z.object({
  patient: z.object({
    patient_id: z.string(),
    pseudonym: z.string(),
    display_name: z.string(),
    age: z.number().int().nullish(),
    sex: z.string().nullish(),
    language: z.string().nullish(),
    diagnosis_text: z.string().nullish(),
    synthetic: z.boolean().nullish(),
  }),
  therapy: z.object({
    fact_id: z.string().nullish(),
    regimen_id: z.string(),
    regimen_label: z.string().nullish(),
    drugs: z.array(z.object({ name: z.string(), atc: z.string().nullish() })).nullish(),
    cycle_start: z.string().nullish(),
    cycle_day: z.number().int().nullish(),
    /** Vertrag v1.3: lokalisierte Texte */
    watch_notes: z.array(z.string()).nullish(),
  }),
  traffic_light: trafficLightSchema,
  open_alerts: z.array(alertSchema),
  /** Vertrag v1.3 (DR-011): quittierte Meldungen, deren Wert weiter besteht */
  persisting: z.boolean().nullish(),
  persisting_alerts: z.array(alertSchema).nullish(),
  evaluation_pending: z.boolean().nullish(),
  days_without_response: z.number().int().nullish(),
  last_visit_at: z.string().nullish(),
  next_visit_at: z.string().nullish(),
  last_response_at: z.string().nullish(),
  since_last_visit: z.array(sinceLastVisitRowSchema),
  summary: summarySchema.nullish(),
  report_sections: z.array(z.string()).nullish(),
  tracked_symptoms: z.array(trackedSymptomSchema).nullish(),
});
export type Overview = z.infer<typeof overviewSchema>;

export const factSchema = z.object({
  fact_id: z.string(),
  kind: z.enum(['response', 'observation', 'alert', 'visit', 'assessment', 'therapy', 'free_text']),
  at: z.string(),
  label: z.string(),
  data: z.record(z.string(), z.unknown()).default({}),
});
export type Fact = z.infer<typeof factSchema>;

const patientPath = (patientId: string): string =>
  `/waechter/patients/${encodeURIComponent(patientId)}`;

export function getOverview(
  patientId: string,
  lang: Lang,
  signal?: AbortSignal,
): Promise<Overview> {
  return apiGet(withLang(`${patientPath(patientId)}/overview`, lang), overviewSchema, signal);
}

/** KI-Zusammenfassung (Entwurf) neu erzeugen; der Server verwirft unbelegte Sätze. */
export function generateSummary(patientId: string, lang: Lang): Promise<Summary> {
  return apiPost(withLang(`${patientPath(patientId)}/summary`, lang), {}, summarySchema);
}

export function getFact(
  patientId: string,
  factId: string,
  lang: Lang,
  signal?: AbortSignal,
): Promise<Fact> {
  return apiGet(
    withLang(`${patientPath(patientId)}/facts/${encodeURIComponent(factId)}`, lang),
    factSchema,
    signal,
  );
}

/* ---------- Verlauf (Timeline) und Regelkonfiguration ---------- */

export const seriesPointSchema = z.object({
  t: z.string(),
  value: z.number().int().nullable(),
  fact_id: z.string(),
});
export type SeriesPoint = z.infer<typeof seriesPointSchema>;

export const seriesSchema = z.object({
  symptom_key: z.string(),
  attribute: z.string(),
  label: z.string(),
  points: z.array(seriesPointSchema),
});
export type Series = z.infer<typeof seriesSchema>;

export const assessmentSchema = z.object({
  assessment_id: z.string(),
  fact_id: z.string().nullish(),
  patient_id: z.string().nullish(),
  assessed_at: z.string(),
  assessed_by: z.string().nullish(),
  ctcae_version: z.string().nullish(),
  related_alert_ids: z.array(z.string()).nullish(),
  items: z.array(
    z.object({
      ctcae_term_id: z.string(),
      term_en: z.string().nullish(),
      meddra_code: z.string().nullish(),
      grade: z.number().int(),
      attribution: z.string().nullish(),
      note: z.string().nullish(),
    }),
  ),
});
export type Assessment = z.infer<typeof assessmentSchema>;

export const timelineSchema = z.object({
  patient_id: z.string(),
  from: z.string(),
  to: z.string(),
  series: z.array(seriesSchema),
  alerts: z.array(alertSchema),
  /** Prager Kalendertage ohne Eingabe, `YYYY-MM-DD` */
  missing_days: z.array(z.string()),
  visits: z.array(
    z.object({
      fact_id: z.string().nullish(),
      at: z.string(),
      kind: z.enum(['past', 'planned']).nullish(),
    }),
  ),
  assessments: z.array(assessmentSchema),
  therapy_events: z
    .array(z.object({ fact_id: z.string().nullish(), at: z.string(), label: z.string() }))
    .nullish(),
});
export type Timeline = z.infer<typeof timelineSchema>;

export interface TimelineRange {
  /** ISO 8601 (UTC); fehlt = ab Beginn der Aufzeichnung */
  from?: string;
  to?: string;
}

export function getTimeline(
  patientId: string,
  range: TimelineRange,
  lang: Lang,
  signal?: AbortSignal,
): Promise<Timeline> {
  const query = new URLSearchParams();
  if (range.from) query.set('from', range.from);
  if (range.to) query.set('to', range.to);
  query.set('lang', lang);
  return apiGet(`${patientPath(patientId)}/timeline?${query.toString()}`, timelineSchema, signal);
}

/**
 * Mehrsprachiger Text der Konfiguration: Datei-Inhalt `{cs,en,…}`; ab Vertrag v1.6 darf der Server ihn
 * schon in der Anfragesprache als String liefern. Beides wird gelesen.
 */
export const localizedSchema = z.union([z.string(), z.record(z.string(), z.string())]);
export type Localized = z.infer<typeof localizedSchema>;

/** Text in `lang`, sonst en, cs, der erste vorhandene; leer, wenn nichts vorliegt. */
export function localized(value: Localized | null | undefined, lang: Lang): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return value[lang] ?? value.en ?? value.cs ?? Object.values(value)[0] ?? '';
}

export const configRuleSchema = z.object({
  id: z.string(),
  kind: z.enum(['threshold', 'baseline_delta', 'trend', 'missing']),
  level: alertLevelSchema,
  enabled: z.boolean(),
  symptom_keys: z.array(z.string()).nullish(),
  attributes: z.array(z.string()).nullish(),
  params: z.record(z.string(), z.number()).default({}),
  rationale: localizedSchema.nullish(),
  source_id: z.string().nullish(),
});
export type ConfigRule = z.infer<typeof configRuleSchema>;

export const noiseSchema = z.object({
  notify_levels: z.array(alertLevelSchema),
  digest_levels: z.array(alertLevelSchema),
  cooldown_hours: z.number(),
});
export type Noise = z.infer<typeof noiseSchema>;

export const rulesFileSchema = z.object({
  version: z.string(),
  rules: z.array(configRuleSchema),
  noise: noiseSchema.nullish(),
});
export type RulesFile = z.infer<typeof rulesFileSchema>;

export const REPORT_SECTIONS = [
  'summary',
  'alerts',
  'timeline',
  'since_last_visit',
  'therapy',
  'assessments',
  'missing_data',
  'audit',
] as const;
export type ReportSection = (typeof REPORT_SECTIONS)[number];

export const REPORT_SINCE = ['last_visit', 'days_14', 'days_28'] as const;
export type ReportSince = (typeof REPORT_SINCE)[number];

export const reportFileSchema = z.object({
  version: z.string(),
  since: z.enum(REPORT_SINCE).nullish(),
  sections: z.array(z.string()),
});
export type ReportFile = z.infer<typeof reportFileSchema>;

const regimenSchema = z.object({
  id: z.string(),
  label: localizedSchema,
  cycle_length_days: z.number().nullish(),
  drugs: z.array(z.object({ name: z.string(), atc: z.string().nullish() })).nullish(),
  symptom_keys: z.array(z.string()).nullish(),
});
export type Regimen = z.infer<typeof regimenSchema>;

const configItemSchema = z.object({
  symptom_key: z.string(),
  core: z.boolean().nullish(),
  label: localizedSchema,
});

/** v2.1 Tipp-Regeln (advice.yaml): ID, Symptom, Wertebereich, Tipps, Quellen, Status – nur zum Lesen. */
export const adviceRuleSchema = z.object({
  id: z.string(),
  symptom_key: z.string(),
  min_value: z.number().int(),
  max_value: z.number().int().nullish(),
  status: z.string().nullish(),
  tips: z.array(localizedSchema).nullish(),
  source_ids: z.array(z.string()).nullish(),
});
export type AdviceRule = z.infer<typeof adviceRuleSchema>;

export const adviceFileSchema = z.object({
  version: z.string().nullish(),
  advice: z.array(adviceRuleSchema),
  sources: z
    .array(z.object({ id: z.string(), title: z.string().nullish(), url: z.string().nullish() }))
    .nullish(),
});
export type AdviceFile = z.infer<typeof adviceFileSchema>;

export const configBundleSchema = z.object({
  items: z.object({ items: z.array(configItemSchema) }),
  regimens: z.object({ regimens: z.array(regimenSchema) }),
  rules: rulesFileSchema,
  report: reportFileSchema,
  advice: adviceFileSchema.nullish(),
});
export type ConfigBundle = z.infer<typeof configBundleSchema>;
/** Alter Name aus F-04 (Schwellenlinien lesen nur `rules`); gleiches Schema. */
export const configRulesSchema = configBundleSchema;
export type ConfigRules = ConfigBundle['rules'];

export function getConfig(lang: Lang, signal?: AbortSignal): Promise<ConfigBundle> {
  return apiGet(withLang('/waechter/config', lang), configBundleSchema, signal);
}

export function getConfigRules(lang: Lang, signal?: AbortSignal): Promise<ConfigRules> {
  return getConfig(lang, signal).then((bundle) => bundle.rules);
}

/** Version einer Konfiguration (Vertrag v1.5, `GET /config/history`). */
export const historyRowSchema = z.object({
  version: z.string(),
  changed_at: z.string(),
  changed_by: z.string().nullish(),
  change_note: z.string().nullish(),
  active: z.boolean(),
});
export type HistoryRow = z.infer<typeof historyRowSchema>;

export function getConfigHistory(
  kind: 'rules' | 'report',
  lang: Lang,
  signal?: AbortSignal,
): Promise<HistoryRow[]> {
  return apiGet(
    withLang(`/waechter/config/history?kind=${kind}`, lang),
    z.array(historyRowSchema),
    signal,
  );
}

export const configStateSchema = z
  .object({ version: z.string(), changed_at: z.string(), changed_by: z.string().nullish() })
  .passthrough();
export type ConfigState = z.infer<typeof configStateSchema>;

export const CHANGE_NOTE_MAX_LENGTH = 300;

export interface RulesUpdate {
  expected_version: string;
  /** vollständige RulesFile ohne `version` (der Server vergibt rules-vN+1) */
  rules: { rules: ConfigRule[]; noise?: Noise };
  /** Pflicht (Nachvollziehbarkeit), höchstens 300 Zeichen */
  change_note: string;
}

export function updateRules(body: RulesUpdate): Promise<ConfigState> {
  return apiPut('/waechter/config/rules', body, configStateSchema);
}

export interface ReportUpdate {
  expected_version: string;
  report: { since: ReportSince; sections: ReportSection[] };
}

export function updateReport(body: ReportUpdate): Promise<ConfigState> {
  return apiPut('/waechter/config/report', body, configStateSchema);
}

/** Auszug der Audit-Spur einer Patientin (Vertrag: `GET /patients/{id}/audit`). */
export const auditRowSchema = z.object({
  at: z.string(),
  actor_role: z.string().nullish(),
  action: z.string(),
  target_type: z.string().nullish(),
  target_id: z.string().nullish(),
});
export type AuditRow = z.infer<typeof auditRowSchema>;

export function getAudit(patientId: string, signal?: AbortSignal): Promise<AuditRow[]> {
  return apiGet(`${patientPath(patientId)}/audit`, z.array(auditRowSchema), signal);
}

export type FhirBundleType = 'collection' | 'transaction';

/**
 * FHIR-R4-Bundle als Datei laden (`GET /patients/{id}/fhir`, `application/fhir+json`). Der Körper wird
 * nicht geparst oder geloggt; Fehler im Plattformformat werden zu `ApiClientError`.
 */
export async function downloadFhirBundle(
  patientId: string,
  signal?: AbortSignal,
  type: FhirBundleType = 'collection',
): Promise<Blob> {
  let response: Response;
  try {
    // Standard bleibt type=collection (unverändert); type=transaction = Transaction-Bundle (v2.6)
    const query = type === 'transaction' ? '?type=transaction' : '';
    response = await fetch(`${API_BASE}${patientPath(patientId)}/fhir${query}`, {
      credentials: 'same-origin',
      headers: { Accept: 'application/fhir+json, application/json' },
      signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiClientError(0, 'network_error', 'Network request failed');
  }
  if (!response.ok) {
    throw new ApiClientError(response.status, 'export_failed', response.statusText);
  }
  return response.blob();
}

/* ---------- Quittieren und CTCAE-Aufnahme ---------- */

export const DECISIONS = [
  'contact_patient',
  'visit_scheduled',
  'no_action_needed',
  'other',
] as const;
export type Decision = (typeof DECISIONS)[number];

export interface AcknowledgeRequest {
  decision: Decision;
  /** höchstens 500 Zeichen */
  note?: string;
}

export const NOTE_MAX_LENGTH = 500;

export function getAlert(alertId: string, lang: Lang, signal?: AbortSignal): Promise<Alert> {
  return apiGet(
    withLang(`/waechter/alerts/${encodeURIComponent(alertId)}`, lang),
    alertSchema,
    signal,
  );
}

/** Bedingt: nur aus Status „open“; sonst 409 `alert_not_open`. */
export function acknowledgeAlert(
  alertId: string,
  body: AcknowledgeRequest,
  lang: Lang,
): Promise<Alert> {
  return apiPost(
    withLang(`/waechter/alerts/${encodeURIComponent(alertId)}/acknowledge`, lang),
    body,
    alertSchema,
  );
}

export const ATTRIBUTIONS = [
  'unrelated',
  'unlikely',
  'possible',
  'probable',
  'definite',
  'unknown',
] as const;
export type Attribution = (typeof ATTRIBUTIONS)[number];

const templateSourceSchema = z.union([
  z.string(),
  z
    .object({
      id: z.string().nullish(),
      title: z.string().nullish(),
      url: z.string().nullish(),
    })
    .passthrough(),
]);

export const templateTermSchema = z.object({
  ctcae_term_id: z.string(),
  term_en: z.string(),
  label: z.string().nullish(),
  meddra_code: z.string(),
  /** nur in CTCAE definierte Grade (Schlüssel „1“ … „5“); Grad 0 = nicht vorhanden gilt immer */
  grades: z.record(z.string(), z.string()).default({}),
  symptom_keys: z.array(z.string()).default([]),
  pro_hint: z.record(z.string(), z.number().nullable()).nullish(),
  last_grade: z.number().int().nullish(),
});
export type TemplateTerm = z.infer<typeof templateTermSchema>;

export const assessmentTemplateSchema = z.object({
  patient_id: z.string(),
  ctcae_version: z.string(),
  terms: z.array(templateTermSchema),
  source: templateSourceSchema.nullish(),
});
export type AssessmentTemplate = z.infer<typeof assessmentTemplateSchema>;

export interface AssessmentCreate {
  client_submission_id: string;
  related_alert_ids?: string[];
  items: { ctcae_term_id: string; grade: number; attribution?: Attribution; note?: string }[];
}

export function getAssessmentTemplate(
  patientId: string,
  lang: Lang,
  signal?: AbortSignal,
): Promise<AssessmentTemplate> {
  return apiGet(
    withLang(`${patientPath(patientId)}/assessment-template`, lang),
    assessmentTemplateSchema,
    signal,
  );
}

/** Idempotent über `client_submission_id` (200 bei Wiederholung, 201 bei neu). */
export function createAssessment(patientId: string, body: AssessmentCreate): Promise<Assessment> {
  return apiPost(`${patientPath(patientId)}/assessments`, body, assessmentSchema);
}

/* ---------- T-34 Einschreibung: neue synthetische Patientin (nur Klinik-Datensatz) ---------- */

export interface EnrollmentCreate {
  diagnosis_code: string | null;
  regimen_id: string;
  cycle_start: string;
  language: Lang;
  client_request_id: string;
}

export const enrollmentReceiptSchema = z.object({
  patient_id: z.string(),
  pseudonym: z.string(),
});
export type EnrollmentReceipt = z.infer<typeof enrollmentReceiptSchema>;

/** 201 angelegt, 200 bei gleicher `client_request_id` (gleiche Antwort). */
export function enrollPatient(body: EnrollmentCreate): Promise<EnrollmentReceipt> {
  return apiPost('/waechter/patients', body, enrollmentReceiptSchema);
}

/* ---------- v2.0/v2.1 Triage: Befundkarte und Regelkarte (nur lesen) ---------- */

export const triageDecisionSchema = z.object({
  response_id: z.string(),
  decided_at: z.string().nullish(),
  level: triageLevelSchema,
  level_lo: triageLevelSchema,
  level_hi: triageLevelSchema,
  incomplete: z.boolean(),
  profile_id: z.string().nullish(),
  rule_version: z.string(),
  tree_version: z.string(),
  leaf_ids: z.object({ yellow: z.string().nullish(), red: z.string().nullish() }).nullish(),
  reason_codes: z.array(reasonCodeSchema),
  counterfactuals: z
    .array(
      z.object({
        direction: z.enum(['lower', 'raise']),
        text: z.string(),
        /** v2.7: shield = Hinweis „Boden F_X verhindert Senkung“ (eigener Schloss-Eintrag, kein Satzteil) */
        kind: z.enum(['change', 'shield']).nullish(),
      }),
    )
    .nullish(),
  recommendations: z
    .array(
      z.object({
        rule_id: z.string(),
        symptom_key: z.string(),
        outcome: z.enum(['shown', 'suppressed_acute']),
        value: z.number().int().nullish(),
      }),
    )
    .nullish(),
  asked_questions: z.number().int().nullish(),
  full_questions: z.number().int().nullish(),
  status: z.string().nullish(),
});
export type TriageDecision = z.infer<typeof triageDecisionSchema>;

/** Befundkarte der letzten (oder der gewählten) Antwort; 404 = noch keine Triage/API (dezenter Leerzustand). */
export function getTriage(
  patientId: string,
  responseId: string | null,
  lang: Lang,
  signal?: AbortSignal,
): Promise<TriageDecision> {
  const query = new URLSearchParams();
  if (responseId) query.set('response_id', responseId);
  query.set('lang', lang);
  return apiGet(
    `${patientPath(patientId)}/triage?${query.toString()}`,
    triageDecisionSchema,
    signal,
  );
}

const treeSizeSchema = z.object({ leaves: z.number().int(), depth: z.number().int() });

export const triageProfileSchema = z.object({
  profile_id: z.string(),
  regimen_ids: z.array(z.string()).nullish(),
  tree_version: z.string().nullish(),
  trees: z.object({ yellow: treeSizeSchema.nullish(), red: treeSizeSchema.nullish() }).nullish(),
  verification: z
    .object({
      points: z.number().int(),
      under: z.number().int(),
      over: z.number().int(),
      monotone_violations: z.number().int(),
      scope: z.string().nullish(),
    })
    .nullish(),
  rules: z
    .array(
      z.object({
        level: z.string(),
        text: z.string(),
        leaf_id: z.string().nullish(),
        teacher_rule_ids: z.array(z.string()).nullish(),
      }),
    )
    .nullish(),
  floors: z
    .array(
      z.object({
        id: z.string(),
        text: z.string(),
        min_level: z.string(),
        locked: z.boolean().nullish(),
        status: z.string().nullish(),
      }),
    )
    .nullish(),
  placeholders: z.array(z.string()).nullish(),
});
export type TriageProfile = z.infer<typeof triageProfileSchema>;

export const triageRuleCardSchema = z.object({
  kb_version: z.string(),
  compiler_version: z.string().nullish(),
  profiles: z.array(triageProfileSchema),
});
export type TriageRuleCard = z.infer<typeof triageRuleCardSchema>;

export function getTriageConfig(lang: Lang, signal?: AbortSignal): Promise<TriageRuleCard> {
  return apiGet(withLang('/waechter/config/triage', lang), triageRuleCardSchema, signal);
}

/* ---------- v2.3 Arzneimittelsuche der Ärztin (GET /medications, /medications/{id}) ---------- */

export const MEDICATION_MATCHES = ['sukl_code', 'atc', 'name', 'synonym', 'id'] as const;

export const medicationSchema = z.object({
  medication_id: z.string(),
  inn: z.string(),
  trade_name: z.string().nullish(),
  sukl_code: z.string().nullish(),
  atc: z.string(),
  /** reviewed | draft | … | sukl_only (T-33: nur SÚKL-Datenbank) */
  status: z.string().nullish(),
  regimens: z.array(
    z.object({
      regimen_id: z.string(),
      label: z.string().nullish(),
      symptom_keys: z.array(z.string()).nullish(),
    }),
  ),
  spc: z
    .object({
      title: z.string().nullish(),
      url: z.string().nullish(),
      locator: z.string().nullish(),
    })
    .nullish(),
  /** worüber gefunden; in der Detailansicht ohne Bedeutung */
  match: z.enum(MEDICATION_MATCHES).nullish(),
  patients_on_regimen: z.number().int().nullish(),
  /** T-33: nur bei status `sukl_only` – Basisdaten aus SÚKL Open Data, kein Therapieprofil */
  sukl: z
    .object({
      name: z.string().nullish(),
      strength: z.string().nullish(),
      package: z.string().nullish(),
      form: z.string().nullish(),
      holder: z.string().nullish(),
    })
    .nullish(),
});
export type Medication = z.infer<typeof medicationSchema>;

/** Höchstens 20 Treffer, sortiert: exakte Nummer > Namensanfang > Teilwort (Server); q 2–60 Zeichen, sonst 422. */
export function searchMedications(
  query: string,
  lang: Lang,
  signal?: AbortSignal,
): Promise<Medication[]> {
  return apiGet(
    withLang(`/waechter/medications?q=${encodeURIComponent(query)}`, lang),
    z.array(medicationSchema),
    signal,
  );
}

export function getMedication(
  medicationId: string,
  lang: Lang,
  signal?: AbortSignal,
): Promise<Medication> {
  return apiGet(
    withLang(`/waechter/medications/${encodeURIComponent(medicationId)}`, lang),
    medicationSchema,
    signal,
  );
}

/* ---------- v2.6 FHIR-Push (nur Administration) ---------- */

export const fhirPushSchema = z.object({
  status: z.enum(['sent', 'disabled', 'failed']),
  http_status: z.number().int().nullish(),
  entries: z.number().int().nullish(),
  created: z.number().int().nullish(),
  updated: z.number().int().nullish(),
  /** Kurztexte ohne Patientendaten (Vertrag) */
  errors: z.array(z.string()).nullish(),
});
export type FhirPushResult = z.infer<typeof fhirPushSchema>;

/** Transaction-Bundle an den konfigurierten FHIR-R4-Server senden (`POST /patients/{id}/fhir/push`). */
export function pushFhir(patientId: string): Promise<FhirPushResult> {
  return apiPost(`${patientPath(patientId)}/fhir/push`, {}, fhirPushSchema);
}

/* ---------- v2.9 Freitext (T-22): POST /me/free-text, GET /patients/{id}/free-texts ---------- */

export const freeTextFeatureSchema = z.object({
  enabled: z.boolean(),
  max_length: z.number().int().positive(),
});
export type FreeTextFeature = z.infer<typeof freeTextFeatureSchema>;

/** Folgefrage-Karte zu einer geprüften Zuordnung: Standardfragen wie im Check-in (kritisch zuerst). */
export const followupCardSchema = z.object({
  free_text_id: z.string(),
  symptom_key: z.string(),
  label: z.string(),
  quote: z.string(),
  critical: z.boolean(),
  questions: z.array(questionSchema),
});
export type FollowupCard = z.infer<typeof followupCardSchema>;

export const freeTextReceiptSchema = z.object({
  free_text_id: z.string(),
  response_id: z.string(),
  saved: z.literal(true),
  followups: z.array(followupCardSchema),
});
export type FreeTextReceipt = z.infer<typeof freeTextReceiptSchema>;

export const FREE_TEXT_MODES = ['template', 'live', 'fallback'] as const;

/** KI-Vorschlag, nicht bewertet: `text.slice(start, end) === quote` (vom Server geprüft). */
export const freeTextSuggestionSchema = z.object({
  symptom_key: z.string(),
  label: z.string(),
  attribute: z.string().nullable(),
  /** Vorschlagswert des Modells: nur für die Ärztin, zählt nie als Antwort */
  proposed_value: z.number().int().nullable(),
  quote: z.string(),
  start: z.number().int().nonnegative(),
  end: z.number().int().positive(),
  in_questionnaire: z.boolean(),
  /** alle Folgefragen dieses Symptoms beantwortet (Antwort der Patientin, nicht der Vorschlag) */
  confirmed: z.boolean(),
  answers: z.array(z.object({ attribute: z.string(), value: z.number().int().nullable() })),
  /** Quelle der Zuordnung (T-22F): Sprachmodell oder Wortliste (Sicherheitsnetz bei kritischen Symptomen) */
  source: z.enum(['model', 'wordlist']).nullish(),
});
export type FreeTextSuggestion = z.infer<typeof freeTextSuggestionSchema>;

export const freeTextSchema = z.object({
  free_text_id: z.string(),
  response_id: z.string(),
  patient_id: z.string(),
  text: z.string(),
  lang: z.enum(LANGS),
  created_at: z.string(),
  suggestions: z.array(freeTextSuggestionSchema),
  mapper: z.string(),
  mode: z.enum(FREE_TEXT_MODES),
  rejected_suggestions: z.number().int().nonnegative(),
  /** Zahl der Symptome mit unbeantworteter Folgefrage (Hinweis „unbestätigt“, kein Alarm) */
  unconfirmed: z.number().int().nonnegative(),
});
export type FreeText = z.infer<typeof freeTextSchema>;

export interface FreeTextSubmit {
  response_id: string;
  text: string;
  lang?: Lang;
}

export function postFreeText(body: FreeTextSubmit): Promise<FreeTextReceipt> {
  return apiPost('/waechter/me/free-text', body, freeTextReceiptSchema);
}

export function getFreeTexts(
  patientId: string,
  lang: Lang,
  signal?: AbortSignal,
): Promise<FreeText[]> {
  return apiGet(
    withLang(`${patientPath(patientId)}/free-texts`, lang),
    z.array(freeTextSchema),
    signal,
  );
}

export function getFollowupCards(lang: Lang, signal?: AbortSignal): Promise<FollowupCard[]> {
  return apiGet(
    withLang('/waechter/me/free-text/followups', lang),
    z.array(followupCardSchema),
    signal,
  );
}

export interface FollowupAnswers {
  client_submission_id: string;
  answers: SubmitAnswer[];
}

/** Antwort auf Folgefragen: normale Antwort (`source = free_text_followup`) mit Beleg wie im Check-in. */
export function answerFollowups(freeTextId: string, body: FollowupAnswers): Promise<SubmitReceipt> {
  return apiPost(
    `/waechter/me/free-text/${encodeURIComponent(freeTextId)}/answers`,
    body,
    submitReceiptSchema,
  );
}
