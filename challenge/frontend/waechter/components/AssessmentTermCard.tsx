import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { ATTRIBUTIONS, NOTE_MAX_LENGTH, type Attribution, type TemplateTerm } from '../api/client';
import { availableGrades, parseHintKey, type TermDraft } from '../model/assessment';
import { FreeTextMentions } from './FreeTextMentions';

interface AssessmentTermCardProps {
  term: TemplateTerm;
  /** Patientin und Sprache für „Patientin schrieb …“ (Freitext-Zitate, nur Anzeige) */
  patientId?: string;
  locale?: string;
  draft: TermDraft;
  errors: readonly string[];
  onChange: (draft: TermDraft) => void;
}

const TILE =
  'flex min-h-11 w-full min-w-0 cursor-pointer items-start gap-3 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink hover:bg-sunken has-[:checked]:border-accent has-[:checked]:bg-accent-subtle has-[:checked]:text-accent-subtle-ink has-[:checked]:ring-2 has-[:checked]:ring-accent has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2';

/**
 * Eine Begriffskarte der CTCAE-Aufnahme. Angeboten werden nur Grad 0 (nicht vorhanden) und die in
 * CTCAE definierten Grade mit ihrem Originaltext (englisch). Der PRO-Verlauf steht daneben nur als
 * Hinweis – es gibt keine Vorauswahl und keinen Gradvorschlag.
 */
export function AssessmentTermCard({
  term,
  patientId,
  locale = 'cs',
  draft,
  errors,
  onChange,
}: AssessmentTermCardProps) {
  const { t } = useTranslation();
  const name = useId();
  const attributionId = useId();
  const noteId = useId();
  const counterId = useId();
  const grades = availableGrades(term);
  const hint = Object.entries(term.pro_hint ?? {});
  const attributeName = (attribute: string) =>
    t(`waechter.clinic.since.attr.${attribute}`, { defaultValue: attribute });

  return (
    <fieldset
      data-testid="term-card"
      data-term={term.ctcae_term_id}
      className="m-0 min-w-0 space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      <legend className="px-1 text-lg font-semibold">
        {term.term_en}
        {term.label && term.label !== term.term_en ? ` · ${term.label}` : ''}
      </legend>
      <p className="text-base text-muted">
        {t('waechter.clinic.assess.meddra', { code: term.meddra_code })}
      </p>

      <div
        className="space-y-1 rounded-md border border-dashed border-border-strong p-3"
        data-testid="pro-hint"
      >
        <p className="text-base font-semibold">{t('waechter.clinic.assess.hintTitle')}</p>
        {hint.length > 0 ? (
          <ul className="m-0 list-none space-y-0 p-0 text-base">
            {hint.map(([key, value]) => {
              const parsed = parseHintKey(key);
              const base = parsed.attribute ? attributeName(parsed.attribute) : key;
              // Begriffe mit mehreren Symptomen: Symptom voranstellen, sonst genügt das Merkmal
              const named =
                parsed.symptom && term.symptom_keys.length > 1
                  ? `${parsed.symptom}: ${base}`
                  : base;
              const label =
                parsed.attribute && parsed.stat
                  ? t(`waechter.clinic.assess.hintStat.${parsed.stat}`, { name: named })
                  : named;
              return (
                <li key={key}>
                  {label}: {value === null ? t('waechter.clinic.since.noValue') : value}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-base text-muted">{t('waechter.clinic.assess.hintNone')}</p>
        )}
        <p className="text-base text-muted">
          {term.last_grade === null || term.last_grade === undefined
            ? t('waechter.clinic.assess.noLastGrade')
            : t('waechter.clinic.assess.lastGrade', { grade: term.last_grade })}
        </p>
        <p className="text-base text-muted">{t('waechter.clinic.assess.hintNote')}</p>
        {patientId ? (
          <FreeTextMentions patientId={patientId} symptomKeys={term.symptom_keys} locale={locale} />
        ) : null}
      </div>

      <div role="radiogroup" aria-label={term.term_en} className="grid grid-cols-1 gap-2">
        <label className={TILE}>
          <input
            type="radio"
            name={name}
            className="mt-0.5 size-5 shrink-0"
            checked={draft.grade === null}
            onChange={() => onChange({ ...draft, grade: null })}
          />
          <span className="min-w-0 break-words">{t('waechter.clinic.assess.gradeNone')}</span>
        </label>
        {grades.map((option) => (
          <label key={option.grade} className={TILE}>
            <input
              type="radio"
              name={name}
              className="mt-0.5 size-5 shrink-0"
              checked={draft.grade === option.grade}
              onChange={() => onChange({ ...draft, grade: option.grade })}
            />
            <span className="min-w-0 break-words">
              <span className="block font-semibold">
                {option.grade === 0
                  ? t('waechter.clinic.assess.gradeZero')
                  : t('waechter.clinic.assess.gradeLabel', { grade: option.grade })}
              </span>
              {option.text ? (
                <span lang="en" className="block">
                  {option.text}
                </span>
              ) : null}
            </span>
          </label>
        ))}
      </div>

      {draft.grade !== null ? (
        <div className="space-y-3">
          <div className="space-y-1">
            <label htmlFor={attributionId} className="block text-base font-semibold">
              {t('waechter.clinic.assess.attribution')}
            </label>
            <select
              id={attributionId}
              value={draft.attribution}
              onChange={(event) =>
                onChange({ ...draft, attribution: event.target.value as Attribution })
              }
              className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink"
            >
              {ATTRIBUTIONS.map((option) => (
                <option key={option} value={option}>
                  {t(`waechter.clinic.assess.attributions.${option}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label htmlFor={noteId} className="block text-base font-semibold">
              {t('waechter.clinic.assess.note')}
            </label>
            <textarea
              id={noteId}
              value={draft.note}
              maxLength={NOTE_MAX_LENGTH}
              rows={2}
              aria-describedby={counterId}
              onChange={(event) => onChange({ ...draft, note: event.target.value })}
              className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink"
            />
            <p id={counterId} className="text-right text-base text-muted">
              {t('waechter.clinic.ack.counter', { count: draft.note.length, max: NOTE_MAX_LENGTH })}
            </p>
          </div>
        </div>
      ) : null}

      {errors.length > 0 ? (
        <ul
          role="alert"
          data-testid="term-errors"
          className="m-0 list-none space-y-1 rounded-md border border-danger p-3 text-base font-semibold"
        >
          {errors.map((message) => (
            <li key={message}>{t('waechter.clinic.assess.errors.fieldError', { message })}</li>
          ))}
        </ul>
      ) : null}
    </fieldset>
  );
}
