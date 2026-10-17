import { describe, expect, it } from 'vitest';

import { formatAbsolute, formatRelative, relativeValue } from './time';

const NOW = new Date('2026-10-17T09:00:00+02:00');

describe('relativeValue', () => {
  it('rechnet unter einer Stunde in Minuten, unter 24 h in Stunden', () => {
    expect(relativeValue('2026-10-17T08:30:00+02:00', NOW)).toEqual({ value: -30, unit: 'minute' });
    expect(relativeValue('2026-10-17T09:00:00+02:00', NOW)).toEqual({ value: 0, unit: 'minute' });
    expect(relativeValue('2026-10-17T06:00:00+02:00', NOW)).toEqual({ value: -3, unit: 'hour' });
    expect(relativeValue('2026-10-17T11:00:00+02:00', NOW)).toEqual({ value: 2, unit: 'hour' });
  });

  it('rechnet ab 24 h in Prager Kalendertagen', () => {
    expect(relativeValue('2026-10-16T08:00:00+02:00', NOW)).toEqual({ value: -1, unit: 'day' });
    expect(relativeValue('2026-10-15T23:00:00+02:00', NOW)).toEqual({ value: -2, unit: 'day' });
    expect(relativeValue('2026-10-20T10:00:00+02:00', NOW)).toEqual({ value: 3, unit: 'day' });
  });

  it('zählt Tage in Europe/Prague, nicht in UTC (G-04)', () => {
    const now = new Date('2026-10-19T09:00:00+02:00');
    // 22:30 UTC am 16.10. ist 00:30 in Prag am 17.10. ⇒ 2 Kalendertage, nicht 3
    expect(relativeValue('2026-10-16T22:30:00Z', now)).toEqual({ value: -2, unit: 'day' });
  });

  it('liefert null für ungültige Zeitangaben', () => {
    expect(relativeValue('kein Datum', NOW)).toBeNull();
  });
});

describe('formatRelative', () => {
  it('formatiert in der Anzeigesprache', () => {
    expect(formatRelative('2026-10-17T06:00:00+02:00', NOW, 'de')).toBe('vor 3 Stunden');
    expect(formatRelative('2026-10-17T06:00:00+02:00', NOW, 'en')).toBe('3 hours ago');
    expect(formatRelative('2026-10-16T08:00:00+02:00', NOW, 'de')).toBe('gestern');
  });

  it('zeigt Zukünftiges nur mit allowFuture (Termine), nie als „letzte Eingabe“', () => {
    expect(formatRelative('2026-10-20T10:00:00+02:00', NOW, 'de', { allowFuture: true })).toBe(
      'in 3 Tagen',
    );
    expect(formatRelative('2026-10-20T10:00:00+02:00', NOW, 'de')).toBeNull();
  });

  it('gibt für ungültige Eingaben null zurück', () => {
    expect(formatRelative('x', NOW, 'de')).toBeNull();
  });
});

describe('formatAbsolute', () => {
  it('zeigt Prager Ortszeit, auch über die Zeitumstellung', () => {
    // Sommerzeit (UTC+2)
    expect(formatAbsolute('2026-10-17T05:00:00Z', 'de')).toMatch(/17\.10\.2026.*07:00/);
    // nach der Umstellung am 25.10.2026 (UTC+1)
    expect(formatAbsolute('2026-11-01T05:00:00Z', 'de')).toMatch(/01\.11\.2026.*06:00/);
  });

  it('gibt ungültige Eingaben unverändert zurück', () => {
    expect(formatAbsolute('kein Datum', 'de')).toBe('kein Datum');
  });
});
