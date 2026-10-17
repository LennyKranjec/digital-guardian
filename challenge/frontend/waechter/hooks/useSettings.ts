import { useMutation, useQuery } from '@tanstack/react-query';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import {
  getConfigHistory,
  updateReport,
  updateRules,
  type ConfigState,
  type ReportUpdate,
  type RulesUpdate,
} from '../api/client';
import { useInvalidateClinicData } from './useAcknowledge';
import { useLang } from './useLang';

export function useConfigHistory(kind: 'rules' | 'report') {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'config-history', kind, lang],
    queryFn: ({ signal }) => getConfigHistory(kind, lang, signal),
    retry: false,
  });
}

/** Schlüssel unter `waechter.clinic.settings.errors.*` zu einem Fehler beim Speichern der Konfiguration. */
export function settingsErrorKey(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return 'network';
    if (error.status === 409) return 'conflict';
    if (error.status === 422) {
      if (error.code === 'no_red_rule') return 'noRedRule';
      if (error.code === 'no_red_notification') return 'noRedNotification';
      return 'invalid';
    }
    if (error.status === 401 || error.status === 403) return 'forbidden';
  }
  return 'generic';
}

export function useUpdateRules() {
  const invalidate = useInvalidateClinicData();
  return useMutation<ConfigState, Error, RulesUpdate>({
    mutationFn: updateRules,
    onSuccess: () => invalidate(),
  });
}

export function useUpdateReport() {
  const invalidate = useInvalidateClinicData();
  return useMutation<ConfigState, Error, ReportUpdate>({
    mutationFn: updateReport,
    onSuccess: () => invalidate(),
  });
}
