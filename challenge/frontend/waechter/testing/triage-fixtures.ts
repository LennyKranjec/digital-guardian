import type { Alert, TriageDecision, TriageRuleCard } from '../api/client';

/** Testdaten (synthetisch) nach openapi v2.0/v2.1 (TriageDecision, TriageRuleCard); nicht Teil der Laufzeit. */

/** Rot mit Schutzboden: Schild-Treffer, Pfadbedingung, Kontrafaktische, Tipps teils unterdrückt. */
export const TRIAGE_RED: TriageDecision = {
  response_id: 'resp-1',
  decided_at: '2026-10-17T08:30:00+02:00',
  level: 'RED',
  level_lo: 'RED',
  level_hi: 'RED',
  incomplete: false,
  profile_id: 'chemo-folfox',
  rule_version: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
  tree_version: 'tree-7f3a',
  leaf_ids: { yellow: 'Y-1a2b', red: 'R-3c4d' },
  reason_codes: [
    {
      code: 'PATH-RED-1',
      text: 'Durchfall Schwere ≥ 3 und Häufigkeit ≥ 3',
      items: ['diarrhea'],
      kind: 'path',
    },
    {
      code: 'SHIELD-FEVER',
      text: 'Fieber ja: Mindeststufe Rot',
      items: ['fever'],
      kind: 'shield',
    },
    { code: 'LEAF-R', text: 'Blatt R-3c4d', kind: 'leaf' },
  ],
  counterfactuals: [
    { direction: 'raise', text: 'wenn ein weiteres Symptom Stufe 3 erreicht' },
    { direction: 'lower', kind: 'change', text: 'Durchfall (Schwere) auf ≤ 2 sinkt' },
    { direction: 'lower', kind: 'shield', text: 'Boden FLOOR-FEVER verhindert Senkung' },
  ],
  recommendations: [
    { rule_id: 'ADV-DIARRHEA-01', symptom_key: 'diarrhea', outcome: 'shown', value: 3 },
    { rule_id: 'ADV-FEVER-01', symptom_key: 'fever', outcome: 'suppressed_acute', value: 1 },
  ],
  asked_questions: 5,
  full_questions: 14,
  status: 'placeholder',
};

/** Gelb über Pfad, unvollständig mit Spanne GRÜN–ROT, ohne Schild. */
export const TRIAGE_YELLOW: TriageDecision = {
  response_id: 'resp-2',
  level: 'YELLOW',
  level_lo: 'GREEN',
  level_hi: 'RED',
  incomplete: true,
  profile_id: 'chemo-capecitabine',
  rule_version: 'ffeeddccbbaa99887766554433221100',
  tree_version: 'tree-90ab',
  reason_codes: [
    { code: 'PATH-YEL-1', text: 'Übelkeit Häufigkeit ≥ 2', items: ['nausea'], kind: 'path' },
    {
      code: 'INCOMPLETE',
      text: 'Sicherheitsfrage nicht beantwortet',
      items: ['fever'],
      kind: 'incomplete',
    },
  ],
  counterfactuals: [{ direction: 'lower', text: 'Übelkeit Häufigkeit auf 1 sinkt' }],
  recommendations: [],
  asked_questions: 4,
  full_questions: 12,
  status: 'placeholder',
};

export const TRIAGE_RULE_CARD: TriageRuleCard = {
  kb_version: '0123456789abcdef0123456789abcdef',
  compiler_version: 'compiler-1',
  profiles: [
    {
      profile_id: 'chemo-folfox',
      regimen_ids: ['regimen-folfox'],
      tree_version: 'tree-7f3a',
      trees: { yellow: { leaves: 9, depth: 4 }, red: { leaves: 5, depth: 3 } },
      verification: {
        points: 12345,
        under: 0,
        over: 0,
        monotone_violations: 0,
        scope: 'exhaustive',
      },
      rules: [
        { level: 'YELLOW', text: 'Übelkeit Häufigkeit ≥ 2', leaf_id: 'Y-1a2b3c4d5e6f7a8b' },
        { level: 'RED', text: 'Durchfall Schwere ≥ 3', leaf_id: 'R-3c4d5e6f7a8b9c0d' },
      ],
      floors: [
        {
          id: 'FLOOR-FEVER',
          text: 'Fieber ja',
          min_level: 'RED',
          locked: true,
          status: 'placeholder',
        },
        { id: 'FLOOR-X', text: 'Beispielboden', min_level: 'YELLOW', locked: false },
      ],
      placeholders: ['Schwellen: Platzhalter, nicht klinisch freigegeben', 'Böden: Platzhalter'],
    },
    {
      profile_id: 'chemo-capecitabine',
      regimen_ids: ['regimen-cape'],
      verification: { points: 800, under: 1, over: 0, monotone_violations: 2, scope: 'sampled' },
      rules: [],
      floors: [],
      placeholders: [],
    },
  ],
};

/** `advice`-Block von `GET /config` (v2.1): Tipp-Regeln mit Bereich, Tipps, Quellen, Status. */
export const ADVICE_FILE = {
  version: 'advice-v1',
  advice: [
    {
      id: 'ADV-NAUSEA-01',
      symptom_key: 'nausea',
      status: 'draft',
      min_value: 2,
      max_value: 3,
      tips: [{ cs: 'Pijte po malých douškách.', en: 'Sip fluids.' }, 'Kleine Mahlzeiten.'],
      source_ids: ['SRC-NCI-NAUSEA'],
    },
    {
      id: 'ADV-NAUSEA-02',
      symptom_key: 'nausea',
      status: 'draft',
      min_value: 4,
      tips: [{ cs: 'Tip', en: 'Tip' }],
      source_ids: ['SRC-NCI-NAUSEA', 'SRC-UNKNOWN'],
    },
  ],
  sources: [
    { id: 'SRC-NCI-NAUSEA', title: 'Nausea and Vomiting, NCI', url: 'https://www.cancer.gov/' },
  ],
};

/** Meldung aus dem kompilierten Baum (v2.8): explanation.kind triage mit Spanne und Schutzboden. */
export const ALERT_TRIAGE: Alert = {
  alert_id: 'al-tri',
  patient_id: 'pat-1',
  rule_id: 'R-TRI-RED',
  rule_version: 'tree-7f3a',
  level: 'red',
  symptom_key: null,
  attribute: null,
  headline: 'Triage: Stufe Rot',
  status: 'open',
  created_at: '2026-10-17T08:30:00+02:00',
  notified: true,
  explanation: {
    kind: 'triage',
    params: {},
    observed: {},
    baseline_window: null,
    cycle_day: 8,
    evidence: [],
    rationale: 'Meldung aus dem kompilierten Baum.',
    triage: {
      level: 'RED',
      level_lo: 'YELLOW',
      level_hi: 'RED',
      incomplete: true,
      response_id: 'resp-9',
      tree_version: 'tree-7f3a',
      reason_codes: [
        { code: 'PATH-1', text: 'Durchfall Schwere ≥ 3', items: ['diarrhea'], kind: 'path' },
        {
          code: 'SHIELD-FEVER',
          text: 'Fieber ja: Mindeststufe Rot',
          items: ['fever'],
          kind: 'shield',
        },
      ],
    },
  },
};
