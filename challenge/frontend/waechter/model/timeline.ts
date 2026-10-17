import type {
  Alert,
  Assessment,
  ConfigRule,
  Series,
  SeriesPoint,
  Timeline,
  TimelineRange,
} from '../api/client';
import { DISPLAY_TIME_ZONE } from './time';

/**
 * Reine Verlaufslogik (keine UI): Zeitraum, Prager Tagesgrenzen, Achsen, Reihenfolge der
 * Symptome, Linienstücke ohne Verbindung über Lücken, Schwellen und die Ereignisliste.
 */

/* ---------- Zeitraum ---------- */

export const RANGE_MODES = ['visit', '14d', '28d', 'all'] as const;
export type RangeMode = (typeof RANGE_MODES)[number];

const DAY_MS = 86_400_000;

/**
 * Abfrage-Zeitraum. „Seit letztem Termin“ braucht den letzten Termin, 14/28 Tage die Serverzeit
 * (nie die Browseruhr, DR-009); ist die Grundlage unbekannt, gibt es `null` (Option nicht verfügbar).
 * „Alles“ sendet keine Grenzen.
 */
export function timelineRange(
  mode: RangeMode,
  context: { serverNow: Date | null; lastVisitAt: string | null | undefined },
): TimelineRange | null {
  if (mode === 'all') return {};
  if (mode === 'visit') {
    const visit = context.lastVisitAt ? new Date(context.lastVisitAt) : null;
    return visit && !Number.isNaN(visit.getTime()) ? { from: visit.toISOString() } : null;
  }
  if (!context.serverNow) return null;
  const days = mode === '14d' ? 14 : 28;
  return { from: new Date(context.serverNow.getTime() - days * DAY_MS).toISOString() };
}

/* ---------- Prager Tage ---------- */

function pragueOffsetMs(ts: number): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: DISPLAY_TIME_ZONE,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(ts));
  const part = (type: string) => Number(parts.find((entry) => entry.type === type)?.value);
  const asUtc = Date.UTC(
    part('year'),
    part('month') - 1,
    part('day'),
    part('hour'),
    part('minute'),
    part('second'),
  );
  return asUtc - Math.floor(ts / 1000) * 1000;
}

/** Beginn (UTC-Millisekunden) des Prager Kalendertags `YYYY-MM-DD`; `null` bei ungültiger Eingabe. */
export function pragueDayStartMs(date: string): number | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return null;
  const guess = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const first = guess - pragueOffsetMs(guess);
  return guess - pragueOffsetMs(first); // zweite Runde fängt die Zeitumstellung ab
}

/** Prager Kalendertag eines Zeitpunkts als `YYYY-MM-DD`. */
export function pragueDateString(ms: number): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: DISPLAY_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(ms));
}

export function addDays(date: string, days: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return date;
  const next = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days));
  return next.toISOString().slice(0, 10);
}

/** Beginn und Ende eines Prager Kalendertags (Ende = Beginn des Folgetags). */
export function pragueDayRange(date: string): [number, number] | null {
  const start = pragueDayStartMs(date);
  const end = pragueDayStartMs(addDays(date, 1));
  return start === null || end === null ? null : [start, end];
}

export interface Tick {
  ms: number;
  date: string;
}

/** Tagesmarken auf Prager Mitternacht; Schrittweite so gewählt, dass höchstens `maxTicks` entstehen. */
export function timeTicks(fromMs: number, toMs: number, maxTicks: number): Tick[] {
  if (!(toMs > fromMs) || maxTicks < 1) return [];
  const days = (toMs - fromMs) / DAY_MS;
  const step = [1, 2, 3, 5, 7, 14, 28, 56, 112].find((s) => Math.ceil(days / s) <= maxTicks) ?? 224;
  let date = pragueDateString(fromMs);
  let ms = pragueDayStartMs(date) ?? fromMs;
  if (ms < fromMs) {
    date = addDays(date, 1);
    ms = pragueDayStartMs(date) ?? fromMs;
  }
  const ticks: Tick[] = [];
  while (ms <= toMs && ticks.length < 400) {
    ticks.push({ ms, date });
    date = addDays(date, step);
    const next = pragueDayStartMs(date);
    if (next === null) break;
    ms = next;
  }
  return ticks;
}

/* ---------- Achsen ---------- */

export interface Domain {
  from: number;
  to: number;
}

export function domainOf(timeline: Pick<Timeline, 'from' | 'to'>): Domain | null {
  const from = Date.parse(timeline.from);
  const to = Date.parse(timeline.to);
  return Number.isNaN(from) || Number.isNaN(to) || to <= from ? null : { from, to };
}

/** Linearer Maßstab Zeit → Pixel; Werte außerhalb werden auf den Rand begrenzt. */
export function scaleX(domain: Domain, left: number, right: number): (ms: number) => number {
  const span = domain.to - domain.from;
  return (ms) =>
    left + ((Math.min(Math.max(ms, domain.from), domain.to) - domain.from) / span) * (right - left);
}

/** Wertebereich der PRO-Skala 0–4, 0 unten. */
export function scaleY(top: number, bottom: number, max = 4): (value: number) => number {
  return (value) => bottom - (Math.min(Math.max(value, 0), max) / max) * (bottom - top);
}

/* ---------- Serien ---------- */

export interface TimedPoint {
  ms: number;
  value: number | null;
  factId: string;
}

export function timedPoints(points: readonly SeriesPoint[]): TimedPoint[] {
  return points
    .map((point) => ({ ms: Date.parse(point.t), value: point.value, factId: point.fact_id }))
    .filter((point) => !Number.isNaN(point.ms))
    .sort((a, b) => a.ms - b.ms);
}

/** Zusammenhängende Wertestücke; ein fehlender Wert (`null`) trennt die Linie – es wird nie über eine Lücke verbunden. */
export function valueRuns(
  points: readonly TimedPoint[],
): { ms: number; value: number; factId: string }[][] {
  const runs: { ms: number; value: number; factId: string }[][] = [];
  let current: { ms: number; value: number; factId: string }[] = [];
  for (const point of points) {
    if (point.value === null) {
      if (current.length > 0) runs.push(current);
      current = [];
    } else {
      current.push({ ms: point.ms, value: point.value, factId: point.factId });
    }
  }
  if (current.length > 0) runs.push(current);
  return runs;
}

const sameSeries = (alert: Alert, series: Pick<Series, 'symptom_key' | 'attribute'>): boolean =>
  alert.symptom_key === series.symptom_key &&
  (alert.attribute === null ||
    alert.attribute === undefined ||
    alert.attribute === series.attribute);

/** Meldungen, die zu dieser Kurve gehören (Symptom und, falls angegeben, Merkmal). */
export function alertsForSeries(alerts: readonly Alert[], series: Series): Alert[] {
  return alerts.filter((alert) => sameSeries(alert, series));
}

/** Symptome mit offener Meldung zuerst; sonst bleibt die Reihenfolge des Servers. */
export function orderSeries(series: readonly Series[], alerts: readonly Alert[]): Series[] {
  const open = alerts.filter((alert) => alert.status === 'open');
  return series
    .map((entry, index) => ({
      entry,
      index,
      hasOpen: open.some((alert) => sameSeries(alert, entry)),
    }))
    .sort((a, b) => Number(b.hasOpen) - Number(a.hasOpen) || a.index - b.index)
    .map(({ entry }) => entry);
}

/** Meldungen ohne passende Kurve (z. B. fehlende Eingabe): sie erscheinen nur in der Ereignisleiste. */
export function unmatchedAlerts(alerts: readonly Alert[], series: readonly Series[]): Alert[] {
  return alerts.filter((alert) => !series.some((entry) => sameSeries(alert, entry)));
}

export interface Threshold {
  ruleId: string;
  value: number;
}

/** Schwellenlinien für eine Kurve aus den aktiven Regeln (Art „threshold“, passendes Symptom/Merkmal). */
export function thresholdsFor(
  series: Pick<Series, 'symptom_key' | 'attribute'>,
  rules: readonly ConfigRule[],
): Threshold[] {
  return rules
    .filter(
      (rule) =>
        rule.kind === 'threshold' &&
        rule.enabled &&
        typeof rule.params.min_value === 'number' &&
        (!rule.symptom_keys ||
          rule.symptom_keys.length === 0 ||
          rule.symptom_keys.includes(series.symptom_key)) &&
        (!rule.attributes ||
          rule.attributes.length === 0 ||
          rule.attributes.includes(series.attribute)),
    )
    .map((rule) => ({ ruleId: rule.id, value: rule.params.min_value ?? 0 }));
}

/** Faktkennung zu einer Meldung (Muster `alert-…` laut Vertrag). */
export function alertFactId(alert: Pick<Alert, 'alert_id'>): string {
  return alert.alert_id.startsWith('alert-') ? alert.alert_id : `alert-${alert.alert_id}`;
}

/* ---------- Ereignisliste ---------- */

export type TimelineEvent =
  | {
      kind: 'response';
      ms: number;
      values: { label: string; attribute: string; value: number | null }[];
    }
  | { kind: 'alert'; ms: number; alert: Alert }
  | { kind: 'acknowledged'; ms: number; alert: Alert }
  | { kind: 'assessment'; ms: number; assessment: Assessment }
  | { kind: 'visit'; ms: number; visitKind: 'past' | 'planned'; factId?: string | null }
  | { kind: 'missing'; ms: number; date: string }
  | { kind: 'therapy'; ms: number; label: string; factId?: string | null };

/** Alle Ereignisse zeitlich aufsteigend (Antworten desselben Zeitpunkts zu einer Zeile gebündelt). */
export function buildEvents(timeline: Timeline): TimelineEvent[] {
  const events: TimelineEvent[] = [];

  const responses = new Map<number, Extract<TimelineEvent, { kind: 'response' }>>();
  for (const series of timeline.series) {
    for (const point of timedPoints(series.points)) {
      let event = responses.get(point.ms);
      if (!event) {
        event = { kind: 'response', ms: point.ms, values: [] };
        responses.set(point.ms, event);
        events.push(event);
      }
      event.values.push({ label: series.label, attribute: series.attribute, value: point.value });
    }
  }

  for (const alert of timeline.alerts) {
    const created = Date.parse(alert.created_at);
    if (!Number.isNaN(created)) events.push({ kind: 'alert', ms: created, alert });
    const acknowledgedAt = alert.acknowledgement?.at ? Date.parse(alert.acknowledgement.at) : NaN;
    if (!Number.isNaN(acknowledgedAt)) {
      events.push({ kind: 'acknowledged', ms: acknowledgedAt, alert });
    }
  }

  for (const assessment of timeline.assessments) {
    const ms = Date.parse(assessment.assessed_at);
    if (!Number.isNaN(ms)) events.push({ kind: 'assessment', ms, assessment });
  }

  for (const visit of timeline.visits) {
    const ms = Date.parse(visit.at);
    if (!Number.isNaN(ms)) {
      events.push({ kind: 'visit', ms, visitKind: visit.kind ?? 'past', factId: visit.fact_id });
    }
  }

  for (const date of timeline.missing_days) {
    const start = pragueDayStartMs(date);
    if (start !== null) events.push({ kind: 'missing', ms: start, date });
  }

  for (const entry of timeline.therapy_events ?? []) {
    const ms = Date.parse(entry.at);
    if (!Number.isNaN(ms))
      events.push({ kind: 'therapy', ms, label: entry.label, factId: entry.fact_id });
  }

  return events
    .map((event, index) => ({ event, index }))
    .sort((a, b) => a.event.ms - b.event.ms || a.index - b.index)
    .map(({ event }) => event);
}

/* ---------- Kompakte Übersicht ---------- */

/** Höchstzahl der Kurven in der kompakten Verlaufsleiste. */
export const COMPACT_MAX = 4;
/** So viele Kurven stehen dort, wenn keine Meldung offen ist. */
export const COMPACT_FALLBACK = 3;

/**
 * Kurven der kompakten Leiste: alle Symptome mit offener Meldung (zuerst, höchstens `COMPACT_MAX`),
 * sonst die ersten `COMPACT_FALLBACK` in Serverreihenfolge. Es werden nur vorhandene Daten gezeigt,
 * nichts wird gewichtet oder bewertet.
 */
export function pickCompactSeries(
  series: readonly Series[],
  alerts: readonly Alert[],
): { series: Series; openAlerts: Alert[] }[] {
  const open = alerts.filter((alert) => alert.status === 'open');
  const ordered = orderSeries(series, alerts).map((entry) => ({
    series: entry,
    openAlerts: open.filter((alert) => sameSeries(alert, entry)),
  }));
  const flagged = ordered.filter((entry) => entry.openAlerts.length > 0);
  return (flagged.length > 0 ? flagged : ordered.slice(0, COMPACT_FALLBACK)).slice(0, COMPACT_MAX);
}

/** Letzter vorhandener Wert einer Kurve (0–4) oder `null`, wenn es keinen gibt. */
export function lastValue(series: Pick<Series, 'points'>): number | null {
  const points = timedPoints(series.points);
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const value = points[index]?.value;
    if (value !== null && value !== undefined) return value;
  }
  return null;
}
