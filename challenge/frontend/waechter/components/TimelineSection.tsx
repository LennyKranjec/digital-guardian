import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  EmptyState,
  ErrorState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { useElementWidth, useRules, useTimeline } from '../hooks/useTimeline';
import {
  RANGE_MODES,
  domainOf,
  orderSeries,
  thresholdsFor,
  timelineRange,
  type RangeMode,
} from '../model/timeline';
import { TimelineAxis } from './TimelineAxis';
import { TimelineChart } from './TimelineChart';
import { TimelineEventList } from './TimelineEventList';
import { TimelineLegend } from './TimelineLegend';

interface TimelineSectionProps {
  patientId: string;
  lastVisitAt: string | null | undefined;
  /** Serverzeit (DR-009); ohne sie sind 14/28 Tage nicht wählbar */
  serverNow: Date | null;
  locale: string;
  onOpenFact: (factId: string) => void;
}

/**
 * Abschnitt „Verlauf“: vollständige Historie aller Metriken (Small Multiples auf gemeinsamer
 * Zeitachse), Meldungen, Lücken, Termine und Aufnahmen; darunter dieselben Ereignisse als Tabelle.
 */
export function TimelineSection({
  patientId,
  lastVisitAt,
  serverNow,
  locale,
  onOpenFact,
}: TimelineSectionProps) {
  const { t } = useTranslation();
  const context = { serverNow, lastVisitAt };
  const [mode, setMode] = useState<RangeMode>(() =>
    timelineRange('visit', context) ? 'visit' : 'all',
  );
  const range = timelineRange(mode, context);
  const query = useTimeline(patientId, range);
  const rules = useRules();
  const { ref, width } = useElementWidth<HTMLDivElement>();

  const timeline = query.data;
  const domain = useMemo(() => (timeline ? domainOf(timeline) : null), [timeline]);
  const ordered = useMemo(
    () => (timeline ? orderSeries(timeline.series, timeline.alerts) : []),
    [timeline],
  );
  const thresholdSource = rules.data
    ? t('waechter.clinic.timeline.thresholdSource', { version: rules.data.version })
    : null;
  const hasContent =
    timeline !== undefined &&
    (timeline.series.length > 0 ||
      timeline.alerts.length > 0 ||
      timeline.visits.length > 0 ||
      timeline.assessments.length > 0 ||
      timeline.missing_days.length > 0);
  const unavailable = RANGE_MODES.filter((option) => timelineRange(option, context) === null);

  return (
    <section
      id="timeline-full"
      aria-labelledby="timeline-title"
      className="space-y-4"
      data-testid="timeline-section"
    >
      <h2 id="timeline-title" tabIndex={-1} className="text-lg font-semibold">
        {t('waechter.clinic.timeline.title')}
      </h2>
      <fieldset className="m-0 min-w-0 space-y-2 border-0 p-0">
        <legend className="text-base font-semibold">{t('waechter.clinic.timeline.range')}</legend>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
          {RANGE_MODES.map((option) => (
            <label
              key={option}
              className="flex min-h-11 min-w-0 cursor-pointer items-center gap-3 rounded-md border border-border-strong bg-surface px-3 py-2 text-base has-[:checked]:border-accent has-[:checked]:bg-accent-subtle has-[:checked]:ring-2 has-[:checked]:ring-accent has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60 has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2"
            >
              <input
                type="radio"
                name="timeline-range"
                className="size-5 shrink-0"
                checked={mode === option}
                disabled={unavailable.includes(option)}
                onChange={() => setMode(option)}
              />
              <span className="min-w-0 break-words">
                {t(`waechter.clinic.timeline.modes.${option}`)}
              </span>
            </label>
          ))}
        </div>
        {unavailable.some((option) => option === '14d' || option === '28d') ? (
          <p className="text-base text-muted">{t('waechter.clinic.timeline.rangeUnavailable')}</p>
        ) : null}
      </fieldset>

      <div ref={ref} className="min-w-0 space-y-4">
        {query.isPending && range !== null ? <SkeletonBlock lines={5} /> : null}
        {query.isError ? <ErrorState onRetry={() => void query.refetch()} /> : null}
        {timeline && (!domain || !hasContent) ? (
          <EmptyState
            title={t('waechter.clinic.timeline.emptyTitle')}
            body={t('waechter.clinic.timeline.emptyBody')}
          />
        ) : null}
        {timeline && domain && hasContent ? (
          <div className="space-y-4" data-testid="timeline-body">
            <TimelineLegend thresholdSource={thresholdSource} />
            <TimelineAxis domain={domain} width={width} locale={locale} />
            <TimelineChart
              title={t('waechter.clinic.timeline.laneTitle')}
              timeline={timeline}
              domain={domain}
              width={width}
              locale={locale}
              onOpenFact={onOpenFact}
            />
            {ordered.map((series) => (
              <TimelineChart
                key={`${series.symptom_key}-${series.attribute}`}
                series={series}
                title={`${series.label} · ${t(`waechter.clinic.since.attr.${series.attribute}`, { defaultValue: series.attribute })}`}
                timeline={timeline}
                domain={domain}
                width={width}
                thresholds={rules.data ? thresholdsFor(series, rules.data.rules) : []}
                locale={locale}
                onOpenFact={onOpenFact}
              />
            ))}
            <TimelineAxis domain={domain} width={width} locale={locale} />
            <TimelineEventList timeline={timeline} locale={locale} onOpenFact={onOpenFact} />
          </div>
        ) : null}
      </div>
    </section>
  );
}
