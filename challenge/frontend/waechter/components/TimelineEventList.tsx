import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { buildEvents, alertFactId, type TimelineEvent } from '../model/timeline';
import { formatAbsolute, formatDay } from '../model/time';
import type { Timeline } from '../api/client';
import { FactChip } from './FactChip';

interface TimelineEventListProps {
  timeline: Timeline;
  locale: string;
  onOpenFact: (factId: string) => void;
  /** Druckansicht: ohne Beleg-Chips (nur Text) */
  plain?: boolean;
}

/**
 * Zugängliche Alternative zur Grafik: dieselben Ereignisse als Tabelle (Datum, Ereignis, Details),
 * zeitlich aufsteigend – Antworten, Meldungen, Quittierungen, Arztaufnahmen, Termine, Tage ohne
 * Eingabe. Nichts liegt nur grafisch vor.
 */
export function TimelineEventList({
  timeline,
  locale,
  onOpenFact,
  plain = false,
}: TimelineEventListProps) {
  const { t } = useTranslation();
  const events = useMemo(() => buildEvents(timeline), [timeline]);
  const level = (value: 'red' | 'yellow' | 'grey') => t(`waechter.clinic.timeline.levels.${value}`);
  const attributeName = (attribute: string) =>
    t(`waechter.clinic.since.attr.${attribute}`, { defaultValue: attribute });
  const iso = (ms: number) => new Date(ms).toISOString();

  function describe(event: TimelineEvent): {
    kind: string;
    details: string;
    factId?: string | null;
  } {
    switch (event.kind) {
      case 'response':
        return {
          kind: t('waechter.clinic.timeline.events.kinds.response'),
          details: event.values
            .map(
              (entry) =>
                `${entry.label} (${attributeName(entry.attribute)}): ${
                  entry.value === null ? t('waechter.clinic.timeline.events.noValue') : entry.value
                }`,
            )
            .join(' · '),
        };
      case 'alert':
        return {
          kind: t('waechter.clinic.timeline.events.kinds.alert', {
            level: level(event.alert.level),
          }),
          details: `${event.alert.headline ?? event.alert.rule_id} (${event.alert.rule_id})`,
          factId: alertFactId(event.alert),
        };
      case 'acknowledged': {
        const ack = event.alert.acknowledgement;
        const parts = [
          event.alert.headline ?? event.alert.rule_id,
          ack?.decision ? t(`waechter.clinic.timeline.events.decision.${ack.decision}`) : null,
          ack?.by ?? null,
          ack?.note ?? null,
        ].filter((part): part is string => Boolean(part));
        return {
          kind: t('waechter.clinic.timeline.events.kinds.acknowledged'),
          details: parts.join(' · '),
        };
      }
      case 'assessment':
        return {
          kind: t('waechter.clinic.timeline.events.kinds.assessment'),
          details: event.assessment.items
            .map((item) =>
              t('waechter.clinic.timeline.events.gradeItem', {
                term: item.term_en ?? item.ctcae_term_id,
                grade: item.grade,
              }),
            )
            .join(' · '),
          factId: event.assessment.fact_id,
        };
      case 'visit':
        return {
          kind: t('waechter.clinic.timeline.events.kinds.visit', {
            kind: t(`waechter.clinic.timeline.visitKind.${event.visitKind}`),
          }),
          details: '',
          factId: event.factId,
        };
      case 'missing':
        return {
          kind: t('waechter.clinic.timeline.events.kinds.missing'),
          details: t('waechter.clinic.timeline.events.missingDay'),
        };
      case 'therapy':
        return {
          kind: t('waechter.clinic.timeline.events.kinds.therapy'),
          details: event.label,
          factId: event.factId,
        };
    }
  }

  return (
    <section aria-labelledby="events-title" className="space-y-2" data-testid="timeline-events">
      <h3 id="events-title" className="text-base font-semibold">
        {t('waechter.clinic.timeline.events.title')}
      </h3>
      {events.length === 0 ? (
        <p className="text-base text-muted">{t('waechter.clinic.timeline.events.empty')}</p>
      ) : (
        <table className="block w-full border-collapse sm:table sm:table-fixed">
          <caption className="block pb-2 text-left text-base text-muted sm:table-caption">
            {t('waechter.clinic.timeline.events.caption')}
          </caption>
          <thead className="sr-only sm:not-sr-only sm:table-header-group">
            <tr className="border-b border-border-strong">
              <th
                scope="col"
                className="w-[34%] px-2 py-2 text-left text-base font-semibold text-muted sm:w-1/4"
              >
                {t('waechter.clinic.timeline.events.date')}
              </th>
              <th
                scope="col"
                className="w-[26%] px-2 py-2 text-left text-base font-semibold text-muted sm:w-1/4"
              >
                {t('waechter.clinic.timeline.events.event')}
              </th>
              <th scope="col" className="px-2 py-2 text-left text-base font-semibold text-muted">
                {t('waechter.clinic.timeline.events.details')}
              </th>
            </tr>
          </thead>
          <tbody className="block sm:table-row-group">
            {events.map((event, index) => {
              const entry = describe(event);
              return (
                <tr
                  key={`${event.kind}-${event.ms}-${index}`}
                  data-event={event.kind}
                  className="mb-2 block rounded-md border border-border p-2 sm:mb-0 sm:table-row sm:rounded-none sm:border-0 sm:border-b sm:p-0"
                >
                  <td
                    data-label={t('waechter.clinic.timeline.events.date')}
                    className="block break-words px-2 py-1 text-left align-top text-base before:mr-1 before:font-semibold before:text-muted before:content-[attr(data-label)] sm:table-cell sm:py-2 sm:before:content-none"
                  >
                    {event.kind === 'missing'
                      ? formatDay(event.ms, locale)
                      : formatAbsolute(iso(event.ms), locale)}
                  </td>
                  <td
                    data-label={t('waechter.clinic.timeline.events.event')}
                    className="block break-words px-2 py-1 text-left align-top text-base before:mr-1 before:font-semibold before:text-muted before:content-[attr(data-label)] sm:table-cell sm:py-2 sm:before:content-none font-semibold"
                  >
                    {entry.kind}
                  </td>
                  <td
                    data-label={t('waechter.clinic.timeline.events.details')}
                    className="block break-words px-2 py-1 text-left align-top text-base before:mr-1 before:font-semibold before:text-muted before:content-[attr(data-label)] sm:table-cell sm:py-2 sm:before:content-none"
                  >
                    <span className="block">{entry.details}</span>
                    {entry.factId && !plain ? (
                      <span className="mt-1 inline-block">
                        <FactChip factId={entry.factId} onOpen={onOpenFact} />
                      </span>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
