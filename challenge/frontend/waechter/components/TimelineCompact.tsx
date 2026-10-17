import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

import { SkeletonBlock } from '../../../../platform/frontend/src/shared/ui/StateViews';
import type { Series } from '../api/client';
import { useTimeline } from '../hooks/useTimeline';
import {
  domainOf,
  lastValue,
  pickCompactSeries,
  scaleX,
  scaleY,
  timedPoints,
  timelineRange,
  valueRuns,
  type Domain,
} from '../model/timeline';

/** Id des vollständigen Verlaufs (Sprungziel der kompakten Leiste). */
export const TIMELINE_FULL_ID = 'timeline-full';

const WIDTH = 72;
const HEIGHT = 32;

function Sparkline({
  series,
  domain,
  alertTimes,
}: {
  series: Series;
  domain: Domain;
  alertTimes: number[];
}) {
  const x = scaleX(domain, 4, WIDTH - 4);
  const y = scaleY(5, HEIGHT - 4);
  const runs = valueRuns(timedPoints(series.points));
  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
      data-testid="sparkline"
    >
      <line
        x1={4}
        x2={WIDTH - 4}
        y1={HEIGHT - 4}
        y2={HEIGHT - 4}
        className="stroke-current text-border"
        strokeWidth={1}
      />
      <g className="stroke-current text-accent" fill="none" strokeWidth={2} strokeLinejoin="round">
        {runs.map((run, index) =>
          run.length > 1 ? (
            <polyline
              key={index}
              data-testid="spark-run"
              points={run.map((point) => `${x(point.ms)},${y(point.value)}`).join(' ')}
            />
          ) : (
            <circle
              key={index}
              data-testid="spark-run"
              cx={x(run[0]?.ms ?? domain.from)}
              cy={y(run[0]?.value ?? 0)}
              r={2.5}
            />
          ),
        )}
      </g>
      {alertTimes.map((ms) => (
        <path
          key={ms}
          data-testid="spark-alert"
          d={`M${x(ms)} 1 l4 4 -4 4 -4 -4 z`}
          className="fill-current text-ink"
        />
      ))}
    </svg>
  );
}

/**
 * Kompakte Verlaufsleiste unter Lage und Meldungen: je Symptom mit offener Meldung (sonst die
 * ersten drei) eine Sparkline 0–4 aus denselben Verlaufsdaten wie der volle Verlauf (gleiche
 * Abfrage, kein neuer Endpunkt). Ein Klick springt zu den vollständigen Kurven weiter unten.
 */
export function TimelineCompact({
  patientId,
  lastVisitAt,
  serverNow,
}: {
  patientId: string;
  lastVisitAt: string | null | undefined;
  serverNow: Date | null;
}) {
  const { t } = useTranslation();
  const context = { serverNow, lastVisitAt };
  // derselbe Standardbereich wie im vollen Verlauf (seit letztem Termin, sonst alles) → eine Abfrage
  const range = timelineRange('visit', context) ?? timelineRange('all', context);
  const query = useTimeline(patientId, range);
  const timeline = query.data;
  const domain = useMemo(() => (timeline ? domainOf(timeline) : null), [timeline]);
  const picked = useMemo(
    () => (timeline ? pickCompactSeries(timeline.series, timeline.alerts) : []),
    [timeline],
  );

  function jump() {
    const target = document.getElementById(TIMELINE_FULL_ID);
    target?.scrollIntoView?.({ block: 'start' });
    document.getElementById('timeline-title')?.focus();
  }

  if (query.isError || (timeline && (!domain || picked.length === 0))) return null;

  return (
    <section
      aria-labelledby="timeline-compact-title"
      data-testid="timeline-compact"
      className="@container rounded-lg border border-border bg-surface p-1"
    >
      <div className="flex flex-col gap-1 @3xl:flex-row @3xl:items-center @3xl:gap-x-4">
        <h2 id="timeline-compact-title" className="m-0 text-base font-semibold">
          {t('waechter.clinic.timeline.compact.title')}
        </h2>
        {query.isPending || !timeline || !domain ? (
          <div className="min-w-0 flex-1">
            <SkeletonBlock lines={1} />
          </div>
        ) : (
          <ul className="m-0 grid min-w-0 flex-1 list-none grid-cols-1 gap-2 p-0 @md:grid-cols-2 @3xl:grid-cols-4">
            {picked.map(({ series, openAlerts }) => {
              const title = `${series.label} · ${t(`waechter.clinic.since.attr.${series.attribute}`, { defaultValue: series.attribute })}`;
              const last = lastValue(series);
              const lastText =
                last === null
                  ? t('waechter.clinic.timeline.compact.noValue')
                  : t('waechter.clinic.timeline.compact.last', { value: last });
              return (
                <li key={`${series.symptom_key}-${series.attribute}`} className="min-w-0">
                  <button
                    type="button"
                    data-testid="timeline-compact-card"
                    data-open-alert={openAlerts.length > 0 ? 'true' : 'false'}
                    aria-label={t('waechter.clinic.timeline.compact.open', {
                      title,
                      last: lastText,
                    })}
                    onClick={jump}
                    className="flex min-h-11 w-full min-w-0 items-center gap-2 rounded-md border border-border-strong bg-surface px-2 text-left text-base hover:bg-sunken"
                  >
                    <Sparkline
                      series={series}
                      domain={domain}
                      alertTimes={openAlerts
                        .map((alert) => Date.parse(alert.created_at))
                        .filter((ms) => !Number.isNaN(ms))}
                    />
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-semibold">{series.label}</span>
                      <span className="text-muted"> · {lastText}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
