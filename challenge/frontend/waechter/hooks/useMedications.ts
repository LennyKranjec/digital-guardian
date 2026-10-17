import { useQuery } from '@tanstack/react-query';

import { getMedication, searchMedications } from '../api/client';
import { cleanQuery, canSearch } from '../model/medications';
import { useLang } from './useLang';

/** Suche (nur ab 2 Zeichen); kein erneuter Versuch bei 4xx, damit 422/403 sofort erscheinen. */
export function useMedicationSearch(rawQuery: string) {
  const lang = useLang();
  const query = cleanQuery(rawQuery);
  return useQuery({
    queryKey: ['waechter', 'medications', query, lang],
    queryFn: ({ signal }) => searchMedications(query, lang, signal),
    enabled: canSearch(rawQuery),
    retry: false,
    staleTime: 30_000,
  });
}

export function useMedication(medicationId: string) {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'medication', medicationId, lang],
    queryFn: ({ signal }) => getMedication(medicationId, lang, signal),
    retry: false,
    staleTime: 30_000,
  });
}
