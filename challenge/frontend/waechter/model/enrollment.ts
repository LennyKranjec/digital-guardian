import { z } from 'zod';

import { LANGS, type EnrollmentCreate } from '../api/client';

/**
 * T-34 Einschreibung: Formularprüfung (zod) und Umwandlung in den Request-Body.
 * Das System schlägt weder Diagnose noch Therapie vor; Code und Regime wählt die Ärztin.
 * Die fachliche Prüfung (Regime vorhanden, Diagnosegruppe, ≤ 30 Tage Zukunft) macht der Server.
 */

export const ICD10_PATTERN = /^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$/;

export const ENROLL_FIELDS = ['diagnosis_code', 'regimen_id', 'cycle_start', 'language'] as const;
export type EnrollField = (typeof ENROLL_FIELDS)[number];

export const enrollmentFormSchema = z.object({
  diagnosis_code: z
    .string()
    .trim()
    .transform((value) => value.toUpperCase())
    .refine((value) => value === '' || ICD10_PATTERN.test(value), { message: 'icd10' }),
  regimen_id: z.string().min(1, { message: 'required' }),
  cycle_start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, { message: 'date' }),
  language: z.enum(LANGS),
});
export type EnrollmentForm = z.input<typeof enrollmentFormSchema>;

export type EnrollErrors = Partial<Record<EnrollField, string>>;

export type EnrollParse =
  | { ok: true; body: Omit<EnrollmentCreate, 'client_request_id'> }
  | { ok: false; errors: EnrollErrors };

/** Prüft das Formular; Fehler als Schlüssel `required | icd10 | date | invalid` je Feld. */
export function parseEnrollment(form: EnrollmentForm): EnrollParse {
  const result = enrollmentFormSchema.safeParse(form);
  if (!result.success) {
    const errors: EnrollErrors = {};
    for (const issue of result.error.issues) {
      const field = issue.path[0];
      if (typeof field === 'string' && (ENROLL_FIELDS as readonly string[]).includes(field)) {
        errors[field as EnrollField] ??= issue.message === 'Required' ? 'required' : issue.message;
      }
    }
    return { ok: false, errors };
  }
  const data = result.data;
  return {
    ok: true,
    body: {
      diagnosis_code: data.diagnosis_code === '' ? null : data.diagnosis_code,
      regimen_id: data.regimen_id,
      cycle_start: data.cycle_start,
      language: data.language,
    },
  };
}

const SERVER_CODES: Record<string, string> = {
  unknown_regimen: 'required',
  invalid_format: 'icd10',
  unknown_diagnosis_group: 'unknownGroup',
  too_far_in_future: 'future',
};

/** Feldfehler des Servers (Plattformformat) auf Formularfelder und Textschlüssel abbilden. */
export function serverFieldErrors(
  fieldErrors: readonly { field: string; code: string }[],
): EnrollErrors {
  const errors: EnrollErrors = {};
  for (const error of fieldErrors) {
    if ((ENROLL_FIELDS as readonly string[]).includes(error.field)) {
      errors[error.field as EnrollField] ??= SERVER_CODES[error.code] ?? 'invalid';
    }
  }
  return errors;
}
