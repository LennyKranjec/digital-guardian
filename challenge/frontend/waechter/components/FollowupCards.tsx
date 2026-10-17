import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { newSubmissionId, type FollowupCard, type SubmitReceipt } from '../api/client';
import { freeTextErrorKey, useAnswerFollowups, useFollowupCards } from '../hooks/useFreeText';
import type { AnswerValue } from '../model/checkin';
import { EscalationNotice } from './EscalationNotice';
import { QuestionGroup } from './QuestionGroup';

type Draft = Record<string, AnswerValue | undefined>;

/**
 * Eine Folgefrage-Karte: „Sie schrieben: ‚…‘“ plus die Standardfragen des Check-ins (gleicher Wortlaut,
 * gleiche Optionen). Erst die Antwort der Patientin zählt; der Vorschlag des Modells wird ihr nie als
 * Wert gezeigt oder vorausgewählt. Die Quittung ist die des Check-ins (bei „akut“ der Klinikhinweis).
 */
function Card({
  card,
  onDone,
}: {
  card: FollowupCard;
  onDone: (card: FollowupCard, receipt: SubmitReceipt) => void;
}) {
  const { t } = useTranslation();
  const mutation = useAnswerFollowups(card.free_text_id);
  const [draft, setDraft] = useState<Draft>({});
  const [submissionId] = useState(newSubmissionId);
  const answered = card.questions.every((q) => draft[q.attribute] !== undefined);
  return (
    <li
      data-testid="followup-card"
      data-symptom={card.symptom_key}
      data-critical={card.critical || undefined}
      className="space-y-3 rounded-lg border border-border-strong bg-surface p-4 shadow-card"
    >
      <h3 className="text-lg font-semibold">{card.label}</h3>
      <p className="text-base" data-testid="followup-quote">
        {t('waechter.patient.freeText.followup.wrote', { quote: card.quote })}
      </p>
      {card.questions.map((question) => (
        <QuestionGroup
          key={question.attribute}
          question={question}
          value={draft[question.attribute]}
          onChange={(value) => setDraft((current) => ({ ...current, [question.attribute]: value }))}
        />
      ))}
      {mutation.isError ? (
        <p role="alert" data-testid="followup-error" className="text-base font-semibold">
          {t(`waechter.patient.freeText.errors.${freeTextErrorKey(mutation.error)}`)}
        </p>
      ) : null}
      <Button
        disabled={!answered || mutation.isPending}
        data-testid="followup-send"
        onClick={() =>
          mutation.mutate(
            {
              client_submission_id: submissionId,
              answers: card.questions.map((q) => ({
                symptom_key: card.symptom_key,
                attribute: q.attribute,
                value: draft[q.attribute] ?? null,
              })),
            },
            { onSuccess: (receipt) => onDone(card, receipt) },
          )
        }
      >
        {mutation.isPending
          ? t('waechter.patient.freeText.sending')
          : mutation.isError
            ? t('waechter.patient.freeText.retry')
            : t('waechter.patient.freeText.followup.send')}
      </Button>
    </li>
  );
}

/** Beantwortete Karte: bleibt stehen (mit dem Akut-Hinweis der Quittung), auch wenn der Server sie nicht mehr listet. */
function DoneCard({ card, receipt }: { card: FollowupCard; receipt: SubmitReceipt }) {
  const { t } = useTranslation();
  return (
    <li
      data-testid="followup-done"
      data-symptom={card.symptom_key}
      className="space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      {receipt.escalation ? <EscalationNotice escalation={receipt.escalation} /> : null}
      <p role="status" className="text-base">
        {t('waechter.patient.freeText.followup.saved', { label: card.label })}
      </p>
    </li>
  );
}

/**
 * Offene Folgefragen zu Freitexten (T-22), kritische Symptome zuerst. Erscheint nach dem Speichern
 * eines Freitexts und bei jedem weiteren Check-in, solange Fragen offen sind; ohne offene Fragen oder bei
 * abgeschaltetem Freitext erscheint nichts.
 */
export function FollowupCards() {
  const { t } = useTranslation();
  const query = useFollowupCards();
  const [done, setDone] = useState<Record<string, { card: FollowupCard; receipt: SubmitReceipt }>>(
    {},
  );
  const keyOf = (card: FollowupCard) => `${card.free_text_id}:${card.symptom_key}`;
  const open = (query.data ?? []).filter((card) => done[keyOf(card)] === undefined);
  const finished = Object.values(done);
  if (open.length === 0 && finished.length === 0) return null;
  return (
    <section aria-labelledby="followup-title" data-testid="followups" className="space-y-3">
      <h2 id="followup-title" className="text-lg font-semibold">
        {t('waechter.patient.freeText.followup.title')}
      </h2>
      {open.length > 0 ? (
        <p className="text-base">{t('waechter.patient.freeText.followup.intro')}</p>
      ) : null}
      <ul className="m-0 list-none space-y-3 p-0">
        {finished.map(({ card, receipt }) => (
          <DoneCard key={keyOf(card)} card={card} receipt={receipt} />
        ))}
        {open.map((card) => (
          <Card
            key={keyOf(card)}
            card={card}
            onDone={(finishedCard, receipt) =>
              setDone((current) => ({
                ...current,
                [keyOf(finishedCard)]: { card: finishedCard, receipt },
              }))
            }
          />
        ))}
      </ul>
    </section>
  );
}
