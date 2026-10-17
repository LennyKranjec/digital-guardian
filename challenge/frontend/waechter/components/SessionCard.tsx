import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import type { SessionQuestion } from '../api/client';
import type { AnswerValue } from '../model/checkin';
import { QuestionGroup } from './QuestionGroup';

interface SessionCardProps {
  question: SessionQuestion;
  isSending: boolean;
  /** Schlüssel unter `waechter.patient.errors.*`, wenn das Senden fehlgeschlagen ist */
  errorKey: string | null;
  onSubmit: (value: AnswerValue) => void;
  /** Fortschritt (zwischen Frage und Aktionen) */
  progress?: ReactNode;
  /** Zurück-Pfeil (nur wenn bereits eine Antwort gegeben wurde) */
  back?: ReactNode;
}

/**
 * Eine Frage pro Karte: Antwortkacheln als Radiogruppe (≥ 44 px, Pfeiltasten wählen, ändern aber noch
 * nichts am Server), „Überspringen“ als eigene Option (`null`), „Weiter“ sendet genau diese Antwort.
 * Zurück geht nur über den Zurück-Pfeil der Seite (Server nimmt die letzte Antwort zurück, T-31),
 * denn der Server entscheidet anhand der Antworten über Folgefrage und Stopp.
 */
export function SessionCard({
  question,
  isSending,
  errorKey,
  onSubmit,
  progress,
  back,
}: SessionCardProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState<AnswerValue | undefined>(undefined);
  const heading = useRef<HTMLHeadingElement>(null);

  // neue Karte ⇒ Fokus auf die Überschrift (Screenreader lesen die Frage, Tastatur beginnt oben)
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, []);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (value !== undefined && !isSending) onSubmit(value);
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      data-testid="session-card"
      aria-labelledby="session-card-title"
      className="space-y-4 rounded-lg border border-border bg-surface p-4"
    >
      <h2
        id="session-card-title"
        ref={heading}
        tabIndex={-1}
        className="text-lg font-semibold outline-none"
      >
        {question.label}
      </h2>
      <QuestionGroup question={question} value={value} onChange={setValue} />
      {errorKey ? (
        <p role="alert" className="rounded-md border border-danger p-3 text-base font-semibold">
          {t(`waechter.patient.errors.${errorKey}`)}
        </p>
      ) : null}
      {progress}
      <div className="flex min-w-0 items-center gap-3">
        {back}
        <Button
          type="submit"
          disabled={value === undefined || isSending}
          className="min-w-0 flex-1 sm:flex-none"
        >
          {isSending ? t('waechter.patient.sending') : t('waechter.patient.session.next')}
        </Button>
      </div>
    </form>
  );
}
