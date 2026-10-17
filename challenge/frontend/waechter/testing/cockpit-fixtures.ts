import type {
  Alert,
  Assessment,
  AssessmentTemplate,
  Fact,
  Overview,
  Summary,
  Timeline,
  WorklistRow,
} from '../api/client';
import { META_FIXTURE } from '../../../../platform/frontend/src/test/render';
import { ANCHOR } from './fixtures';

/** Testdaten (synthetisch) für das Patienten-Cockpit. */

export const ALERT_RED: Alert = {
  alert_id: 'al-1',
  patient_id: 'pat-1',
  rule_id: 'R-URG-01',
  rule_version: 'rules-v1',
  level: 'red',
  symptom_key: 'fever',
  attribute: 'presence',
  headline: 'Fieber gemeldet',
  status: 'open',
  created_at: '2026-10-17T06:00:00+02:00',
  notified: true,
  explanation: {
    kind: 'threshold',
    params: { min_value: 1 },
    observed: { value: 1 },
    baseline_window: null,
    cycle_day: 8,
    evidence: ['resp-101', 'obs-201'],
    rationale: 'Fieber wurde mit 1 angegeben; Schwelle: Wert ≥ 1.',
  },
};

export const ALERT_YELLOW: Alert = {
  alert_id: 'al-2',
  patient_id: 'pat-1',
  rule_id: 'R-DLT-01',
  rule_version: 'rules-v1',
  level: 'yellow',
  symptom_key: 'nausea',
  attribute: 'severity',
  headline: 'Übelkeit stärker als gewohnt',
  status: 'open',
  created_at: '2026-10-16T09:00:00+02:00',
  explanation: {
    kind: 'baseline_delta',
    params: { baseline_days: 7, min_delta: 2, min_value: 2 },
    observed: { value: 3, baseline: 1, delta: 2, slope_per_day: null },
    baseline_window: { from: '2026-10-09T09:00:00+02:00', to: '2026-10-16T09:00:00+02:00' },
    cycle_day: 7,
    evidence: ['obs-202'],
    rationale: 'Wert 3 liegt 2 über der Baseline 1.',
  },
};

export const SUMMARY: Summary = {
  summary_id: 'sum-1',
  generated_at: '2026-10-17T08:00:00+02:00',
  generator: 'template-v1',
  mode: 'fallback',
  sentences: [
    { text: 'Fieber wurde mit dem Wert 1 angegeben.', refs: ['resp-101'], verified: true },
    { text: 'Übelkeit stieg von 1 auf 3.', refs: ['obs-202', 'obs-201'], verified: true },
    { text: 'Zur Müdigkeit liegt kein letzter Wert vor.', refs: [], verified: false },
  ],
  dropped_sentences: 2,
  unknown_topics: ['Laborwerte'],
  fact_count: 12,
  disclaimer_key: 'summary.disclaimer',
};

export const NEW_SUMMARY: Summary = {
  summary_id: 'sum-2',
  generated_at: '2026-10-17T09:00:00+02:00',
  generator: 'azure-openai:test',
  mode: 'live',
  sentences: [{ text: 'Neue Kurzfassung zu Fieber.', refs: ['resp-101'], verified: true }],
  dropped_sentences: 0,
  disclaimer_key: 'summary.disclaimer',
};

export const OVERVIEW: Overview = {
  patient: {
    patient_id: 'pat-1',
    pseudonym: 'SYN-0001',
    display_name: 'Rita Rot',
    age: 62,
    sex: 'f',
    language: 'cs',
    diagnosis_text: 'Mammakarzinom (synthetisch)',
    synthetic: true,
  },
  therapy: {
    fact_id: 'ther-1',
    regimen_id: 'regimen-a',
    regimen_label: 'Regime A',
    drugs: [
      { name: 'Wirkstoff X', atc: 'L01XX01' },
      { name: 'Wirkstoff Y', atc: 'L01YY02' },
    ],
    cycle_start: '2026-10-09',
    cycle_day: 8,
    watch_notes: ['Fieber im Zyklus beobachten', 'Übelkeit nach der Gabe'],
  },
  traffic_light: 'red',
  // bewusst gelb zuerst: das Cockpit zeigt rote Meldungen zuerst
  open_alerts: [ALERT_YELLOW, ALERT_RED],
  last_visit_at: '2026-10-10T10:00:00+02:00',
  next_visit_at: '2026-10-20T10:00:00+02:00',
  last_response_at: '2026-10-17T06:00:00+02:00',
  since_last_visit: [
    {
      symptom_key: 'nausea',
      label: 'Übelkeit',
      attribute: 'severity',
      first: 1,
      last: 3,
      max: 3,
      direction: 'up',
      alerts: 1,
      missing_days: 0,
    },
    {
      symptom_key: 'fever',
      label: 'Fieber',
      attribute: 'presence',
      first: 0,
      last: 1,
      max: 1,
      direction: 'flat',
      alerts: 1,
      missing_days: 1,
    },
    {
      symptom_key: 'fatigue',
      label: 'Müdigkeit',
      attribute: 'severity',
      first: null,
      last: null,
      max: null,
      direction: 'unknown',
      alerts: 0,
      missing_days: 3,
    },
  ],
  summary: SUMMARY,
};

/** Übersicht ohne Meldungen und ohne Kurzfassung (grün). */
export const OVERVIEW_QUIET: Overview = {
  ...OVERVIEW,
  traffic_light: 'green',
  open_alerts: [],
  since_last_visit: [],
  summary: null,
  therapy: { ...OVERVIEW.therapy, watch_notes: [] },
};

export function factFor(factId: string): Fact {
  return {
    fact_id: factId,
    kind: factId.startsWith('obs') ? 'observation' : 'response',
    at: '2026-10-17T06:00:00+02:00',
    label: `Beleg ${factId}`,
    data: { symptom_key: 'fever', attribute: 'presence', value: 1, channel: 'web', note: null },
  };
}

/** Minimale Übersicht zu einer Arbeitslistenzeile (für Navigationstests). */
export function overviewForRow(row: WorklistRow): Overview {
  return {
    ...OVERVIEW_QUIET,
    patient: {
      patient_id: row.patient_id,
      pseudonym: row.pseudonym,
      display_name: row.display_name,
      synthetic: true,
    },
    traffic_light: row.traffic_light,
  };
}

/** `/meta` mit der Erweiterung des Vertrags v1.2 (DR-009); ohne `withServerNow` fehlt sie. */
export function metaBody(withServerNow = true): Record<string, unknown> {
  return {
    ...META_FIXTURE,
    challenge_loaded: true,
    ...(withServerNow
      ? {
          waechter: {
            server_now: ANCHOR,
            timezone: 'Europe/Prague',
            content_versions: { items: 'items-v1', rules: 'rules-v1', report: 'report-v1' },
          },
        }
      : {}),
  };
}

const point = (t: string, value: number | null, factId: string) => ({ t, value, fact_id: factId });

/** Alle Zeiten Europe/Prague (UTC+2). Server-Reihenfolge der Serien: Müdigkeit, Übelkeit, Fieber. */
export const TIMELINE: Timeline = {
  patient_id: 'pat-1',
  from: '2026-10-10T10:00:00+02:00',
  to: '2026-10-17T09:00:00+02:00',
  series: [
    {
      symptom_key: 'fatigue',
      attribute: 'severity',
      label: 'Müdigkeit',
      points: [
        point('2026-10-13T08:00:00+02:00', 2, 'obs-401'),
        point('2026-10-17T06:00:00+02:00', 2, 'obs-402'),
      ],
    },
    {
      symptom_key: 'nausea',
      attribute: 'severity',
      label: 'Übelkeit',
      points: [
        point('2026-10-12T08:00:00+02:00', 1, 'obs-211'),
        point('2026-10-13T08:00:00+02:00', 1, 'obs-212'),
        point('2026-10-14T08:00:00+02:00', 2, 'obs-213'),
        point('2026-10-16T08:00:00+02:00', 3, 'obs-202'),
        point('2026-10-17T06:00:00+02:00', 3, 'obs-203'),
      ],
    },
    {
      symptom_key: 'fever',
      attribute: 'presence',
      label: 'Fieber',
      points: [
        point('2026-10-12T08:00:00+02:00', 0, 'obs-301'),
        point('2026-10-13T08:00:00+02:00', 0, 'obs-302'),
        point('2026-10-14T08:00:00+02:00', null, 'obs-303'),
        point('2026-10-15T08:00:00+02:00', 0, 'obs-304'),
        point('2026-10-17T06:00:00+02:00', 1, 'obs-201'),
      ],
    },
  ],
  alerts: [
    ALERT_RED,
    ALERT_YELLOW,
    {
      alert_id: 'al-9',
      patient_id: 'pat-1',
      rule_id: 'R-MIS-01',
      rule_version: 'rules-v1',
      level: 'grey',
      symptom_key: null,
      attribute: null,
      headline: 'Keine Eingabe seit 2 Tagen',
      status: 'acknowledged',
      created_at: '2026-10-14T09:00:00+02:00',
      explanation: {
        kind: 'missing',
        params: { max_days_without_response: 1 },
        observed: { days_without_response: 2 },
        evidence: [],
      },
      acknowledgement: {
        by: 'doctor',
        at: '2026-10-15T10:00:00+02:00',
        decision: 'contact_patient',
        note: 'Patientin angerufen',
      },
    },
  ],
  missing_days: ['2026-10-14'],
  visits: [
    { fact_id: 'visit-1', at: '2026-10-10T10:00:00+02:00', kind: 'past' },
    { fact_id: 'visit-2', at: '2026-10-20T10:00:00+02:00', kind: 'planned' },
  ],
  assessments: [
    {
      assessment_id: 'as-1',
      fact_id: 'assess-1',
      patient_id: 'pat-1',
      assessed_at: '2026-10-15T11:00:00+02:00',
      assessed_by: 'doctor',
      ctcae_version: 'v6.0',
      items: [
        {
          ctcae_term_id: 'nausea',
          term_en: 'Nausea',
          meddra_code: '10028813',
          grade: 1,
          attribution: 'possible',
        },
      ],
    },
  ],
};

/** `GET /config` (Ausschnitt): Schwellenregeln für die gestrichelte Linie. */
export const CONFIG = {
  items: {
    version: 'items-v1',
    items: [
      { symptom_key: 'nausea', core: true, label: { cs: 'Nevolnost', en: 'Nausea' } },
      { symptom_key: 'fever', core: true, label: { cs: 'Horečka', en: 'Fever' } },
      { symptom_key: 'fatigue', core: true, label: { cs: 'Únava', en: 'Tiredness' } },
      {
        symptom_key: 'peripheral_neuropathy',
        core: false,
        label: { cs: 'Brnění', en: 'Tingling or numbness' },
      },
    ],
  },
  regimens: {
    version: 'regimens-v1',
    regimens: [
      {
        id: 'FOLFOX',
        label: { cs: 'FOLFOX', en: 'FOLFOX (oxaliplatin, fluorouracil)' },
        cycle_length_days: 14,
        drugs: [
          { name: 'oxaliplatin', atc: 'L01XA03' },
          { name: 'fluorouracil', atc: 'L01BC02' },
        ],
        symptom_keys: ['peripheral_neuropathy', 'nausea', 'fever'],
      },
      {
        id: 'PEMBRO',
        label: { cs: 'Pembrolizumab', en: 'Pembrolizumab' },
        cycle_length_days: 21,
        drugs: [{ name: 'pembrolizumab', atc: 'L01FF02' }],
        symptom_keys: ['fatigue'],
      },
    ],
  },
  ctcae: {},
  report: {
    version: 'report-v1',
    since: 'last_visit',
    sections: [
      'summary',
      'alerts',
      'timeline',
      'since_last_visit',
      'therapy',
      'assessments',
      'missing_data',
      'audit',
    ],
  },
  rules: {
    version: 'rules-v1',
    noise: { notify_levels: ['red'], cooldown_hours: 24, digest_levels: ['yellow', 'grey'] },
    rules: [
      {
        id: 'R-SEV-01',
        kind: 'threshold',
        level: 'red',
        enabled: true,
        attributes: ['severity', 'interference'],
        params: { min_value: 3 },
        rationale: {
          cs: 'Demonstrační práh, klinicky neověřeno.',
          en: 'Demo threshold, not clinically validated.',
        },
        source_id: 'SRC-DEMO',
      },
      {
        id: 'R-URG-01',
        kind: 'threshold',
        level: 'red',
        enabled: true,
        symptom_keys: ['fever'],
        attributes: ['presence'],
        params: { min_value: 1 },
      },
      {
        id: 'R-OFF-01',
        kind: 'threshold',
        level: 'yellow',
        enabled: false,
        symptom_keys: ['fatigue'],
        params: { min_value: 2 },
      },
      {
        id: 'R-DLT-01',
        kind: 'baseline_delta',
        level: 'yellow',
        enabled: true,
        params: { min_delta: 2 },
      },
    ],
  },
};

/** Quittierte rote Meldung, wie sie `POST …/acknowledge` zurückgibt. */
export const ACKED_RED: Alert = {
  ...ALERT_RED,
  status: 'acknowledged',
  acknowledgement: {
    by: 'doctor',
    at: '2026-10-17T09:00:00+02:00',
    decision: 'contact_patient',
    note: 'Patientin angerufen',
  },
};

/** Vorlage der CTCAE-Aufnahme: nur definierte Grade (Fatigue: Grad 4 leer ⇒ nicht anbieten). */
export const TEMPLATE: AssessmentTemplate = {
  patient_id: 'pat-1',
  ctcae_version: 'v6.0',
  source: {
    id: 'SRC-CTCAE-V6',
    title: 'Common Terminology Criteria for Adverse Events (CTCAE) v6.0, NCI/NIH/DHHS',
    url: 'https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events/ctcae-v6.pdf',
  },
  terms: [
    {
      ctcae_term_id: 'CTCAE-NAUSEA',
      term_en: 'Nausea',
      label: 'Übelkeit',
      meddra_code: '10028813',
      grades: {
        '1': 'Loss of appetite without alteration in eating habits',
        '2': 'Oral intake decreased without significant weight loss, dehydration or malnutrition',
        '3': 'Inadequate oral caloric or fluid intake; tube feeding, TPN, or hospitalization indicated',
      },
      symptom_keys: ['nausea'],
      pro_hint: { 'nausea.severity.max': 3, 'nausea.severity.last': 3 },
      last_grade: 1,
    },
    {
      ctcae_term_id: 'CTCAE-FEVER',
      term_en: 'Fever',
      label: 'Fieber',
      meddra_code: '10016558',
      grades: {
        '1': '38.0 - 39.0 degrees C (100.4 - 102.2 degrees F)',
        '2': '>39.0 - 40.0 degrees C (102.3 - 104.0 degrees F)',
        '3': '>40.0 degrees C (>104.0 degrees F) for <= 24 hrs',
        '4': '>40.0 degrees C (>104.0 degrees F) for > 24 hrs',
      },
      symptom_keys: ['fever'],
      pro_hint: { 'fever.presence.max': 1, 'fever.presence.last': 1 },
      last_grade: null,
    },
    {
      ctcae_term_id: 'CTCAE-FATIGUE',
      term_en: 'Fatigue',
      label: 'Fatigue',
      meddra_code: '10016256',
      grades: { '1': 'Fatigue relieved by rest', '2': 'Fatigue not relieved by rest', '4': '' },
      symptom_keys: ['fatigue'],
      pro_hint: {},
      last_grade: null,
    },
  ],
};

export const ASSESSMENT_SAVED: Assessment = {
  assessment_id: 'as-9',
  fact_id: 'assess-9',
  patient_id: 'pat-1',
  assessed_at: '2026-10-17T09:00:00+02:00',
  assessed_by: 'doctor',
  ctcae_version: 'v6.0',
  items: [{ ctcae_term_id: 'CTCAE-NAUSEA', grade: 2 }],
};

/** Versionshistorie (Vertrag v1.5): neueste zuerst. */
export const HISTORY_RULES = [
  {
    version: 'rules-v2',
    changed_at: '2026-10-16T18:00:00+02:00',
    changed_by: 'Admin (Demo)',
    change_note: 'Schwelle angepasst',
    active: true,
  },
  {
    version: 'rules-v1',
    changed_at: '2026-10-10T08:00:00+02:00',
    changed_by: 'Seed',
    change_note: null,
    active: false,
  },
];

export const HISTORY_REPORT = [
  {
    version: 'report-v1',
    changed_at: '2026-10-10T08:00:00+02:00',
    changed_by: 'Seed',
    change_note: null,
    active: true,
  },
];

export const AUDIT_ROWS = [
  {
    at: '2026-10-17T08:00:00+02:00',
    actor_role: 'clinician',
    action: 'view_overview',
    target_type: 'patient',
    target_id: 'pat-1',
  },
  {
    at: '2026-10-17T08:30:00+02:00',
    actor_role: 'clinician',
    action: 'acknowledge_alert',
    target_type: 'alert',
    target_id: 'al-1',
  },
];

export const FHIR_BUNDLE = {
  resourceType: 'Bundle',
  type: 'collection',
  entry: [{ fullUrl: 'urn:uuid:00000000-0000-4000-8000-000000000001' }],
};

export const CONFIG_STATE = {
  version: 'rules-v2',
  changed_at: '2026-10-17T09:00:00+02:00',
  changed_by: 'Admin (Demo)',
};
