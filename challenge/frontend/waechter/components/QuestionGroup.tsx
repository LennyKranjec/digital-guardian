import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import type { QuestionnaireQuestion } from '../api/client';
import type { AnswerValue } from '../model/checkin';

const TILE =
  'flex min-h-11 w-full min-w-0 cursor-pointer items-center gap-3 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink hover:bg-sunken has-[:checked]:border-accent has-[:checked]:bg-accent-subtle has-[:checked]:text-accent-subtle-ink has-[:checked]:ring-2 has-[:checked]:ring-accent has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2';
const SKIP_TILE = `${TILE} border-dashed`;
const RADIO = 'size-5 shrink-0';

interface QuestionGroupProps {
  question: QuestionnaireQuestion;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
}

/**
 * Eine Frage als Radiogruppe mit großen Kacheln (≥ 44 px). Der gewählte Zustand ist am gefüllten
 * Radiopunkt und am Rahmen erkennbar, nie nur an der Farbe. „Überspringen“ ist eine eigene Option
 * (`null`); ohne Wahl bleibt die Frage unbeantwortet.
 */
export function QuestionGroup({ question, value, onChange }: QuestionGroupProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const name = useId();

  return (
    <div role="radiogroup" aria-labelledby={labelId} className="space-y-2">
      <p id={labelId} className="text-base font-semibold">
        {question.text}
      </p>
      <div className="grid grid-cols-1 gap-2">
        {question.options.map((option) => (
          <label key={option.value} className={TILE}>
            <input
              type="radio"
              name={name}
              className={RADIO}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span className="min-w-0 break-words">{option.label}</span>
          </label>
        ))}
        <label className={SKIP_TILE}>
          <input
            type="radio"
            name={name}
            className={RADIO}
            checked={value === null}
            onChange={() => onChange(null)}
          />
          <span className="min-w-0 break-words">{t('waechter.patient.skip')}</span>
        </label>
      </div>
    </div>
  );
}
