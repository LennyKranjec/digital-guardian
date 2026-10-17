import { describe, expect, it } from 'vitest';

import type { ConfigRule } from '../api/client';
import { ALERT_RED, ALERT_YELLOW, TIMELINE } from '../testing/cockpit-fixtures';
import {
  addDays,
  alertFactId,
  alertsForSeries,
  buildEvents,
  COMPACT_FALLBACK,
  COMPACT_MAX,
  domainOf,
  lastValue,
  orderSeries,
  pickCompactSeries,
  pragueDateString,
  pragueDayRange,
  pragueDayStartMs,
  scaleX,
  scaleY,
  thresholdsFor,
  timeTicks,
  timedPoints,
  timelineRange,
  unmatchedAlerts,
  valueRuns,
} from './timeline';

const iso = (ms: number | null) => (ms === null ? null : new Date(ms).toISOString());
const NOW = new Date('2026-10-17T09:00:00+02:00');

describe('timelineRange', () => {
  it('sendet für „Alles“ keine Grenzen', () => {
    expect(timelineRange('all', { serverNow: null, lastVisitAt: null })).toEqual({});
  });

  it('beginnt „Seit letztem Termin“ am letzten Termin (UTC-ISO), ohne Termin nicht verfügbar', () => {
    expect(
      timelineRange('visit', { serverNow: NOW, lastVisitAt: '2026-10-10T10:00:00+02:00' }),
    ).toEqual({
      from: '2026-10-10T08:00:00.000Z',
    });
    expect(timelineRange('visit', { serverNow: NOW, lastVisitAt: null })).toBeNull();
    expect(timelineRange('visit', { serverNow: NOW, lastVisitAt: 'kein Datum' })).toBeNull();
  });

  it('rechnet 14 und 28 Tage gegen die Serverzeit, ohne sie nicht verfügbar (nie Browseruhr)', () => {
    expect(timelineRange('14d', { serverNow: NOW, lastVisitAt: null })).toEqual({
      from: '2026-10-03T07:00:00.000Z',
    });
    expect(timelineRange('28d', { serverNow: NOW, lastVisitAt: null })).toEqual({
      from: '2026-09-19T07:00:00.000Z',
    });
    expect(timelineRange('14d', { serverNow: null, lastVisitAt: null })).toBeNull();
    expect(
      timelineRange('28d', { serverNow: null, lastVisitAt: '2026-10-10T10:00:00+02:00' }),
    ).toBeNull();
  });
});

describe('Prager Tage', () => {
  it('liefert Tagesbeginn in Sommer- und Winterzeit', () => {
    expect(iso(pragueDayStartMs('2026-10-17'))).toBe('2026-10-16T22:00:00.000Z');
    expect(iso(pragueDayStartMs('2026-11-01'))).toBe('2026-10-31T23:00:00.000Z');
  });

  it('kennt den 25-Stunden-Tag der Zeitumstellung (25.10.2026)', () => {
    const range = pragueDayRange('2026-10-25');
    expect(iso(range?.[0] ?? null)).toBe('2026-10-24T22:00:00.000Z');
    expect(iso(range?.[1] ?? null)).toBe('2026-10-25T23:00:00.000Z');
    expect(((range?.[1] ?? 0) - (range?.[0] ?? 0)) / 3_600_000).toBe(25);
  });

  it('lehnt ungültige Datumsangaben ab', () => {
    expect(pragueDayStartMs('17.10.2026')).toBeNull();
    expect(pragueDayRange('kaputt')).toBeNull();
  });

  it('ordnet Zeitpunkte dem Prager Kalendertag zu, nicht dem UTC-Tag', () => {
    expect(pragueDateString(Date.parse('2026-10-16T22:30:00Z'))).toBe('2026-10-17');
    expect(pragueDateString(Date.parse('2026-10-17T21:30:00Z'))).toBe('2026-10-17');
  });

  it('addiert Tage über Monatsgrenzen', () => {
    expect(addDays('2026-10-31', 1)).toBe('2026-11-01');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
  });
});

describe('Achsen', () => {
  const domain = {
    from: Date.parse('2026-10-10T10:00:00+02:00'),
    to: Date.parse('2026-10-17T09:00:00+02:00'),
  };

  it('setzt Tagesmarken auf Prager Mitternacht', () => {
    const ticks = timeTicks(domain.from, domain.to, 7);
    expect(ticks.map((tick) => tick.date)).toEqual([
      '2026-10-11',
      '2026-10-12',
      '2026-10-13',
      '2026-10-14',
      '2026-10-15',
      '2026-10-16',
      '2026-10-17',
    ]);
    expect(iso(ticks[0]?.ms ?? null)).toBe('2026-10-10T22:00:00.000Z');
  });

  it('wählt bei wenig Platz eine größere Schrittweite (höchstens maxTicks)', () => {
    const ticks = timeTicks(domain.from, domain.to, 3);
    expect(ticks.map((tick) => tick.date)).toEqual(['2026-10-11', '2026-10-14', '2026-10-17']);
    expect(timeTicks(domain.to, domain.from, 3)).toEqual([]);
  });

  it('bildet Zeit linear auf Pixel ab und begrenzt Werte außerhalb auf den Rand', () => {
    const x = scaleX(domain, 34, 534);
    expect(x(domain.from)).toBe(34);
    expect(x(domain.to)).toBe(534);
    expect(x(domain.from - 1e9)).toBe(34);
    expect(x(domain.to + 1e9)).toBe(534);
    expect(x((domain.from + domain.to) / 2)).toBeCloseTo(284, 5);
  });

  it('zeichnet die Skala 0–4 mit 0 unten', () => {
    const y = scaleY(14, 114);
    expect(y(0)).toBe(114);
    expect(y(4)).toBe(14);
    expect(y(2)).toBe(64);
    expect(y(9)).toBe(14);
    expect(y(-1)).toBe(114);
  });

  it('liest den Zeitraum der Antwort und lehnt leere oder umgekehrte Zeiträume ab', () => {
    expect(domainOf(TIMELINE)).toEqual(domain);
    expect(domainOf({ from: TIMELINE.to, to: TIMELINE.from })).toBeNull();
    expect(domainOf({ from: 'x', to: 'y' })).toBeNull();
  });
});

describe('Kurven', () => {
  const point = (day: number, value: number | null) => ({
    t: `2026-10-${String(day).padStart(2, '0')}T08:00:00+02:00`,
    value,
    fact_id: `obs-${day}`,
  });

  it('verbindet nie über eine Lücke: null trennt die Linie', () => {
    const runs = valueRuns(timedPoints([point(1, 1), point(2, 2), point(3, null), point(4, 3)]));
    expect(runs.map((run) => run.map((entry) => entry.value))).toEqual([[1, 2], [3]]);
  });

  it('behandelt führende, folgende und aufeinanderfolgende Lücken sowie reine Lücken', () => {
    expect(
      valueRuns(
        timedPoints([
          point(1, null),
          point(2, 1),
          point(3, null),
          point(4, null),
          point(5, 2),
          point(6, null),
        ]),
      ).map((run) => run.map((entry) => entry.value)),
    ).toEqual([[1], [2]]);
    expect(valueRuns(timedPoints([point(1, null), point(2, null)]))).toEqual([]);
    expect(valueRuns([])).toEqual([]);
  });

  it('sortiert Punkte nach Zeit und verwirft ungültige Zeiten', () => {
    const points = timedPoints([
      point(3, 3),
      { t: 'kaputt', value: 9, fact_id: 'obs-x' },
      point(1, 1),
    ]);
    expect(points.map((entry) => entry.value)).toEqual([1, 3]);
  });

  it('ordnet Symptome mit offener Meldung zuerst, sonst in Serverreihenfolge', () => {
    const order = orderSeries(TIMELINE.series, TIMELINE.alerts).map((entry) => entry.symptom_key);
    expect(TIMELINE.series.map((entry) => entry.symptom_key)).toEqual([
      'fatigue',
      'nausea',
      'fever',
    ]);
    expect(order).toEqual(['nausea', 'fever', 'fatigue']);
  });

  it('zählt quittierte Meldungen nicht als offen und passt auf Merkmal, wenn angegeben', () => {
    const acknowledged = { ...ALERT_RED, status: 'acknowledged' as const };
    expect(orderSeries(TIMELINE.series, [acknowledged]).map((entry) => entry.symptom_key)).toEqual([
      'fatigue',
      'nausea',
      'fever',
    ]);
    const otherAttribute = { ...ALERT_RED, attribute: 'severity' };
    expect(
      orderSeries(TIMELINE.series, [otherAttribute]).map((entry) => entry.symptom_key),
    ).toEqual(['fatigue', 'nausea', 'fever']);
    const noAttribute = { ...ALERT_RED, attribute: null };
    expect(orderSeries(TIMELINE.series, [noAttribute])[0]?.symptom_key).toBe('fever');
  });

  it('ordnet Meldungen Kurven zu und findet Meldungen ohne Kurve', () => {
    const fever = TIMELINE.series[2];
    if (!fever) throw new Error('Fixture fehlt');
    expect(alertsForSeries(TIMELINE.alerts, fever).map((alert) => alert.alert_id)).toEqual([
      'al-1',
    ]);
    expect(
      unmatchedAlerts(TIMELINE.alerts, TIMELINE.series).map((alert) => alert.alert_id),
    ).toEqual(['al-9']);
    expect(alertsForSeries([ALERT_YELLOW], fever)).toEqual([]);
  });

  it('bildet die Faktkennung einer Meldung mit Präfix alert-', () => {
    expect(alertFactId({ alert_id: 'al-1' })).toBe('alert-al-1');
    expect(alertFactId({ alert_id: 'alert-77' })).toBe('alert-77');
  });
});

describe('thresholdsFor', () => {
  const rules: ConfigRule[] = [
    {
      id: 'R-SEV-01',
      kind: 'threshold',
      level: 'red',
      enabled: true,
      attributes: ['severity', 'interference'],
      params: { min_value: 3 },
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
      params: { min_value: 2 },
    },
    {
      id: 'R-DLT-01',
      kind: 'baseline_delta',
      level: 'yellow',
      enabled: true,
      params: { min_value: 2, min_delta: 2 },
    },
    { id: 'R-NOV-01', kind: 'threshold', level: 'red', enabled: true, params: {} },
  ];

  it('wählt aktive Schwellenregeln, die zu Symptom und Merkmal passen (leer = alle)', () => {
    expect(thresholdsFor({ symptom_key: 'nausea', attribute: 'severity' }, rules)).toEqual([
      { ruleId: 'R-SEV-01', value: 3 },
    ]);
    expect(thresholdsFor({ symptom_key: 'fever', attribute: 'presence' }, rules)).toEqual([
      { ruleId: 'R-URG-01', value: 1 },
    ]);
  });

  it('ignoriert deaktivierte Regeln, andere Regelarten und Regeln ohne min_value', () => {
    expect(thresholdsFor({ symptom_key: 'nausea', attribute: 'frequency' }, rules)).toEqual([]);
    expect(thresholdsFor({ symptom_key: 'nausea', attribute: 'severity' }, [])).toEqual([]);
  });
});

describe('buildEvents', () => {
  const events = buildEvents(TIMELINE);

  it('sortiert zeitlich aufsteigend', () => {
    const times = events.map((event) => event.ms);
    expect(times).toEqual([...times].sort((a, b) => a - b));
  });

  it('bündelt Antworten desselben Zeitpunkts zu einer Zeile und behält Lücken als null', () => {
    const responses = events.filter((event) => event.kind === 'response');
    const latest = responses.at(-1);
    expect(latest?.kind === 'response' && latest.values.map((entry) => entry.value)).toEqual([
      2, 3, 1,
    ]);
    const gapDay = responses.find((event) => event.ms === Date.parse('2026-10-14T08:00:00+02:00'));
    expect(gapDay?.kind === 'response' && gapDay.values.some((entry) => entry.value === null)).toBe(
      true,
    );
  });

  it('enthält Meldungen, Quittierungen, Aufnahmen, Termine und fehlende Tage', () => {
    const kinds = new Set(events.map((event) => event.kind));
    expect([...kinds].sort()).toEqual([
      'acknowledged',
      'alert',
      'assessment',
      'missing',
      'response',
      'visit',
    ]);
    const missing = events.find((event) => event.kind === 'missing');
    expect(iso(missing?.ms ?? null)).toBe('2026-10-13T22:00:00.000Z');
    const acknowledged = events.find((event) => event.kind === 'acknowledged');
    expect(iso(acknowledged?.ms ?? null)).toBe('2026-10-15T08:00:00.000Z');
    expect(
      events
        .filter((event) => event.kind === 'visit')
        .map((event) => event.kind === 'visit' && event.visitKind),
    ).toEqual(['past', 'planned']);
  });

  it('übergeht ungültige Zeitangaben', () => {
    const broken = buildEvents({
      ...TIMELINE,
      series: [],
      alerts: [],
      visits: [{ at: 'x' }],
      assessments: [],
      missing_days: ['kaputt'],
    });
    expect(broken).toEqual([]);
  });
});

describe('kompakte Übersicht (pickCompactSeries, lastValue)', () => {
  const series = (key: string, values: (number | null)[]) => ({
    symptom_key: key,
    attribute: 'severity',
    label: key,
    points: values.map((value, index) => ({
      t: `2026-10-1${index}T08:00:00+02:00`,
      value,
      fact_id: `obs-${key}-${index}`,
    })),
  });
  const alert = (key: string, status: 'open' | 'acknowledged') => ({
    ...ALERT_YELLOW,
    alert_id: `al-${key}-${status}`,
    symptom_key: key,
    attribute: null,
    status,
  });

  it('wählt Symptome mit offener Meldung zuerst und lässt die übrigen weg', () => {
    const list = [series('a', [1]), series('b', [2]), series('c', [3])];
    const picked = pickCompactSeries(list, [alert('c', 'open'), alert('b', 'open')]);
    expect(picked.map((entry) => entry.series.symptom_key)).toEqual(['b', 'c']);
    expect(picked.every((entry) => entry.openAlerts.length > 0)).toBe(true);
  });

  it('zählt quittierte Meldungen nicht als offen und zeigt dann die ersten drei in Serverreihenfolge', () => {
    const list = [series('a', [1]), series('b', [2]), series('c', [3]), series('d', [4])];
    const picked = pickCompactSeries(list, [alert('d', 'acknowledged')]);
    expect(picked.map((entry) => entry.series.symptom_key)).toEqual(['a', 'b', 'c']);
    expect(picked).toHaveLength(COMPACT_FALLBACK);
    expect(picked.every((entry) => entry.openAlerts.length === 0)).toBe(true);
  });

  it('begrenzt die Karten auf höchstens vier', () => {
    const list = ['a', 'b', 'c', 'd', 'e', 'f'].map((key) => series(key, [1]));
    const alerts = list.map((entry) => alert(entry.symptom_key, 'open'));
    expect(pickCompactSeries(list, alerts)).toHaveLength(COMPACT_MAX);
    expect(pickCompactSeries([], [])).toEqual([]);
  });

  it('ordnet eine Meldung mit Merkmal nur der passenden Kurve zu', () => {
    const list = [
      { ...series('a', [1]), attribute: 'presence' },
      { ...series('a', [2]), attribute: 'severity' },
    ];
    const picked = pickCompactSeries(list, [{ ...alert('a', 'open'), attribute: 'severity' }]);
    expect(picked.map((entry) => entry.series.attribute)).toEqual(['severity']);
  });

  it('nimmt als letzten Wert den jüngsten vorhandenen und ignoriert übersprungene Tage am Ende', () => {
    expect(lastValue(series('a', [1, 2, 3]))).toBe(3);
    expect(lastValue(series('a', [1, 2, null]))).toBe(2);
    expect(lastValue(series('a', [null, null]))).toBeNull();
    expect(lastValue(series('a', []))).toBeNull();
    expect(lastValue(series('a', [0]))).toBe(0);
  });
});
