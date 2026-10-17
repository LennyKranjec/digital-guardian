import { useQuery } from '@tanstack/react-query';

import { getTriage, getTriageConfig } from '../api/client';
import { useLang } from './useLang';

/**
 * Befundkarte einer Antwort (Standard: die letzte). Wird erst geladen, wenn die Ärztin den Bereich
 * öffnet (`enabled`); kein erneuter Versuch bei Fehlern, damit „noch nicht verfügbar“ sofort erscheint.
 */
export function useTriage(patientId: string, responseId: string | null, enabled: boolean) {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'triage', patientId, responseId, lang],
    queryFn: ({ signal }) => getTriage(patientId, responseId, lang, signal),
    enabled,
    retry: false,
    staleTime: 30_000,
  });
}

/** Regelkarte je Profil (Einstellungen, nur lesen). */
export function useTriageConfig() {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'config', 'triage', lang],
    queryFn: ({ signal }) => getTriageConfig(lang, signal),
    retry: false,
    staleTime: 60_000,
  });
}
