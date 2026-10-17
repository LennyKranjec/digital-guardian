import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import type { FhirPushResult } from '../api/client';

/**
 * Anzeigelogik des FHIR-Push (Vertrag v2.6, keine UI): aus der Serverantwort bzw. dem Fehler wird genau
 * ein Zustand für die Statuszeile. Der Server entscheidet; hier wird nichts bewertet oder wiederholt.
 */

export const MAX_ERROR_LENGTH = 120;

export type PushOutcome =
  | { kind: 'sent'; entries: number; created: number; updated: number }
  | { kind: 'disabled' }
  | { kind: 'failed'; httpStatus: number | null; error: string | null }
  /** Fehler vor einer Serverantwort bzw. HTTP-Fehler des Wächter-Backends */
  | { kind: 'forbidden' }
  | { kind: 'notSynthetic' }
  | { kind: 'unavailable' }
  | { kind: 'network' }
  | { kind: 'generic' };

/** Erste Fehlermeldung des Servers, gekürzt (Kurztext ohne Patientendaten; die Anzeige bleibt kurz). */
export function shortError(errors: readonly string[] | null | undefined): string | null {
  const first = (errors ?? []).map((entry) => entry.trim()).find((entry) => entry !== '');
  if (!first) return null;
  return first.length > MAX_ERROR_LENGTH ? `${first.slice(0, MAX_ERROR_LENGTH - 1)}…` : first;
}

export function outcomeOf(result: FhirPushResult): PushOutcome {
  if (result.status === 'sent') {
    return {
      kind: 'sent',
      entries: result.entries ?? 0,
      created: result.created ?? 0,
      updated: result.updated ?? 0,
    };
  }
  if (result.status === 'disabled') return { kind: 'disabled' };
  return {
    kind: 'failed',
    httpStatus: result.http_status ?? null,
    error: shortError(result.errors),
  };
}

export function outcomeOfError(error: unknown): PushOutcome {
  if (!(error instanceof ApiClientError)) return { kind: 'generic' };
  if (error.isNetwork) return { kind: 'network' };
  if (error.status === 403 || error.status === 401) return { kind: 'forbidden' };
  if (error.status === 409)
    return { kind: error.code === 'not_synthetic' ? 'notSynthetic' : 'generic' };
  if (error.status === 404 || error.status === 501) return { kind: 'unavailable' };
  return { kind: 'generic' };
}

/** Dateiname `<pseudonym>-transaction-bundle.json`; nur sichere Zeichen. */
export function transactionFileName(pseudonym: string): string {
  const safe = pseudonym.replace(/[^A-Za-z0-9_-]/g, '_');
  return `${safe || 'patient'}-transaction-bundle.json`;
}
