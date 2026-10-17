import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import type { Summary, TrackedSymptom } from '../api/client';
import { formatAbsolute } from '../model/time';
import { FactChip } from './FactChip';

/** So viele Sätze stehen sofort sichtbar, der Rest hinter „Weitere Sätze“ (alle bleiben im DOM). */
export const VISIBLE_SENTENCES = 2;

type Sentence = Summary['sentences'][number];

interface SummaryPanelProps {
  summary: Summary | null | undefined;
  locale: string;
  isGenerating: boolean;
  hasError: boolean;
  onGenerate: () => void;
  onOpenFact: (factId: string) => void;
  /** CTCAE-Subraum des aktuellen Fragebogens (T-25), steht am Kopf der Kurzfassung */
  tracked?: readonly TrackedSymptom[] | null;
}

/**
 * KI-Kurzfassung (Entscheidungsunterstützung, Entwurf): jeder Satz mit Beleg-Chips, Klick öffnet
 * den Beleg. Sichtbar bleiben Generator, Modus, Zeit und die Zahl verworfener Sätze; Themen ohne
 * Daten stehen als „unbekannt“. Ohne Kurzfassung: Knopf zum Erzeugen.
 */
export function SummaryPanel({
  summary,
  locale,
  isGenerating,
  hasError,
  onGenerate,
  onOpenFact,
}: SummaryPanelProps) {
  const { t } = useTranslation();
  const draftNote = t('waechter.clinic.summary.draft');
  const sentences = summary?.sentences ?? [];
  const first = sentences.slice(0, VISIBLE_SENTENCES);
  const rest = sentences.slice(VISIBLE_SENTENCES);

  function renderSentences(list: readonly Sentence[], start: number) {
    return (
      <ol start={start} className="m-0 list-decimal space-y-2 pl-6">
        {list.map((sentence, index) => (
          <li key={`${start + index}-${sentence.text}`} data-testid="summary-sentence">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <p className="m-0 line-clamp-2 min-w-0 flex-1 basis-56 break-words text-base">
                {sentence.text}
              </p>
              {sentence.refs.length > 0 ? (
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                  {sentence.refs.map((ref) => (
                    <li key={ref}>
                      <FactChip factId={ref} onOpen={onOpenFact} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            {sentence.verified ? null : (
              <p className="m-0 text-base font-semibold">
                {t('waechter.clinic.summary.unverified')}
              </p>
            )}
          </li>
        ))}
      </ol>
    );
  }

  return (
    <section
      aria-labelledby="summary-title"
      data-testid="summary-panel"
      className="space-y-2 rounded-lg border border-border bg-surface p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="summary-title" className="m-0 text-lg font-semibold">
          {t('waechter.clinic.summary.title')}
        </h2>
        <Button
          variant={summary ? 'secondary' : 'primary'}
          disabled={isGenerating}
          onClick={onGenerate}
        >
          {isGenerating
            ? t('waechter.clinic.summary.generating')
            : summary
              ? t('waechter.clinic.summary.regenerate')
              : t('waechter.clinic.summary.generate')}
        </Button>
      </div>
      {summary ? (
        <>
          <p className="m-0 rounded-md border border-border-strong px-2 py-1 text-base font-semibold">
            {t(`waechter.${summary.disclaimer_key}`, { defaultValue: draftNote })}
          </p>
          <dl className="m-0 flex flex-wrap gap-x-4 gap-y-0 text-base">
            <div className="flex gap-1">
              <dt className="text-muted">{t('waechter.clinic.summary.generator')}</dt>
              <dd className="m-0 break-words">{summary.generator}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-muted">{t('waechter.clinic.summary.mode')}</dt>
              <dd className="m-0">{t(`waechter.clinic.summary.modes.${summary.mode}`)}</dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-muted">{t('waechter.clinic.summary.generatedAt')}</dt>
              <dd className="m-0">
                <time dateTime={summary.generated_at}>
                  {formatAbsolute(summary.generated_at, locale)}
                </time>
              </dd>
            </div>
            <div className="flex gap-1">
              <dt className="text-muted">{t('waechter.clinic.summary.droppedLabel')}</dt>
              <dd className="m-0" data-testid="dropped-sentences">
                {summary.dropped_sentences}
              </dd>
            </div>
          </dl>
          {sentences.length > 0 ? (
            <>
              {renderSentences(first, 1)}
              {rest.length > 0 ? (
                <details data-testid="summary-more">
                  <summary className="inline-flex min-h-11 cursor-pointer items-center text-base font-semibold underline">
                    {t('waechter.clinic.summary.moreSentences', { count: rest.length })}
                  </summary>
                  {renderSentences(rest, VISIBLE_SENTENCES + 1)}
                </details>
              ) : null}
            </>
          ) : (
            <p className="m-0 text-base text-muted">{t('waechter.clinic.summary.noSentences')}</p>
          )}
          {summary.unknown_topics && summary.unknown_topics.length > 0 ? (
            <div
              data-testid="unknown-topics"
              className="flex flex-wrap items-baseline gap-x-2 text-base"
            >
              <p className="m-0 font-semibold">{t('waechter.clinic.summary.unknown')}</p>
              <ul className="m-0 flex list-none flex-wrap gap-x-3 p-0">
                {summary.unknown_topics.map((topic) => (
                  <li key={topic}>{topic}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : (
        <>
          <p className="m-0 rounded-md border border-border-strong px-2 py-1 text-base font-semibold">
            {draftNote}
          </p>
          <p className="m-0 text-base text-muted">{t('waechter.clinic.summary.none')}</p>
        </>
      )}
      {hasError ? (
        <p role="alert" className="m-0 rounded-md border border-danger p-3 text-base font-semibold">
          {t('waechter.clinic.summary.error')}
        </p>
      ) : null}
    </section>
  );
}
