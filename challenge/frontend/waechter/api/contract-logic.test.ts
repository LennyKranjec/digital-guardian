import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { ackErrorKey } from '../hooks/useAcknowledge';
import { submitErrorKey } from '../hooks/useCheckin';
import { availableGrades, mapFieldErrors, parseHintKey } from '../model/assessment';
import { settingsErrorKey } from '../hooks/useSettings';
import { buildRulesUpdate, initialDrafts, initialNoise, mapRuleErrors } from '../model/settings';
import {
  alertFactId,
  buildEvents,
  domainOf,
  orderSeries,
  thresholdsFor,
  timedPoints,
  valueRuns,
} from '../model/timeline';
import {
  alertSchema,
  assessmentTemplateSchema,
  auditRowSchema,
  configRulesSchema,
  historyRowSchema,
  overviewSchema,
  summarySchema,
  timelineSchema,
  worklistRowSchema,
  type FieldErrorLike,
} from './client';
import { metaExtensionSchema } from '../hooks/useServerNow';

/**
 * Zweite Ebene der Vertragsprobe: die Logik des Frontends arbeitet mit ECHTEN Backend-Antworten
 * (Fixtures aus `test_frontend_shapes.py`) richtig – nicht nur das Parsen gelingt.
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
const byName = new Map(
  Object.entries(FILES).map(([path, fixture]) => [path.replace(/^.*\/(.*)\.json$/, '$1'), fixture]),
);

function load(name: string): Fixture {
  const found = byName.get(name);
  if (!found) throw new Error(`Fixture ${name} fehlt`);
  return found;
}

const apiError = (name: string): ApiClientError => {
  const { status, body } = load(name);
  const parsed = body as { code: string; message: string; field_errors: FieldErrorLike[] };
  return new ApiClientError(status, parsed.code, parsed.message, parsed.field_errors);
};

describe('Verlauf auf echten Daten', () => {
  const timeline = timelineSchema.parse(load('timeline_all').body);

  it('liefert einen gültigen Zeitraum und Serien mit Punkten', () => {
    expect(domainOf(timeline)).not.toBeNull();
    expect(timeline.series.length).toBeGreaterThan(3);
    for (const series of timeline.series) {
      expect(series.points.length).toBeGreaterThan(0);
      expect(timedPoints(series.points)).toHaveLength(series.points.length);
      for (const point of series.points) expect(point.fact_id).toMatch(/^obs-/);
    }
  });

  it('trennt Linienstücke an jeder echten Lücke (null)', () => {
    const withGap = timeline.series.filter((series) => series.points.some((p) => p.value === null));
    expect(withGap.length).toBeGreaterThan(0);
    for (const series of withGap) {
      const points = timedPoints(series.points);
      const values = points.filter((p) => p.value !== null).length;
      const runs = valueRuns(points);
      expect(runs.flat()).toHaveLength(values);
      expect(runs.length).toBeGreaterThan(1);
    }
  });

  it('stellt Symptome mit offener Meldung zuerst', () => {
    const open = timeline.alerts.filter((alert) => alert.status === 'open');
    expect(open.length).toBeGreaterThan(0);
    const ordered = orderSeries(timeline.series, timeline.alerts);
    expect(ordered).toHaveLength(timeline.series.length);
    const firstKey = ordered[0]?.symptom_key;
    expect(open.some((alert) => alert.symptom_key === firstKey)).toBe(true);
  });

  it('baut aus der echten Antwort eine aufsteigende Ereignisliste mit Meldungen und Terminen', () => {
    const events = buildEvents(timeline);
    const times = events.map((event) => event.ms);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    const kinds = new Set(events.map((event) => event.kind));
    expect(kinds.has('response')).toBe(true);
    expect(kinds.has('alert')).toBe(true);
    expect(kinds.has('visit')).toBe(true);
  });

  it('enthält nach der Aufnahme die Aufnahme im Verlauf', () => {
    const after = timelineSchema.parse(load('timeline_after_assessment').body);
    expect(after.assessments.length).toBeGreaterThan(0);
    expect(buildEvents(after).some((event) => event.kind === 'assessment')).toBe(true);
  });

  it('findet Schwellenlinien in der echten Regelkonfiguration für Schwere-Kurven', () => {
    const rules = configRulesSchema.parse(load('config').body).rules.rules;
    const severity = timeline.series.filter((series) => series.attribute === 'severity');
    expect(severity.length).toBeGreaterThan(0);
    for (const series of severity) {
      expect(thresholdsFor(series, rules).length, series.symptom_key).toBeGreaterThan(0);
    }
  });
});

describe('Meldungen und Belege auf echten Daten', () => {
  it('bildet die Faktkennung einer Meldung so, wie das Backend sie ausliefert', () => {
    const fact = load('fact_alert');
    const factId = (fact.body as { fact_id: string }).fact_id;
    const alert = alertSchema.parse(load('alert_detail').body);
    expect(alertFactId(alert)).toBe(factId);
  });

  it('nennt als Belege einer Erklärung nur Antworten oder Einzelwerte', () => {
    const overview = overviewSchema.parse(load('overview_red').body);
    expect(overview.open_alerts.length).toBeGreaterThan(0);
    for (const alert of overview.open_alerts) {
      for (const evidence of alert.explanation.evidence) expect(evidence).toMatch(/^(resp|obs)-/);
    }
  });

  it('führt quittierte, weiter bestehende Meldungen getrennt in persisting_alerts', () => {
    const after = overviewSchema.parse(load('overview_after_acknowledge').body);
    const before = overviewSchema.parse(load('overview_red').body);
    expect(after.open_alerts.length).toBeLessThan(before.open_alerts.length);
    for (const alert of after.persisting_alerts ?? []) expect(alert.status).toBe('acknowledged');
  });

  it('zeigt eine quittierte Meldung mit wer/wann/Entscheidung', () => {
    const acked = alertSchema.parse(load('acknowledge_ok').body);
    expect(acked.status).toBe('acknowledged');
    expect(acked.acknowledgement?.decision).toBe('contact_patient');
    expect(acked.acknowledgement?.by).toBeTruthy();
    expect(acked.acknowledgement?.at).toBeTruthy();
  });

  it('liefert die Serverzeit am eingefrorenen Anker', () => {
    const parsed = metaExtensionSchema.parse(load('meta').body);
    expect(Date.parse(parsed.waechter.server_now)).toBe(Date.parse('2026-10-17T09:00:00+02:00'));
  });

  it('hat in der Arbeitsliste Nullwerte nur dort, wo das Frontend sie kennt', () => {
    const rows = (load('worklist').body as unknown[]).map((row) => worklistRowSchema.parse(row));
    expect(rows.length).toBeGreaterThan(1);
    expect(rows.some((row) => row.traffic_light === 'red')).toBe(true);
  });
});

describe('Aufnahme auf echten Daten', () => {
  const template = assessmentTemplateSchema.parse(load('assessment_template').body);

  it('bietet je Begriff nur Grad 0 und definierte Grade mit Text an', () => {
    expect(template.terms.length).toBeGreaterThan(0);
    for (const term of template.terms) {
      const options = availableGrades(term);
      expect(options[0]).toEqual({ grade: 0, text: null });
      for (const option of options.slice(1)) {
        expect(option.grade).toBeGreaterThanOrEqual(1);
        expect(option.grade).toBeLessThanOrEqual(5);
        expect(option.text).toBeTruthy();
        expect(term.grades[String(option.grade)]).toBeTruthy();
      }
      // kein undefinierter Grad wird angeboten
      const offered = new Set(options.map((option) => option.grade));
      for (let grade = 1; grade <= 5; grade += 1) {
        if (!term.grades[String(grade)])
          expect(offered.has(grade), `${term.term_en} ${grade}`).toBe(false);
      }
    }
  });

  it('kann jeden PRO-Hinweisschlüssel der echten Vorlage einem Merkmal zuordnen', () => {
    const keys = template.terms.flatMap((term) => Object.keys(term.pro_hint ?? {}));
    expect(keys.length).toBeGreaterThan(0);
    for (const key of keys) {
      const parsed = parseHintKey(key);
      expect(parsed.attribute, key).not.toBeNull();
      expect(parsed.stat, key).not.toBeNull();
    }
  });

  it('liefert die Quelle der Vorlage mit Titel und Link', () => {
    expect(template.source).toBeTruthy();
    if (typeof template.source === 'object' && template.source !== null) {
      expect(template.source.url).toMatch(/^https:\/\//);
      expect(template.source.title).toBeTruthy();
    }
  });

  it('ordnet die echten 422-Feldfehler (items.<i>.<feld>) den gesendeten Begriffen zu', () => {
    const { fieldErrors } = apiError('assessment_invalid');
    const sent = [
      { ctcae_term_id: 'T0', grade: 1 },
      { ctcae_term_id: 'T1', grade: 4 },
      { ctcae_term_id: 'T2', grade: 0 },
    ];
    const mapped = mapFieldErrors(fieldErrors, sent);
    expect(mapped.byTerm.get('T0')).toEqual(['Term not in subspace']);
    expect(mapped.byTerm.get('T1')).toEqual(['Grade not defined']);
    expect(mapped.byTerm.get('T2')).toEqual(['Duplicate term']);
    expect(mapped.general).toEqual([]);
  });

  it('ordnet den Fehler einer fremden Meldung nicht einem Begriff zu', () => {
    const { fieldErrors } = apiError('assessment_foreign_alert');
    const mapped = mapFieldErrors(fieldErrors, [{ ctcae_term_id: 'T0', grade: 0 }]);
    expect(fieldErrors.length).toBeGreaterThan(0);
    expect(fieldErrors.every((error) => error.code === 'foreign_alert')).toBe(true);
    expect(mapped.byTerm.size).toBe(0);
    expect(mapped.general.length).toBe(fieldErrors.length);
  });
});

describe('Einstellungen auf echten Daten', () => {
  const rawConfig = load('config_admin').body as {
    rules: Record<string, unknown>;
    report: Record<string, unknown>;
  };
  const file = configRulesSchema.parse(rawConfig).rules;

  it('schickt unveränderte Entwürfe als genau dieselbe Regeldatei zurück (ohne Version, nichts verloren)', () => {
    const update = buildRulesUpdate(
      file,
      initialDrafts(file.rules),
      initialNoise(file.noise),
      'de',
      'Notiz',
    );
    const { version, ...withoutVersion } = rawConfig.rules;
    expect(version).toBe(file.version);
    expect(update.rules).toEqual(withoutVersion);
    expect(update.expected_version).toBe(file.version);
  });

  it('nennt jede Regel mit Art, Stufe und Parametern, die das Frontend übersetzt', () => {
    expect(file.rules.length).toBeGreaterThan(3);
    for (const rule of file.rules) {
      expect(['threshold', 'baseline_delta', 'trend', 'missing']).toContain(rule.kind);
      expect(Object.keys(rule.params).length, rule.id).toBeGreaterThan(0);
      expect(rule.rationale, rule.id).toBeTruthy();
    }
    const known = new Set([
      'min_value',
      'baseline_days',
      'min_delta',
      'window_days',
      'min_points',
      'horizon_days',
      'min_slope_per_day',
      'target_value',
      'max_days_without_response',
    ]);
    for (const rule of file.rules) {
      for (const key of Object.keys(rule.params))
        expect(known.has(key), `${rule.id}.${key}`).toBe(true);
    }
  });

  it('ordnet den echten 422-Feldpfad rules.rules[<i>].params.<name> der Regelzeile zu', () => {
    const { fieldErrors } = apiError('rules_invalid');
    const mapped = mapRuleErrors(fieldErrors, file.rules);
    expect(fieldErrors[0]?.field).toMatch(/^rules\.rules\[0\]\.params\./);
    expect(mapped.byRule.get(file.rules[0]?.id ?? '')).toEqual(['out of range']);
    expect(mapped.general).toEqual([]);
  });

  it('erkennt die Konfigurationsfehler des Servers: 409, 403, no_red_rule, no_red_notification, 422', () => {
    expect(settingsErrorKey(apiError('rules_conflict'))).toBe('conflict');
    expect(settingsErrorKey(apiError('rules_forbidden'))).toBe('forbidden');
    expect(settingsErrorKey(apiError('rules_no_red_rule'))).toBe('noRedRule');
    expect(settingsErrorKey(apiError('rules_no_red_notification'))).toBe('noRedNotification');
    expect(settingsErrorKey(apiError('rules_invalid'))).toBe('invalid');
    expect(settingsErrorKey(apiError('report_invalid'))).toBe('invalid');
  });

  it('zeigt die neue Version nach der Änderung (aktive Version, Historie neueste zuerst)', () => {
    const updated = configRulesSchema.parse(load('config_updated').body);
    expect(updated.rules.version).not.toBe(file.version);
    expect(updated.report.version).not.toBe(configRulesSchema.parse(rawConfig).report.version);
    const history = z.array(historyRowSchema).parse(load('config_history_rules').body);
    expect(history[0]?.version).toBe(updated.rules.version);
    expect(history[0]?.active).toBe(true);
    expect(history.filter((row) => row.active)).toHaveLength(1);
    expect(history.map((row) => row.version)).toEqual(
      [...history.map((row) => row.version)].sort().reverse(),
    );
  });
});

describe('Fehlerbehandlung auf echten Fehlerantworten', () => {
  it('erkennt Quittieren-Fehler: 409 ⇒ conflict, 404 ⇒ notFound, 422 ⇒ invalid', () => {
    expect(ackErrorKey(apiError('acknowledge_conflict'))).toBe('conflict');
    expect(ackErrorKey(apiError('acknowledge_not_found'))).toBe('notFound');
    expect(ackErrorKey(apiError('acknowledge_invalid'))).toBe('invalid');
  });

  it('erkennt Check-in-Fehler: 409 idempotency_conflict ⇒ conflict, 422 ⇒ invalid', () => {
    expect(submitErrorKey(apiError('response_conflict'))).toBe('conflict');
    expect(submitErrorKey(apiError('response_invalid'))).toBe('invalid');
  });

  it('meldet den fehlenden Beleg als 404', () => {
    expect(load('fact_not_found').status).toBe(404);
  });

  it('liest die Kurzfassung (Übersicht, GET, POST) mit Sätzen, Belegen und Modus', () => {
    for (const name of ['summary_none', 'summary_created', 'summary_latest']) {
      const summary = summarySchema.parse(load(name).body);
      expect(summary.sentences.length, name).toBeGreaterThan(0);
      expect(summary.disclaimer_key, name).toBeTruthy();
      for (const sentence of summary.sentences) {
        for (const ref of sentence.refs)
          expect(ref, name).toMatch(/^(resp|obs|alert|visit|assess|ther)-/);
      }
    }
    const overview = overviewSchema.parse(load('overview_with_summary').body);
    expect(overview.summary?.summary_id).toBe(
      summarySchema.parse(load('summary_latest').body).summary_id,
    );
  });

  it('nimmt Routen, die im Backend noch fehlen (Historie, Audit, Export), erst mit Schema ernst', () => {
    // Fehlt die Route: 404 im Plattformformat. Sobald sie existiert, muss das Schema passen.
    const history = [load('config_history_rules'), load('config_history_report')];
    for (const fixture of history) {
      if (fixture.status === 200)
        expect(z.array(historyRowSchema).safeParse(fixture.body).success).toBe(true);
      else expect(fixture.status).toBe(404);
    }
    const audit = load('audit');
    if (audit.status === 200)
      expect(z.array(auditRowSchema).safeParse(audit.body).success).toBe(true);
    else expect(audit.status).toBe(404);
    const fhir = load('fhir_bundle');
    if (fhir.status === 200) {
      expect((fhir.body as { resourceType?: string }).resourceType).toBe('Bundle');
    } else {
      expect(fhir.status).toBe(404);
    }
  });
});
