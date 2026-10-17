import { useMutation, useQuery } from '@tanstack/react-query';
import { useRef } from 'react';

import {
  createAssessment,
  getAssessmentTemplate,
  newSubmissionId,
  type Assessment,
  type AssessmentCreate,
} from '../api/client';
import { resolveSubmissionId, type SubmissionIdentity } from '../model/checkin';
import { useInvalidateClinicData } from './useAcknowledge';
import { useLang } from './useLang';

export function useAssessmentTemplate(patientId: string) {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'assessment-template', patientId, lang],
    queryFn: ({ signal }) => getAssessmentTemplate(patientId, lang, signal),
  });
}

/**
 * Aufnahme speichern. Bei unveränderter Nutzlast bleibt `client_submission_id` gleich (Wiederholung
 * nach Netzfehler ⇒ idempotent, kein Doppelsatz); ändert sich die Nutzlast, entsteht eine neue ID.
 */
export function useCreateAssessment(patientId: string) {
  const invalidate = useInvalidateClinicData();
  const identity = useRef<SubmissionIdentity | null>(null);
  const mutation = useMutation<Assessment, Error, AssessmentCreate>({
    mutationFn: (body) => createAssessment(patientId, body),
    onSuccess: () => invalidate(),
  });

  function submit(fingerprint: string, payload: Omit<AssessmentCreate, 'client_submission_id'>) {
    identity.current = resolveSubmissionId(identity.current, fingerprint, newSubmissionId);
    mutation.mutate({ ...payload, client_submission_id: identity.current.id });
  }

  return { mutation, submit };
}
