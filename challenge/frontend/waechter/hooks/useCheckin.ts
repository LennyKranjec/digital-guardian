import { useMutation, useQuery } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import {
  getMyQuestionnaire,
  newSubmissionId,
  submitMyResponse,
  toLang,
  type Questionnaire,
  type SubmitReceipt,
} from '../api/client';
import {
  buildAnswers,
  fingerprintOf,
  progressOf,
  resolveSubmissionId,
  type AnswerMap,
  type AnswerValue,
  type SubmissionIdentity,
} from '../model/checkin';

/** Schlüssel unter `waechter.patient.errors.*` zu einem Sendefehler (Statuscodes laut Vertrag). */
export function submitErrorKey(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return 'network';
    if (error.status === 409) return 'conflict';
    if (error.status === 422) return 'invalid';
    if (error.status === 401 || error.status === 403) return 'forbidden';
  }
  return 'generic';
}

/** Fragebogen der aktiven UI-Sprache laden (Sprachwechsel lädt neu; Antworten bleiben erhalten). */
export function useQuestionnaire() {
  const { i18n } = useTranslation();
  const lang = toLang(i18n.resolvedLanguage ?? i18n.language);
  return useQuery({
    queryKey: ['waechter', 'questionnaire', lang],
    queryFn: ({ signal }) => getMyQuestionnaire(lang, signal),
  });
}

/** Antwortstand und Senden. Wiederholung ohne Änderung nutzt dieselbe `client_submission_id`. */
export function useCheckin(questionnaire: Questionnaire) {
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [receipt, setReceipt] = useState<SubmitReceipt | null>(null);
  const identity = useRef<SubmissionIdentity | null>(null);

  const mutation = useMutation({
    mutationFn: submitMyResponse,
    onSuccess: (result) => setReceipt(result),
  });

  const setAnswer = useCallback((key: string, value: AnswerValue) => {
    setAnswers((current) => ({ ...current, [key]: value }));
  }, []);

  const submit = useCallback(() => {
    const list = buildAnswers(questionnaire, answers);
    identity.current = resolveSubmissionId(
      identity.current,
      fingerprintOf(questionnaire.questionnaire_id, list),
      newSubmissionId,
    );
    mutation.mutate({
      client_submission_id: identity.current.id,
      questionnaire_id: questionnaire.questionnaire_id,
      channel: 'web',
      entered_by: 'self',
      answers: list,
      ...(questionnaire.recall ? { recall: questionnaire.recall } : {}),
    });
  }, [questionnaire, answers, mutation]);

  return {
    answers,
    setAnswer,
    progress: progressOf(questionnaire, answers),
    submit,
    isSending: mutation.isPending,
    errorKey: mutation.isError ? submitErrorKey(mutation.error) : null,
    receipt,
  };
}
