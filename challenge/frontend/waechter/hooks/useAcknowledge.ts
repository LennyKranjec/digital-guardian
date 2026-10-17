import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { acknowledgeAlert, getAlert, type AcknowledgeRequest, type Alert } from '../api/client';
import { useLang } from './useLang';

/** Alle Abfragen, die eine Quittierung oder Aufnahme verändert (Übersicht, Verlauf, Arbeitsliste, Banner, Meldung). */
export function useInvalidateClinicData() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ['waechter'] });
}

/** Schlüssel unter `waechter.clinic.ack.errors.*` zu einem Fehler beim Quittieren. */
export function ackErrorKey(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return 'network';
    if (error.status === 409) return 'conflict';
    if (error.status === 404) return 'notFound';
    if (error.status === 422) return 'invalid';
    if (error.status === 401 || error.status === 403) return 'forbidden';
  }
  return 'generic';
}

export function useAlert(alertId: string) {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'alert', alertId, lang],
    queryFn: ({ signal }) => getAlert(alertId, lang, signal),
  });
}

/** Meldung quittieren; bei Erfolg werden alle abhängigen Abfragen neu geladen. */
export function useAcknowledge(alertId: string) {
  const invalidate = useInvalidateClinicData();
  const lang = useLang();
  return useMutation<Alert, Error, AcknowledgeRequest>({
    mutationFn: (body) => acknowledgeAlert(alertId, body, lang),
    onSuccess: () => invalidate(),
  });
}
