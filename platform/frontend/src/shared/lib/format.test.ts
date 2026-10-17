import { describe, expect, it } from 'vitest';

import { formatDate, formatDateTime } from './format';

describe('format', () => {
  it('zeigt reine Datumswerte UTC-stabil', () => {
    expect(formatDate('2026-10-14', 'de')).toBe('14.10.2026');
    expect(formatDate('2026-10-14', 'en')).toContain('2026');
  });

  it('gibt unlesbare Werte unverändert zurück', () => {
    expect(formatDate('kein-datum', 'de')).toBe('kein-datum');
    expect(formatDateTime('kein-datum', 'de')).toBe('kein-datum');
  });
});
