import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { metaSchema } from '../../../../platform/frontend/src/features/system/model';
import {
  alertSchema,
  assessmentSchema,
  assessmentTemplateSchema,
  configRulesSchema,
  configStateSchema,
  followupCardSchema,
  freeTextFeatureSchema,
  freeTextReceiptSchema,
  freeTextSchema,
  historyRowSchema,
  factSchema,
  notificationSchema,
  overviewSchema,
  summarySchema,
  questionnaireSchema,
  submitReceiptSchema,
  timelineSchema,
  worklistRowSchema,
} from './client';
import { metaExtensionSchema } from '../hooks/useServerNow';

/**
 * Vertragsprobe (F-INT): jede Fixture ist eine ECHTE Backend-Antwort (erzeugt von
 * `challenge/backend/test_frontend_shapes.py` mit dem echten Inhalt und eingefrorener Uhr). Sie muss
 * durch das zod-Schema des Frontends laufen; so fällt jede Formabweichung hier auf, nicht erst im Browser.
 */

interface Fixture {
  request: string;
  status: number;
  body: unknown;
}

const FILES = import.meta.glob<Fixture>('./__fixtures__/*.json', {
  eager: true,
  import: 'default',
});
const FIXTURES = new Map(
  Object.entries(FILES).map(([path, fixture]) => [path.replace(/^.*\/(.*)\.json$/, '$1'), fixture]),
);

function fixture(name: string): Fixture {
  const found = FIXTURES.get(name);
  if (!found)
    throw new Error(`Fixture ${name} fehlt – test_frontend_shapes.py neu schreiben lassen`);
  return found;
}

const errorBody = z.object({
  code: z.string(),
  message: z.string(),
  field_errors: z.array(z.object({ field: z.string(), code: z.string(), message: z.string() })),
});

/** [Fixture, Schema, erwarteter Status] */
const SUCCESS: [string, z.ZodType, number][] = [
  ['worklist', z.array(worklistRowSchema), 200],
  ['free_text_created', freeTextReceiptSchema, 201],
  ['free_text_replay', freeTextReceiptSchema, 200],
  ['free_texts_list_unconfirmed', z.array(freeTextSchema), 200],
  ['free_text_followups', z.array(followupCardSchema), 200],
  ['free_text_answered', submitReceiptSchema, 201],
  ['free_texts_list', z.array(freeTextSchema), 200],
  ['worklist_free_text', z.array(worklistRowSchema), 200],
  ['fact_free_text', factSchema, 200],
  ['overview_red', overviewSchema, 200],
  ['overview_quiet', overviewSchema, 200],
  ['overview_after_acknowledge', overviewSchema, 200],
  ['timeline_all', timelineSchema, 200],
  ['timeline_from_last_visit', timelineSchema, 200],
  ['timeline_after_assessment', timelineSchema, 200],
  ['alerts_list', z.array(alertSchema), 200],
  ['alert_detail', alertSchema, 200],
  ['alert_after_acknowledge', alertSchema, 200],
  ['acknowledge_ok', alertSchema, 200],
  ['notifications', z.array(notificationSchema), 200],
  ['config', configRulesSchema, 200],
  ['config_admin', configRulesSchema, 200],
  ['config_updated', configRulesSchema, 200],
  ['config_history_rules', z.array(historyRowSchema), 200],
  ['config_history_report', z.array(historyRowSchema), 200],
  ['rules_updated', configStateSchema, 200],
  ['report_updated', configStateSchema, 200],
  ['overview_with_summary', overviewSchema, 200],
  ['summary_none', summarySchema, 200],
  ['summary_created', summarySchema, 200],
  ['summary_latest', summarySchema, 200],
  ['fact_resp', factSchema, 200],
  ['fact_obs', factSchema, 200],
  ['fact_alert', factSchema, 200],
  ['fact_visit', factSchema, 200],
  ['fact_ther', factSchema, 200],
  ['fact_assess', factSchema, 200],
  ['assessment_template', assessmentTemplateSchema, 200],
  ['assessment_created', assessmentSchema, 201],
  ['assessment_replay', assessmentSchema, 200],
  ['assessments_list', z.array(assessmentSchema), 200],
  ['questionnaire', questionnaireSchema, 200],
  ['response_created', submitReceiptSchema, 201],
  ['response_replay', submitReceiptSchema, 200],
];

const ERRORS: [string, number, string][] = [
  ['acknowledge_conflict', 409, 'alert_not_open'],
  ['acknowledge_not_found', 404, 'not_found'],
  ['acknowledge_invalid', 422, 'validation_failed'],
  ['assessment_invalid', 422, 'validation_failed'],
  ['fact_not_found', 404, 'not_found'],
  ['response_conflict', 409, 'idempotency_conflict'],
  ['free_text_conflict', 409, 'free_text_exists'],
  ['free_text_invalid', 422, 'validation_failed'],
  ['response_invalid', 422, 'validation_failed'],
  ['rules_forbidden', 403, 'forbidden'],
  ['rules_no_red_rule', 422, 'no_red_rule'],
  ['rules_no_red_notification', 422, 'no_red_notification'],
  ['rules_invalid', 422, 'validation_failed'],
  ['rules_conflict', 409, 'version_conflict'],
  ['report_invalid', 422, 'validation_failed'],
];

describe('Backend-Fixtures gegen die Frontend-Schemas', () => {
  it('hat Fixtures zu allen genutzten Endpunkten', () => {
    expect(FIXTURES.size).toBeGreaterThanOrEqual(30);
  });

  it.each(SUCCESS.map(([name, schema, status]) => ({ name, schema, status })))(
    '$name lässt sich parsen (Status $status)',
    ({ name, schema, status }) => {
      const { body, status: actual } = fixture(name);
      expect(actual).toBe(status);
      const result = schema.safeParse(body);
      expect(
        result.success,
        result.success ? '' : JSON.stringify(result.error.issues, null, 2),
      ).toBe(true);
    },
  );

  it('/meta: Plattformschema und Erweiterung waechter.server_now', () => {
    const { body } = fixture('meta');
    expect(metaSchema.safeParse(body).success).toBe(true);
    const parsed = metaExtensionSchema.safeParse(body);
    expect(parsed.success).toBe(true);
    if (parsed.success)
      expect(Number.isNaN(Date.parse(parsed.data.waechter.server_now))).toBe(false);
  });

  it('/meta: waechter.free_text (Schalter und Höchstlänge, T-22)', () => {
    const { body } = fixture('meta');
    const feature = (body as { waechter?: { free_text?: unknown } }).waechter?.free_text;
    const parsed = freeTextFeatureSchema.safeParse(feature);
    expect(parsed.success).toBe(true);
    if (parsed.success) expect(parsed.data).toEqual({ enabled: true, max_length: 500 });
  });

  it('Freitext: Vorschläge liegen wörtlich im Text, Folgefragen führen zur Bestätigung (T-22)', () => {
    const open = z.array(freeTextSchema).parse(fixture('free_texts_list_unconfirmed').body);
    expect(open.length).toBeGreaterThan(0);
    for (const item of open) {
      for (const s of item.suggestions) expect(item.text.slice(s.start, s.end)).toBe(s.quote);
      expect(item.suggestions.every((s) => !s.confirmed)).toBe(true);
      expect(item.unconfirmed).toBeGreaterThan(0);
    }
    const receipt = freeTextReceiptSchema.parse(fixture('free_text_created').body);
    expect(receipt.followups.length).toBeGreaterThan(0);
    const cards = z.array(followupCardSchema).parse(fixture('free_text_followups').body);
    expect(cards.map((c) => c.symptom_key)).toEqual(receipt.followups.map((c) => c.symptom_key));
    for (const card of cards) expect(card.questions.length).toBeGreaterThan(0);
    // nach der Antwort ist genau das beantwortete Symptom bestätigt, mit der Antwort der Patientin
    const done = z.array(freeTextSchema).parse(fixture('free_texts_list').body);
    const confirmed = done.flatMap((item) => item.suggestions).filter((s) => s.confirmed);
    expect(confirmed.length).toBeGreaterThan(0);
    expect(confirmed.every((s) => s.answers.length > 0)).toBe(true);
  });

  it('Arbeitsliste: Zahl unbestätigter Freitext-Zuordnungen (T-22)', () => {
    const rows = z.array(worklistRowSchema).parse(fixture('worklist_free_text').body);
    expect(rows.some((row) => (row.free_text_unconfirmed ?? 0) > 0)).toBe(true);
  });

  it.each(ERRORS)(
    'Fehler %s hat Status %i und Code %s im Plattformformat',
    (name, status, code) => {
      const { body, status: actual } = fixture(name);
      expect(actual).toBe(status);
      const parsed = errorBody.parse(body);
      if (name !== 'acknowledge_invalid' && name !== 'response_invalid')
        expect(parsed.code).toBe(code);
    },
  );
});
