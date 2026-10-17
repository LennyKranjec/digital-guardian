import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';

import type { Series, Timeline } from '../api/client';
import {
  alertFactId,
  alertsForSeries,
  pragueDayRange,
  scaleX,
  scaleY,
  timedPoints,
  valueRuns,
  type Domain,
  type Threshold,
} from '../model/timeline';
import { formatAbsolute } from '../model/time';
import { HatchPattern, Marker, VerticalLine, type MarkerKind } from './TimelineMarkers';

const LEFT = 34;
const RIGHT = 48;
const TOP = 14;
const PLOT_HEIGHT = 100;
const SERIES_HEIGHT = TOP + PLOT_HEIGHT + 14;
const LANE_HEIGHT = 56;

/** Ein anklickbares Element der Grafik (Messpunkt, Lücke, Meldung, Termin, Aufnahme). */
interface Item {
  key: string;
  x: number;
  y: number;
  label: string;
  factId?: string;
}

interface TimelineChartProps {
  /** Kurve eines Symptoms/Merkmals; ohne `series` die Ereignisleiste (Meldungen, Termine, Aufnahmen) */
  series?: Series;
  title: string;
  timeline: Timeline;
  domain: Domain;
  width: number;
  thresholds?: readonly Threshold[];
  locale: string;
  onOpenFact: (factId: string) => void;
}

/**
 * Eine Kurve der Small Multiples (Skala 0–4, gemeinsame Zeitachse) oder die Ereignisleiste.
 * Lücken (fehlende Werte) werden nicht verbunden, Tage ohne Eingabe sind schraffiert. Die Grafik
 * ist ein beschriftetes Bild (`role="img"`); die Punkte und Marker liegen als Schaltflächen
 * darüber (ein Tabstopp je Grafik, Pfeiltasten wechseln das Element) und öffnen den Beleg.
 */
export function TimelineChart({
  series,
  title,
  timeline,
  domain,
  width,
  thresholds = [],
  locale,
  onOpenFact,
}: TimelineChartProps) {
  const { t } = useTranslation();
  const hatchId = `hatch-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const isLane = series === undefined;
  const height = isLane ? LANE_HEIGHT : SERIES_HEIGHT;
  const plotBottom = isLane ? LANE_HEIGHT - 8 : TOP + PLOT_HEIGHT;
  const x = useMemo(() => scaleX(domain, LEFT, width - RIGHT), [domain, width]);
  const y = useMemo(() => scaleY(TOP, plotBottom), [plotBottom]);
  const laneY = LANE_HEIGHT / 2;
  const when = (iso: string) => formatAbsolute(iso, locale);
  const levelText = (level: 'red' | 'yellow' | 'grey') =>
    t(`waechter.clinic.timeline.levels.${level}`);

  const points = useMemo(() => (series ? timedPoints(series.points) : []), [series]);
  const runs = useMemo(() => valueRuns(points), [points]);
  const ownAlerts = useMemo(
    () => (series ? alertsForSeries(timeline.alerts, series) : timeline.alerts),
    [series, timeline.alerts],
  );

  /** letzter bekannter Wert zum Zeitpunkt (für die Höhe der Meldungsmarker auf der Kurve) */
  const valueAt = (ms: number): number | null => {
    let found: number | null = null;
    for (const point of points) {
      if (point.ms > ms) break;
      if (point.value !== null) found = point.value;
    }
    return found;
  };

  const { items, alertMarkers, visitLines, assessmentLines, laneMarkers } = useMemo(() => {
    const list: Item[] = [];
    const markers: { key: string; kind: MarkerKind; x: number; y: number }[] = [];
    const lane: { key: string; kind: MarkerKind; x: number; y: number }[] = [];

    if (series) {
      for (const point of points) {
        const label =
          point.value === null
            ? t('waechter.clinic.timeline.item.gap', {
                title,
                date: when(new Date(point.ms).toISOString()),
              })
            : t('waechter.clinic.timeline.item.point', {
                title,
                value: point.value,
                date: when(new Date(point.ms).toISOString()),
              });
        list.push({
          key: `p-${point.ms}-${point.factId}`,
          x: x(point.ms),
          y: point.value === null ? y(0) : y(point.value),
          label,
          factId: point.factId,
        });
      }
    }

    for (const alert of ownAlerts) {
      const ms = Date.parse(alert.created_at);
      if (Number.isNaN(ms)) continue;
      const onCurve = valueAt(ms);
      const cy = isLane ? laneY : onCurve === null ? TOP - 2 : y(onCurve);
      const marker = {
        key: `a-${alert.alert_id}`,
        kind: { type: 'alert', level: alert.level } as MarkerKind,
        x: x(ms),
        y: cy,
      };
      (isLane ? lane : markers).push(marker);
      list.push({
        key: marker.key,
        x: marker.x,
        y: marker.y,
        factId: alertFactId(alert),
        label: t('waechter.clinic.timeline.item.alert', {
          level: levelText(alert.level),
          headline: alert.headline ?? alert.rule_id,
          date: when(alert.created_at),
        }),
      });
    }

    if (isLane) {
      for (const visit of timeline.visits) {
        const ms = Date.parse(visit.at);
        if (Number.isNaN(ms)) continue;
        const planned = visit.kind === 'planned';
        const marker = {
          key: `v-${visit.at}`,
          kind: { type: 'visit', planned } as MarkerKind,
          x: x(ms),
          y: laneY,
        };
        lane.push(marker);
        if (visit.fact_id) {
          list.push({
            key: marker.key,
            x: marker.x,
            y: marker.y,
            factId: visit.fact_id,
            label: t('waechter.clinic.timeline.item.visit', {
              kind: t(`waechter.clinic.timeline.visitKind.${planned ? 'planned' : 'past'}`),
              date: when(visit.at),
            }),
          });
        }
      }
      for (const assessment of timeline.assessments) {
        const ms = Date.parse(assessment.assessed_at);
        if (Number.isNaN(ms)) continue;
        const marker = {
          key: `s-${assessment.assessment_id}`,
          kind: { type: 'assessment' } as MarkerKind,
          x: x(ms),
          y: laneY,
        };
        lane.push(marker);
        if (assessment.fact_id) {
          list.push({
            key: marker.key,
            x: marker.x,
            y: marker.y,
            factId: assessment.fact_id,
            label: t('waechter.clinic.timeline.item.assessment', {
              date: when(assessment.assessed_at),
            }),
          });
        }
      }
    }

    list.sort((a, b) => a.x - b.x || a.y - b.y);
    const lines = (iso: string[]) =>
      iso
        .map((at) => Date.parse(at))
        .filter((ms) => !Number.isNaN(ms))
        .map((ms) => x(ms));
    return {
      items: list,
      alertMarkers: markers,
      laneMarkers: lane,
      visitLines: {
        past: lines(
          timeline.visits.filter((visit) => visit.kind !== 'planned').map((visit) => visit.at),
        ),
        planned: lines(
          timeline.visits.filter((visit) => visit.kind === 'planned').map((visit) => visit.at),
        ),
      },
      assessmentLines: lines(timeline.assessments.map((assessment) => assessment.assessed_at)),
    };
  }, [series, points, ownAlerts, timeline, x, y, isLane, locale, title, t]);

  const missingRects = useMemo(
    () =>
      timeline.missing_days.flatMap((date) => {
        const range = pragueDayRange(date);
        if (!range) return [];
        const start = x(Math.max(range[0], domain.from));
        const end = x(Math.min(range[1], domain.to));
        return end > start ? [{ date, x: start, width: end - start }] : [];
      }),
    [timeline.missing_days, domain, x],
  );

  /* ---------- Fokus (ein Tabstopp, Pfeiltasten) und Bildunterschrift ---------- */
  const [active, setActive] = useState(0);
  const [caption, setCaption] = useState('');
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const focusable = items.filter((item) => item.factId);
  const current = Math.min(active, Math.max(focusable.length - 1, 0));

  function move(target: number) {
    const next = Math.min(Math.max(target, 0), focusable.length - 1);
    setActive(next);
    buttons.current[next]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, number> = {
      ArrowRight: current + 1,
      ArrowDown: current + 1,
      ArrowLeft: current - 1,
      ArrowUp: current - 1,
      Home: 0,
      End: focusable.length - 1,
    };
    const target = keys[event.key];
    if (target === undefined) return;
    event.preventDefault();
    move(target);
  }

  const valueCount = points.filter((point) => point.value !== null).length;
  const chartLabel = series
    ? t('waechter.clinic.timeline.chartLabel', {
        title,
        values: valueCount,
        gaps: points.length - valueCount,
        alerts: ownAlerts.length,
      })
    : t('waechter.clinic.timeline.laneLabel', {
        alerts: timeline.alerts.length,
        visits: timeline.visits.length,
        assessments: timeline.assessments.length,
      });
  const lastValue = [...points].reverse().find((point) => point.value !== null);

  return (
    <section className="space-y-1" data-testid={isLane ? 'timeline-lane' : 'timeline-chart'}>
      <h3 className="text-base font-semibold">{title}</h3>
      <div className="relative" style={{ width, height }}>
        <svg
          role="img"
          aria-label={chartLabel}
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className="block max-w-full"
        >
          <defs>
            <HatchPattern id={hatchId} />
          </defs>
          {!isLane
            ? [0, 1, 2, 3, 4].map((value) => (
                <g key={value}>
                  <line
                    x1={LEFT}
                    x2={width - RIGHT}
                    y1={y(value)}
                    y2={y(value)}
                    className="stroke-current text-border"
                    strokeWidth={1}
                  />
                  {value % 2 === 0 ? (
                    <text
                      x={LEFT - 8}
                      y={y(value) + 5}
                      textAnchor="end"
                      fontSize={16}
                      className="fill-current text-muted"
                    >
                      {value}
                    </text>
                  ) : null}
                </g>
              ))
            : null}
          {missingRects.map((rect) => (
            <rect
              key={rect.date}
              x={rect.x}
              y={TOP}
              width={rect.width}
              height={plotBottom - TOP}
              fill={`url(#${hatchId})`}
              opacity={0.45}
              data-testid="missing-day"
              data-date={rect.date}
            />
          ))}
          {visitLines.past.map((lineX, index) => (
            <VerticalLine
              key={`vp-${index}`}
              x={lineX}
              top={TOP}
              bottom={plotBottom}
              style="visit-past"
            />
          ))}
          {visitLines.planned.map((lineX, index) => (
            <VerticalLine
              key={`vf-${index}`}
              x={lineX}
              top={TOP}
              bottom={plotBottom}
              style="visit-planned"
            />
          ))}
          {!isLane
            ? assessmentLines.map((lineX, index) => (
                <VerticalLine
                  key={`as-${index}`}
                  x={lineX}
                  top={TOP}
                  bottom={plotBottom}
                  style="assessment"
                />
              ))
            : null}
          {thresholds.map((threshold) => (
            <g key={threshold.ruleId} data-testid="threshold">
              <line
                x1={LEFT}
                x2={width - RIGHT}
                y1={y(threshold.value)}
                y2={y(threshold.value)}
                strokeDasharray="7 5"
                strokeWidth={2}
                className="stroke-current text-ink"
              />
              <text
                x={LEFT + 6}
                y={y(threshold.value) - 6}
                fontSize={16}
                className="fill-current text-ink"
                stroke="var(--rk-bg)"
                strokeWidth={4}
                paintOrder="stroke"
              >
                {t('waechter.clinic.timeline.threshold', { value: threshold.value })}
              </text>
            </g>
          ))}
          {runs.map((run, index) => (
            <g key={`run-${index}`} data-testid="value-run" className="stroke-current text-accent">
              {run.length > 1 ? (
                <polyline
                  fill="none"
                  strokeWidth={2.5}
                  strokeLinejoin="round"
                  points={run.map((point) => `${x(point.ms)},${y(point.value)}`).join(' ')}
                />
              ) : null}
              {run.map((point) => (
                <circle
                  key={`${point.ms}-${point.factId}`}
                  cx={x(point.ms)}
                  cy={y(point.value)}
                  r={4.5}
                  className="fill-surface"
                  strokeWidth={2.5}
                  data-testid="value-point"
                />
              ))}
            </g>
          ))}
          {points
            .filter((point) => point.value === null)
            .map((point) => (
              <g
                key={`gap-${point.ms}-${point.factId}`}
                className="stroke-current text-muted"
                strokeWidth={2.5}
                data-testid="gap-marker"
              >
                <line x1={x(point.ms) - 5} y1={y(0) - 5} x2={x(point.ms) + 5} y2={y(0) + 5} />
                <line x1={x(point.ms) - 5} y1={y(0) + 5} x2={x(point.ms) + 5} y2={y(0) - 5} />
              </g>
            ))}
          {alertMarkers.map((marker) => (
            <Marker key={marker.key} kind={marker.kind} x={marker.x} y={marker.y} />
          ))}
          {laneMarkers.map((marker) => (
            <Marker key={marker.key} kind={marker.kind} x={marker.x} y={marker.y} />
          ))}
          {lastValue && lastValue.value !== null ? (
            <text
              x={x(lastValue.ms) + 9}
              y={y(lastValue.value) + 5}
              fontSize={16}
              fontWeight={700}
              className="fill-current text-ink"
              data-testid="end-label"
            >
              {lastValue.value}
            </text>
          ) : null}
        </svg>
        <div
          role="group"
          aria-label={t('waechter.clinic.timeline.itemsGroup', { title })}
          onKeyDown={onKeyDown}
          className="absolute inset-0"
        >
          {focusable.map((item, index) => (
            <button
              key={item.key}
              ref={(node) => {
                buttons.current[index] = node;
              }}
              type="button"
              tabIndex={index === current ? 0 : -1}
              aria-label={item.label}
              title={item.label}
              onFocus={() => {
                setActive(index);
                setCaption(item.label);
              }}
              onBlur={() => setCaption('')}
              onMouseEnter={() => setCaption(item.label)}
              onMouseLeave={() => setCaption('')}
              onClick={() => item.factId && onOpenFact(item.factId)}
              className="absolute rounded-full bg-transparent focus-visible:outline-3 focus-visible:outline-offset-0"
              style={{ left: item.x - 22, top: item.y - 22, width: 44, height: 44 }}
              data-testid="chart-item"
            />
          ))}
        </div>
      </div>
      <p aria-live="polite" className="min-h-6 text-base text-muted" data-testid="chart-caption">
        {caption}
      </p>
    </section>
  );
}
