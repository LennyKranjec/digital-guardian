import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  decideCandidate,
  listDocuments,
  uploadDocument,
  type CandidateDecision,
  type ClinicDocument,
} from '../api/documents';

export const documentsKey = (patientId: string) => ['waechter', 'documents', patientId] as const;

/** Dokumente der Patientin; wird erst geladen, wenn der Bereich geöffnet ist (`enabled`). */
export function useDocuments(patientId: string, enabled: boolean) {
  return useQuery({
    queryKey: documentsKey(patientId),
    queryFn: ({ signal }) => listDocuments(patientId, signal),
    enabled,
  });
}

/** Ein geändertes Dokument in die Liste übernehmen (neu: vorn; sonst an gleicher Stelle ersetzen). */
function merge(current: ClinicDocument[] | undefined, next: ClinicDocument): ClinicDocument[] {
  const list = current ?? [];
  return list.some((d) => d.document_id === next.document_id)
    ? list.map((d) => (d.document_id === next.document_id ? next : d))
    : [next, ...list];
}

export function useUploadDocument(patientId: string) {
  const queryClient = useQueryClient();
  return useMutation<ClinicDocument, Error, { filename: string; text: string }>({
    mutationFn: ({ filename, text }) => uploadDocument(patientId, filename, text),
    onSuccess: (document) =>
      queryClient.setQueryData<ClinicDocument[]>(documentsKey(patientId), (c) =>
        merge(c, document),
      ),
  });
}

export function useDecideCandidate(patientId: string) {
  const queryClient = useQueryClient();
  return useMutation<
    ClinicDocument,
    Error,
    { documentId: string; candidateId: string; decision: CandidateDecision }
  >({
    mutationFn: ({ documentId, candidateId, decision }) =>
      decideCandidate(patientId, documentId, candidateId, decision),
    onSuccess: (document) =>
      queryClient.setQueryData<ClinicDocument[]>(documentsKey(patientId), (c) =>
        merge(c, document),
      ),
    // eine verlorene Parallelentscheidung (409): Liste neu laden, damit der Stand stimmt
    onError: () => queryClient.invalidateQueries({ queryKey: documentsKey(patientId) }),
  });
}
