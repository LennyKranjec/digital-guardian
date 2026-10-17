import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { toLang, type FreeText, type FreeTextSuggestion } from '../api/client';
import { useFreeTexts } from '../hooks/useFreeText';
import { useServerNow } from '../hooks/useServerNow';
import { chipsOf, segmentsOf } from '../model/freetext';
import { TimeInline } from './TimeText';

function ModeBadge({ item }: { item: FreeText }) {
  const { t } = useTranslation();
  return (
    <span
      data-testid="free-text-mode"
      data-mode={item.mode}
      className="inline-flex min-h-6 items-center rounded-md border border-border-strong px-2 text-base"
    >
      {t(`waechter.clinic.freeText.modes.${item.mode}`)}
    </span>
  );
}

/** Text mit hervorgehobenen Zitaten der Vorschläge (`<mark>`; Hervorhebung nie nur durch Farbe). */
function Highlighted({ item }: { item: FreeText }) {
  return (
    <p data-testid="free-text-body" className="m-0 whitespace-pre-wrap break-words text-base">
      {segmentsOf(item.text, item.suggestions).map((segment, index) =>
        segment.suggestions.length > 0 ? (
          <mark
            key={index}
            data-testid="free-text-quote"
            className="rounded-sm bg-status-caution-bg px-0.5 font-semibold text-status-caution-fg underline decoration-2"
          >
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </p>
  );
}

/** Ein Chip „→ Průjem“; Vorschlagswert nur als Hinweis, Bestätigung nur durch die Antwort der Patientin. */
function Chip({ chip, mode }: { chip: FreeTextSuggestion; mode: FreeText['mode'] }) {
  const { t } = useTranslation();
  return (
    <li
      data-testid="free-text-chip"
      data-confirmed={chip.confirmed}
      data-source={chip.source ?? undefined}
      className="inline-flex min-h-8 flex-wrap items-center gap-x-2 rounded-full border border-border-strong px-3 text-base"
    >
      <span className="font-semibold">
        → {chip.label}
        {chip.attribute ? ` (${chip.attribute})` : ''}
      </span>
      {mode === 'live' && chip.source === 'wordlist' ? (
        <span className="text-muted" data-testid="free-text-source">
          {t('waechter.clinic.freeText.sourceWordlist')}
        </span>
      ) : null}
      {chip.proposed_value !== null ? (
        <span className="text-muted" data-testid="free-text-proposed">
          {t('waechter.clinic.freeText.proposed', { value: chip.proposed_value })}
        </span>
      ) : null}
      {chip.confirmed ? (
        <span data-testid="free-text-confirmed">
          <span aria-hidden="true">✓ </span>
          {t('waechter.clinic.freeText.confirmed')}
          {chip.answers.length > 0
            ? ` (${chip.answers.map((a) => `${a.attribute}: ${a.value ?? '–'}`).join(', ')})`
            : ''}
        </span>
      ) : (
        <span className="text-muted" data-testid="free-text-open">
          {t('waechter.clinic.freeText.unconfirmed')}
        </span>
      )}
    </li>
  );
}

function ChipGroup({
  chips,
  heading,
  mode,
}: {
  chips: FreeTextSuggestion[];
  heading: string;
  mode: FreeText['mode'];
}) {
  if (chips.length === 0) return null;
  return (
    <div className="space-y-1" data-testid="free-text-group">
      <p className="m-0 text-base text-muted">{heading}</p>
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0" data-testid="free-text-chips">
        {chips.map((chip) => (
          <Chip key={`${chip.symptom_key}:${chip.attribute ?? ''}`} chip={chip} mode={mode} />
        ))}
      </ul>
    </div>
  );
}

function FreeTextItem({ item, now, locale }: { item: FreeText; now: Date | null; locale: string }) {
  const { t } = useTranslation();
  const chips = chipsOf(item);
  const tracked = chips.filter((chip) => chip.in_questionnaire);
  const outside = chips.filter((chip) => !chip.in_questionnaire);
  return (
    <li
      data-testid="free-text-item"
      className="space-y-2 rounded-lg border border-border bg-surface p-3"
    >
      <div className="flex flex-wrap items-center gap-2 text-base">
        <TimeInline
          iso={item.created_at}
          empty="–"
          allowFuture={false}
          now={now}
          locale={locale}
          showAbsolute
        />
        <ModeBadge item={item} />
        {item.unconfirmed > 0 ? (
          <span
            data-testid="free-text-unconfirmed"
            className="inline-flex min-h-6 items-center gap-1 rounded-md border border-border-strong px-2 font-semibold"
          >
            <span aria-hidden="true">●</span>
            {t('waechter.clinic.freeTextUnconfirmed', { count: item.unconfirmed })}
          </span>
        ) : null}
      </div>
      <Highlighted item={item} />
      {chips.length > 0 ? (
        <>
          <ChipGroup
            chips={tracked}
            heading={t('waechter.clinic.freeText.suggested')}
            mode={item.mode}
          />
          <ChipGroup
            chips={outside}
            heading={t('waechter.clinic.freeText.outside')}
            mode={item.mode}
          />
        </>
      ) : (
        <p className="m-0 text-base text-muted">{t('waechter.clinic.freeText.noSuggestion')}</p>
      )}
    </li>
  );
}

/**
 * Cockpit-Abschnitt „Freitexte“ (T-22): neueste zuerst, Vorschläge als Chips „→ Průjem“ mit
 * hervorgehobenem Zitat, getrennt nach getrackten Symptomen und „außerhalb der getrackten Symptome“, mit
 * Modus, Vorschlagswert (nur Anzeige) und Bestätigung durch die Antwort der Patientin. Die Vorschläge
 * sind „KI-Vorschlag, nicht bewertet“: sie ändern weder Antworten noch Stufen noch Meldungen.
 */
export function FreeTextPanel({ patientId }: { patientId: string }) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const now = useServerNow();
  const locale = toLang(i18n.resolvedLanguage ?? i18n.language);
  const query = useFreeTexts(patientId);

  if (query.isError && query.error instanceof ApiClientError && query.error.status === 403) {
    return null;
  }
  // Solange unklar ist, ob es Freitexte gibt, und wenn keine existieren: kein Abschnitt (kein Flackern)
  if (query.isPending || (query.isSuccess && query.data.length === 0)) return null;

  return (
    <section
      aria-labelledby={titleId}
      data-testid="free-texts"
      className="space-y-2 rounded-lg border border-border bg-surface p-4 shadow-card"
    >
      <h2 id={titleId} className="m-0 text-lg font-semibold">
        {t('waechter.clinic.freeText.title')}
      </h2>
      <p className="m-0 text-base text-muted">{t('waechter.clinic.freeText.note')}</p>
      {query.isError ? (
        <p role="alert" className="m-0 text-base font-semibold">
          {t('waechter.clinic.freeText.error')}
        </p>
      ) : null}
      {query.isSuccess ? (
        <ul className="m-0 list-none space-y-2 p-0">
          {query.data.map((item) => (
            <FreeTextItem key={item.free_text_id} item={item} now={now} locale={locale} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
