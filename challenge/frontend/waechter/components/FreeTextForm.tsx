import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { toLang } from '../api/client';
import { freeTextErrorKey, useFreeTextFeature, usePostFreeText } from '../hooks/useFreeText';

/**
 * Optionales Feld „Další potíže / Other complaints“ am Ende des Check-ins (Sitzungs-Stopp und
 * Vollformular, T-22). Der Text wird zur gerade gesendeten Antwort gespeichert; er erzeugt nie eine
 * Antwort, Stufe oder Meldung und wird der Patientin nicht bewertet. Jede geprüfte Zuordnung wird
 * danach als Folgefrage gestellt (`FollowupCards`); erst deren Antwort zählt.
 */
export function FreeTextForm({ responseId }: { responseId: string }) {
  const { t, i18n } = useTranslation();
  const feature = useFreeTextFeature();
  const post = usePostFreeText();
  const [text, setText] = useState('');
  const fieldId = useId();
  const counterId = useId();
  const errorId = useId();
  if (!feature.enabled) return null;

  const saved = post.data;
  const trimmed = text.trim();
  const locale = toLang(i18n.resolvedLanguage ?? i18n.language);

  return (
    <section
      aria-labelledby={`${fieldId}-title`}
      data-testid="free-text"
      className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-card"
    >
      <h2 id={`${fieldId}-title`} className="text-lg font-semibold">
        {t('waechter.patient.freeText.title')}
      </h2>
      {saved ? (
        <div className="space-y-3">
          <p role="status" data-testid="free-text-saved" className="text-base">
            {t('waechter.patient.freeText.saved')}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <label htmlFor={fieldId} className="block text-base">
            {t('waechter.patient.freeText.hint', { max: feature.max_length })}
          </label>
          <textarea
            id={fieldId}
            value={text}
            maxLength={feature.max_length}
            rows={4}
            lang={locale}
            aria-describedby={`${counterId}${post.isError ? ` ${errorId}` : ''}`}
            aria-invalid={post.isError || undefined}
            disabled={post.isPending}
            onChange={(event) => setText(event.target.value)}
            data-testid="free-text-input"
            className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink"
          />
          <p
            id={counterId}
            data-testid="free-text-counter"
            aria-live="polite"
            className="text-right text-base text-muted"
          >
            {t('waechter.patient.freeText.counter', {
              count: text.length,
              max: feature.max_length,
            })}
          </p>
          {post.isError ? (
            <p
              id={errorId}
              role="alert"
              data-testid="free-text-error"
              className="text-base font-semibold"
            >
              {t(`waechter.patient.freeText.errors.${freeTextErrorKey(post.error)}`)}
            </p>
          ) : null}
          <Button
            disabled={trimmed === '' || post.isPending}
            onClick={() => post.mutate({ response_id: responseId, text: trimmed, lang: locale })}
            data-testid="free-text-send"
          >
            {post.isPending
              ? t('waechter.patient.freeText.sending')
              : post.isError
                ? t('waechter.patient.freeText.retry')
                : t('waechter.patient.freeText.send')}
          </Button>
        </div>
      )}
    </section>
  );
}
