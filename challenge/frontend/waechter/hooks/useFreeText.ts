import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

import { useMeta } from '../../../../platform/frontend/src/features/system/api';
import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import {
  answerFollowups,
  freeTextFeatureSchema,
  getFollowupCards,
  getFreeTexts,
  postFreeText,
  type FollowupAnswers,
  type FreeTextFeature,
  type FreeTextReceipt,
  type FreeTextSubmit,
  type SubmitReceipt,
} from '../api/client';
import { useLang } from './useLang';

/** Rückfall, solange `/meta` nichts über den Freitext sagt (älteres Backend): Feld bleibt verborgen. */
const OFF: FreeTextFeature = { enabled: false, max_length: 500 };

/** Schalter und Höchstlänge aus `GET /meta` → `waechter.free_text` (WAECHTER_FREETEXT, T-22). */
export function useFreeTextFeature(): FreeTextFeature {
  const meta = useMeta();
  return useMemo(() => {
    const data = meta.data as { waechter?: { free_text?: unknown } } | undefined;
    const parsed = freeTextFeatureSchema.safeParse(data?.waechter?.free_text);
    return parsed.success ? parsed.data : OFF;
  }, [meta.data]);
}

/** Schlüssel unter `waechter.patient.freeText.errors.*` zu einem Fehler beim Speichern. */
export function freeTextErrorKey(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return 'network';
    if (error.status === 409) return 'conflict';
    if (error.status === 422) return 'invalid';
    if (error.status === 401 || error.status === 403) return 'forbidden';
  }
  return 'generic';
}

/** Freitext zu einer eigenen Antwort speichern (idempotent je Antwort, nie eine Meldung). */
export function usePostFreeText() {
  const queryClient = useQueryClient();
  return useMutation<FreeTextReceipt, Error, FreeTextSubmit>({
    mutationFn: (body) => postFreeText(body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['waechter', 'free-text-followups'] }),
  });
}

/** Freitexte einer Patientin für das Cockpit (neueste zuerst, Vorschläge nicht bewertet). */
export function useFreeTexts(patientId: string) {
  const lang = useLang();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['waechter', 'free-texts', patientId, lang],
    queryFn: ({ signal }) => getFreeTexts(patientId, lang, signal),
  });
  return { ...query, refresh: () => queryClient.invalidateQueries({ queryKey: ['waechter'] }) };
}

/** Offene Folgefrage-Karten der Patientin (kritische Symptome zuerst); nur bei eingeschaltetem Freitext. */
export function useFollowupCards() {
  const lang = useLang();
  const feature = useFreeTextFeature();
  return useQuery({
    queryKey: ['waechter', 'free-text-followups', lang],
    queryFn: ({ signal }) => getFollowupCards(lang, signal),
    enabled: feature.enabled,
  });
}

/** Antwort auf Folgefragen eines Freitexts senden; danach sind die Karten neu zu laden. */
export function useAnswerFollowups(freeTextId: string) {
  const queryClient = useQueryClient();
  return useMutation<SubmitReceipt, Error, FollowupAnswers>({
    mutationFn: (body) => answerFollowups(freeTextId, body),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['waechter', 'free-text-followups'] }),
  });
}
