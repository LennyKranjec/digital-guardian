import type { Questionnaire, QuestionnaireQuestion, SubmitAnswer } from '../api/client';

/**
 * Reine Check-in-Logik (keine UI): Antwortstand, Fortschritt, Absende-Nutzlast.
 * `undefined` = noch nicht beantwortet · `null` = bewusst übersprungen · Zahl = gewählter Wert.
 */

export type AnswerValue = number | null;
export type AnswerMap = Readonly<Record<string, AnswerValue>>;

export const answerKey = (symptomKey: string, attribute: string): string =>
  `${symptomKey}::${attribute}`;

export interface FlatQuestion {
  symptomKey: string;
  question: QuestionnaireQuestion;
  key: string;
}

export function flattenQuestions(questionnaire: Questionnaire): FlatQuestion[] {
  return questionnaire.items.flatMap((item) =>
    item.questions.map((question) => ({
      symptomKey: item.symptom_key,
      question,
      key: answerKey(item.symptom_key, question.attribute),
    })),
  );
}

export interface Progress {
  total: number;
  answered: number;
  skipped: number;
}

export function progressOf(questionnaire: Questionnaire, answers: AnswerMap): Progress {
  const questions = flattenQuestions(questionnaire);
  let answered = 0;
  let skipped = 0;
  for (const { key } of questions) {
    const value = answers[key];
    if (typeof value === 'number') answered += 1;
    else if (value === null) skipped += 1;
  }
  return { total: questions.length, answered, skipped };
}

/** Jede Frage wird gesendet; nicht beantwortete gelten wie „übersprungen“ (`null`, nie imputiert). */
export function buildAnswers(questionnaire: Questionnaire, answers: AnswerMap): SubmitAnswer[] {
  return flattenQuestions(questionnaire).map(({ symptomKey, question, key }) => ({
    symptom_key: symptomKey,
    attribute: question.attribute,
    value: answers[key] ?? null,
  }));
}

/**
 * Hält `client_submission_id` stabil, solange die Nutzlast unverändert bleibt (Wiederholung nach
 * Netzfehler ⇒ dieselbe ID, Idempotenz laut Vertrag). Ändert die Patientin Antworten, entsteht eine
 * neue ID – sonst käme 409 `idempotency_conflict`.
 */
export interface SubmissionIdentity {
  id: string;
  fingerprint: string;
}

export function fingerprintOf(questionnaireId: string, answers: readonly SubmitAnswer[]): string {
  return JSON.stringify([questionnaireId, answers]);
}

export function resolveSubmissionId(
  previous: SubmissionIdentity | null,
  fingerprint: string,
  newId: () => string,
): SubmissionIdentity {
  return previous?.fingerprint === fingerprint ? previous : { id: newId(), fingerprint };
}
