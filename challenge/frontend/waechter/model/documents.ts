import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { DOCUMENT_MAX_BYTES } from '../api/documents';

const ACCEPTED_SUFFIXES = ['.txt', '.md', '.markdown', '.csv'] as const;

/** Schlüssel unter `waechter.clinic.documents.errors.*`; `null` = Datei darf hochgeladen werden. */
export function fileProblem(name: string, size: number): string | null {
  const lower = name.toLocaleLowerCase();
  if (lower.endsWith('.pdf')) return 'pdf';
  if (!ACCEPTED_SUFFIXES.some((suffix) => lower.endsWith(suffix))) return 'format';
  if (size > DOCUMENT_MAX_BYTES) return 'tooLarge';
  if (size === 0) return 'empty';
  return null;
}

/** Schlüssel unter `waechter.clinic.documents.errors.*` zu einem Fehler der Dokument-API. */
export function documentErrorKey(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return 'network';
    if (error.status === 401 || error.status === 403) return 'forbidden';
    if (error.status === 404) return 'notFound';
    if (error.status === 409) return error.code === 'not_synthetic' ? 'notSynthetic' : 'conflict';
    if (error.status === 413) return 'tooLarge';
    if (error.status === 415) return error.code === 'pdf_not_supported' ? 'pdf' : 'format';
    if (error.status === 422) return 'invalid';
  }
  return 'generic';
}

/** Anzeigeform eines Laborwerts: `108 g/l`; leer, wenn es keinen Wert gibt. */
export function valueText(value: string | null | undefined, unit: string | null | undefined) {
  return value ? `${value}${unit ? ` ${unit}` : ''}` : '';
}
