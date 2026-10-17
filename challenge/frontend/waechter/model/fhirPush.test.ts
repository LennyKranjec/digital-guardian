import { describe, expect, it } from 'vitest';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import {
  MAX_ERROR_LENGTH,
  outcomeOf,
  outcomeOfError,
  shortError,
  transactionFileName,
} from './fhirPush';

describe('FHIR-Push: Anzeigelogik', () => {
  it('macht aus „sent“ Zahlen (fehlende Zahlen = 0)', () => {
    expect(outcomeOf({ status: 'sent', entries: 12, created: 9, updated: 3 })).toEqual({
      kind: 'sent',
      entries: 12,
      created: 9,
      updated: 3,
    });
    expect(outcomeOf({ status: 'sent' })).toEqual({
      kind: 'sent',
      entries: 0,
      created: 0,
      updated: 0,
    });
  });

  it('behandelt „disabled“ nicht als Fehler', () => {
    expect(outcomeOf({ status: 'disabled' })).toEqual({ kind: 'disabled' });
  });

  it('zeigt bei „failed“ HTTP-Status und den ersten Kurztext', () => {
    expect(
      outcomeOf({ status: 'failed', http_status: 500, errors: ['', '  Timeout ', 'zweiter'] }),
    ).toEqual({
      kind: 'failed',
      httpStatus: 500,
      error: 'Timeout',
    });
    expect(outcomeOf({ status: 'failed' })).toEqual({
      kind: 'failed',
      httpStatus: null,
      error: null,
    });
  });

  it('kürzt lange Fehlertexte', () => {
    const text = shortError(['y'.repeat(300)]) ?? '';
    expect(text.length).toBe(MAX_ERROR_LENGTH);
    expect(text.endsWith('…')).toBe(true);
    expect(shortError(['kurz'])).toBe('kurz');
    expect(shortError([])).toBeNull();
    expect(shortError(null)).toBeNull();
  });

  it.each([
    [new ApiClientError(403, 'forbidden', 'x'), 'forbidden'],
    [new ApiClientError(401, 'unauthenticated', 'x'), 'forbidden'],
    [new ApiClientError(409, 'not_synthetic', 'x'), 'notSynthetic'],
    [new ApiClientError(409, 'other', 'x'), 'generic'],
    [new ApiClientError(404, 'not_found', 'x'), 'unavailable'],
    [new ApiClientError(501, 'x', 'x'), 'unavailable'],
    [new ApiClientError(0, 'network', 'x'), 'network'],
    [new ApiClientError(500, 'boom', 'x'), 'generic'],
    [new Error('irgendwas'), 'generic'],
  ] as const)('ordnet den Fehler %# dem Zustand „%s“ zu', (error, kind) => {
    expect(outcomeOfError(error).kind).toBe(kind);
  });

  it('macht aus dem Pseudonym einen sicheren Dateinamen für das Transaction-Bundle', () => {
    expect(transactionFileName('SYN-0001')).toBe('SYN-0001-transaction-bundle.json');
    expect(transactionFileName('SYN 0001/../x')).toBe('SYN_0001____x-transaction-bundle.json');
    expect(transactionFileName('')).toBe('patient-transaction-bundle.json');
  });
});
