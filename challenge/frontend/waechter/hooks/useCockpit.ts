import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  generateSummary,
  getFact,
  getOverview,
  type Alert,
  type Overview,
  type Summary,
} from '../api/client';
import { useLang } from './useLang';

export const overviewKey = (patientId: string, lang: string) =>
  ['waechter', 'overview', patientId, lang] as const;

export function useOverview(patientId: string) {
  const lang = useLang();
  return useQuery({
    queryKey: overviewKey(patientId, lang),
    queryFn: ({ signal }) => getOverview(patientId, lang, signal),
  });
}

/** Neue Kurzfassung erzeugen und direkt in die Übersicht übernehmen (kein zweiter Abruf nötig). */
export function useGenerateSummary(patientId: string) {
  const queryClient = useQueryClient();
  const lang = useLang();
  return useMutation<Summary, Error>({
    mutationFn: () => generateSummary(patientId, lang),
    onSuccess: (summary) => {
      queryClient.setQueryData<Overview>(overviewKey(patientId, lang), (current) =>
        current ? { ...current, summary } : current,
      );
    },
  });
}

export function useFact(patientId: string, factId: string) {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'fact', patientId, factId, lang],
    queryFn: ({ signal }) => getFact(patientId, factId, lang, signal),
  });
}

const LEVEL_RANK: Record<Alert['level'], number> = { red: 0, yellow: 1, grey: 2 };

/** Rote zuerst, dann gelb, grau; innerhalb einer Stufe bleibt die Reihenfolge des Servers. */
export function sortAlerts(alerts: readonly Alert[]): Alert[] {
  return alerts
    .map((alert, index) => ({ alert, index }))
    .sort((a, b) => LEVEL_RANK[a.alert.level] - LEVEL_RANK[b.alert.level] || a.index - b.index)
    .map(({ alert }) => alert);
}
