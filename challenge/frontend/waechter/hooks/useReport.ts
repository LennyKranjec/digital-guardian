import { useQueries, useQuery } from '@tanstack/react-query';

import { getAudit, getFact } from '../api/client';
import { useLang } from './useLang';

/** Audit-Auszug der Patientin; ein Fehler (z. B. Route fehlt) lässt den Bericht trotzdem entstehen. */
export function useAudit(patientId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['waechter', 'audit', patientId],
    queryFn: ({ signal }) => getAudit(patientId, signal),
    enabled,
    retry: false,
  });
}

/** Belege der Fußnoten (eine Abfrage je eindeutiger Fakt-ID, gleiche Cache-Schlüssel wie die Beleg-Schublade). */
export function useFootnoteFacts(patientId: string, factIds: readonly string[]) {
  const lang = useLang();
  return useQueries({
    queries: factIds.map((factId) => ({
      queryKey: ['waechter', 'fact', patientId, factId, lang],
      queryFn: ({ signal }: { signal: AbortSignal }) => getFact(patientId, factId, lang, signal),
      retry: false,
    })),
  });
}

/** Fußnotennummern in Reihenfolge des ersten Auftretens (eine Nummer je Fakt-ID). */
export function footnoteOrder(sentences: readonly { refs: readonly string[] }[]): string[] {
  const order: string[] = [];
  for (const sentence of sentences) {
    for (const ref of sentence.refs) if (!order.includes(ref)) order.push(ref);
  }
  return order;
}
