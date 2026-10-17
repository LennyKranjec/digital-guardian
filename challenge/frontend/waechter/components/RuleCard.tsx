import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { localized, type ConfigRule, type Lang } from '../api/client';
import { parseParam, type RuleDraft } from '../model/settings';
import { LevelBadge } from './LevelBadge';

interface RuleCardProps {
  rule: ConfigRule;
  draft: RuleDraft;
  lang: Lang;
  /** nur Administration darf ändern; Ärztinnen sehen dieselben Werte schreibgeschützt */
  editable: boolean;
  /** Server- und Eingabefehler dieser Regel */
  errors: readonly string[];
  onChange: (draft: RuleDraft) => void;
}

/**
 * Eine Regel der Konfiguration: ID, Art, Stufe, aktiv, Parameter (mit Einheit und Erklärung),
 * Begründung und Quelle. Änderungen betreffen nur Aktivierung und Parameter.
 */
export function RuleCard({ rule, draft, lang, editable, errors, onChange }: RuleCardProps) {
  const { t } = useTranslation();
  const activeId = useId();
  const params = Object.entries(rule.params);
  const rationale = localized(rule.rationale, lang);

  return (
    <article
      data-testid="rule-card"
      data-rule={rule.id}
      aria-labelledby={`${activeId}-title`}
      className="space-y-3 rounded-lg border border-border bg-surface p-4"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h3 id={`${activeId}-title`} className="text-lg font-semibold">
          {rule.id}
        </h3>
        <LevelBadge level={rule.level} />
        <span className="text-base">{t(`waechter.clinic.alerts.kind.${rule.kind}`)}</span>
        {editable ? (
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-base font-semibold has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2">
            <input
              type="checkbox"
              className="size-5"
              checked={draft.enabled}
              onChange={(event) => onChange({ ...draft, enabled: event.target.checked })}
            />
            {t('waechter.clinic.settings.active')}
          </label>
        ) : (
          <span className="text-base font-semibold" data-testid="rule-active">
            {draft.enabled
              ? t('waechter.clinic.settings.active')
              : t('waechter.clinic.settings.inactive')}
          </span>
        )}
      </div>

      <dl className="m-0 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {params.map(([key]) => {
          const label = t(`waechter.clinic.alerts.paramNames.${key}`, { defaultValue: key });
          const unit = t(`waechter.clinic.settings.paramUnit.${key}`, { defaultValue: '' });
          const hint = t(`waechter.clinic.settings.paramHint.${key}`, { defaultValue: '' });
          const text = draft.params[key] ?? '';
          const invalid = parseParam(text) === null;
          const inputId = `${activeId}-${key}`;
          return (
            <div key={key} className="min-w-0 space-y-1">
              <dt>
                <label htmlFor={inputId} className="text-base font-semibold">
                  {label}
                  {unit ? ` (${unit})` : ''}
                </label>
              </dt>
              <dd className="m-0 space-y-1">
                {editable ? (
                  <input
                    id={inputId}
                    type="text"
                    inputMode="decimal"
                    value={text}
                    aria-invalid={invalid}
                    aria-describedby={hint ? `${inputId}-hint` : undefined}
                    onChange={(event) =>
                      onChange({ ...draft, params: { ...draft.params, [key]: event.target.value } })
                    }
                    className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink aria-[invalid=true]:border-danger"
                  />
                ) : (
                  <output id={inputId} className="block text-base">
                    {text}
                  </output>
                )}
                {hint ? (
                  <p id={`${inputId}-hint`} className="text-base text-muted">
                    {hint}
                  </p>
                ) : null}
                {editable && invalid ? (
                  <p role="alert" className="text-base font-semibold">
                    {t('waechter.clinic.settings.invalidNumber')}
                  </p>
                ) : null}
              </dd>
            </div>
          );
        })}
      </dl>

      {rationale ? <p className="break-words text-base">{rationale}</p> : null}
      {rule.source_id ? (
        <p className="text-base text-muted">
          {t('waechter.clinic.settings.source', { id: rule.source_id })}
        </p>
      ) : null}
      {errors.length > 0 ? (
        <ul
          role="alert"
          data-testid="rule-errors"
          className="m-0 list-none space-y-1 rounded-md border border-danger p-3 text-base font-semibold"
        >
          {errors.map((message) => (
            <li key={message}>{t('waechter.clinic.assess.errors.fieldError', { message })}</li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
