import { z } from 'zod';

import {
  API_BASE,
  ApiClientError,
  apiGet,
  apiPost,
} from '../../../../platform/frontend/src/shared/api/client';

/**
 * Dokumente ⇒ FHIR (T-21, Entwurf bis zur ärztlichen Bestätigung). Typen und Laufzeitprüfung nach
 * challenge/contract/openapi.yaml (v2.9). Der Dokumenttext verlässt den Browser nur beim Hochladen;
 * der Server speichert ihn nicht.
 */

export const DOCUMENT_MAX_BYTES = 200_000;
export const DOCUMENT_ACCEPT = '.txt,.md,.markdown,.csv,text/plain,text/markdown,text/csv';

export const RESOURCE_TYPES = ['Condition', 'MedicationStatement', 'Observation'] as const;
export const CANDIDATE_STATES = ['draft', 'confirmed', 'discarded'] as const;

export const candidateSchema = z.object({
  candidate_id: z.string(),
  resource_type: z.enum(RESOURCE_TYPES),
  code: z.string(),
  system: z.string(),
  display: z.string(),
  value: z.string().nullish(),
  unit: z.string().nullish(),
  date: z.string().nullish(),
  sukl_code: z.string().nullish(),
  quote: z.string(),
  state: z.enum(CANDIDATE_STATES),
  decided_at: z.string().nullish(),
});
export type DocumentCandidate = z.infer<typeof candidateSchema>;

export const rejectedSchema = z.object({
  resource_type: z.string(),
  code: z.string(),
  quote: z.string(),
  reasons: z.array(z.string()),
});
export type RejectedCandidate = z.infer<typeof rejectedSchema>;

export const documentSchema = z.object({
  document_id: z.string(),
  patient_id: z.string(),
  filename: z.string(),
  sha256: z.string(),
  size_bytes: z.number().int(),
  created_at: z.string(),
  version: z.number().int(),
  extractor: z.object({
    id: z.string(),
    mode: z.enum(['template', 'llm', 'fallback']),
    fallback_reason: z.string().nullish(),
  }),
  candidates: z.array(candidateSchema),
  rejected: z.array(rejectedSchema),
  counts: z.object({
    draft: z.number().int(),
    confirmed: z.number().int(),
    discarded: z.number().int(),
    rejected: z.number().int(),
  }),
});
export type ClinicDocument = z.infer<typeof documentSchema>;

export type CandidateDecision = 'confirm' | 'discard';

const documentsPath = (patientId: string): string =>
  `/waechter/patients/${encodeURIComponent(patientId)}/documents`;

export function listDocuments(patientId: string, signal?: AbortSignal): Promise<ClinicDocument[]> {
  return apiGet(documentsPath(patientId), z.array(documentSchema), signal);
}

export function uploadDocument(
  patientId: string,
  filename: string,
  text: string,
): Promise<ClinicDocument> {
  return apiPost(documentsPath(patientId), { filename, text }, documentSchema);
}

export function decideCandidate(
  patientId: string,
  documentId: string,
  candidateId: string,
  decision: CandidateDecision,
): Promise<ClinicDocument> {
  const path = `${documentsPath(patientId)}/${encodeURIComponent(documentId)}/candidates/${encodeURIComponent(candidateId)}`;
  return apiPost(path, { decision }, documentSchema);
}

/** Entwurfs-Bundle (`application/fhir+json`) als Datei; der Körper wird nicht geparst oder geloggt. */
export async function downloadDraftBundle(
  patientId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}${documentsPath(patientId)}/${encodeURIComponent(documentId)}/bundle`,
      {
        credentials: 'same-origin',
        headers: { Accept: 'application/fhir+json, application/json' },
        signal,
      },
    );
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiClientError(0, 'network_error', 'Network request failed');
  }
  if (!response.ok) throw new ApiClientError(response.status, 'export_failed', response.statusText);
  return response.blob();
}
