import type { Notification, Questionnaire, SubmitReceipt, WorklistRow } from '../api/client';

/** Feste Ankerzeit der Tests (Vertrag §8). */
export const ANCHOR = '2026-10-17T09:00:00+02:00';

/** Arbeitsliste in bewusst „unsortierter“ Reihenfolge: die Ansicht muss die Serverreihenfolge übernehmen. */
export const WORKLIST: WorklistRow[] = [
  {
    patient_id: 'pat-4',
    pseudonym: 'SYN-0004',
    display_name: 'Anna Grün',
    regimen_id: 'regimen-a',
    regimen_label: 'Regime A',
    cycle_day: 3,
    traffic_light: 'green',
    open_alerts: 0,
    top_alert: null,
    last_response_at: '2026-10-17T08:30:00+02:00',
    next_visit_at: '2026-10-21T10:00:00+02:00',
    synthetic: true,
  },
  {
    patient_id: 'pat-1',
    pseudonym: 'SYN-0001',
    display_name: 'Rita Rot',
    regimen_id: 'regimen-a',
    regimen_label: 'Regime A',
    cycle_day: 8,
    traffic_light: 'red',
    open_alerts: 2,
    top_alert: {
      alert_id: 'al-1',
      rule_id: 'R-URG-01',
      level: 'red',
      headline: 'Fieber gemeldet',
      created_at: '2026-10-17T06:00:00+02:00',
    },
    last_response_at: '2026-10-17T06:00:00+02:00',
    next_visit_at: '2026-10-20T10:00:00+02:00',
    synthetic: true,
  },
  {
    patient_id: 'pat-3',
    pseudonym: 'SYN-0003',
    display_name: 'Gerda Grau',
    regimen_id: 'regimen-b',
    traffic_light: 'grey',
    open_alerts: 1,
    top_alert: {
      alert_id: 'al-3',
      rule_id: 'R-MIS-01',
      level: 'grey',
      headline: 'Keine Eingabe seit 6 Tagen',
    },
    last_response_at: null,
    next_visit_at: null,
    synthetic: true,
  },
  {
    patient_id: 'pat-2',
    pseudonym: 'SYN-0002',
    display_name: 'Gustav Gelb',
    regimen_id: 'regimen-b',
    regimen_label: 'Regime B',
    cycle_day: 12,
    traffic_light: 'yellow',
    open_alerts: 1,
    top_alert: {
      alert_id: 'al-2',
      rule_id: 'R-TRD-01',
      level: 'yellow',
      headline: 'Übelkeit nimmt zu',
    },
    last_response_at: '2026-10-16T08:00:00+02:00',
    next_visit_at: null,
    synthetic: true,
  },
];

export const WORKLIST_NAMES = WORKLIST.map((row) => row.display_name);

export const NOTIFICATIONS: Notification[] = [
  {
    notification_id: 'n-old',
    at: '2026-10-17T07:00:00+02:00',
    patient_id: 'pat-9',
    alert_id: 'al-9',
    level: 'red',
    channel: 'in_app',
    text: 'Rote Meldung zu SYN-0009',
  },
  {
    notification_id: 'n-new',
    at: '2026-10-17T08:45:00+02:00',
    patient_id: 'pat-1',
    alert_id: 'al-1',
    level: 'red',
    channel: 'in_app',
    text: 'Rote Meldung zu SYN-0001',
  },
  {
    notification_id: 'n-yellow',
    at: '2026-10-17T08:50:00+02:00',
    patient_id: 'pat-2',
    alert_id: 'al-2',
    level: 'yellow',
    channel: 'in_app',
    text: 'Gelbe Meldung zu SYN-0002',
  },
];

/** Testdaten (synthetisch) für die Frontend-Tests; nicht Teil der Laufzeit. */

const FREQUENCY_OPTIONS = [
  { value: 0, label: 'Nie' },
  { value: 1, label: 'Selten' },
  { value: 2, label: 'Gelegentlich' },
  { value: 3, label: 'Häufig' },
  { value: 4, label: 'Fast ständig' },
];

const SEVERITY_OPTIONS = [
  { value: 0, label: 'Keine' },
  { value: 1, label: 'Leicht' },
  { value: 2, label: 'Mäßig' },
  { value: 3, label: 'Stark' },
  { value: 4, label: 'Sehr stark' },
];

export const QUESTIONNAIRE: Questionnaire = {
  questionnaire_id: 'items-v1:regimen-a',
  items_version: 'items-v1',
  regimen_id: 'regimen-a',
  lang: 'de',
  recall_period: 'In den letzten 7 Tagen',
  selection_reason: 'Fragen passend zu Ihrer Therapie (Beispiel).',
  items: [
    {
      symptom_key: 'nausea',
      label: 'Übelkeit',
      source: 'core',
      questions: [
        {
          attribute: 'frequency',
          text: 'Wie oft hatten Sie Übelkeit?',
          options: FREQUENCY_OPTIONS,
        },
        { attribute: 'severity', text: 'Wie stark war die Übelkeit?', options: SEVERITY_OPTIONS },
      ],
    },
    {
      symptom_key: 'fever',
      label: 'Fieber',
      source: 'regimen',
      questions: [
        {
          attribute: 'presence',
          text: 'Hatten Sie Fieber?',
          options: [
            { value: 0, label: 'Nein' },
            { value: 1, label: 'Ja' },
          ],
        },
      ],
    },
  ],
};

export const RECEIPT: SubmitReceipt = {
  response_id: 'resp-1',
  recorded_at: '2026-10-17T09:00:00+02:00',
  answered: 1,
  skipped: 2,
  message_key: 'patient.response.saved',
};

export const PATIENT = {
  id: 'u3',
  username: 'patient',
  display_name: 'Patient:in (Demo)',
  role: 'patient',
};
export const CLINICIAN = {
  id: 'u4',
  username: 'doctor',
  display_name: 'doctor',
  role: 'clinician',
};

export const ADMIN = {
  id: 'u1',
  username: 'admin',
  display_name: 'Admin (Demo)',
  role: 'admin',
};
