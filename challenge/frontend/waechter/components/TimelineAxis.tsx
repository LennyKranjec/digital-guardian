import { useMemo } from 'react';

import { scaleX, timeTicks, type Domain } from '../model/timeline';
import { DISPLAY_TIME_ZONE } from '../model/time';

const LEFT = 34;
const RIGHT = 48;
const LABEL_SPACE = 64; // Platz je Datumsmarke (16-px-Schrift, „17.10.“)

/** Gemeinsame Zeitachse (Prager Kalendertage). Reine Beschriftung; die Daten stehen in der Ereignisliste. */
export function TimelineAxis({
  domain,
  width,
  locale,
}: {
  domain: Domain;
  width: number;
  locale: string;
}) {
  const ticks = useMemo(() => {
    const maxTicks = Math.max(2, Math.floor((width - LEFT - RIGHT) / LABEL_SPACE));
    return timeTicks(domain.from, domain.to, maxTicks);
  }, [domain, width]);
  const x = useMemo(() => scaleX(domain, LEFT, width - RIGHT), [domain, width]);
  const format = useMemo(
    () =>
      new Intl.DateTimeFormat(locale, {
        day: '2-digit',
        month: '2-digit',
        timeZone: DISPLAY_TIME_ZONE,
      }),
    [locale],
  );

  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={width}
      height={30}
      viewBox={`0 0 ${width} 30`}
      className="block max-w-full"
      data-testid="timeline-axis"
    >
      <line
        x1={LEFT}
        x2={width - RIGHT}
        y1={4}
        y2={4}
        className="stroke-current text-border-strong"
        strokeWidth={1.5}
      />
      {ticks.map((tick) => (
        <g key={tick.ms}>
          <line
            x1={x(tick.ms)}
            x2={x(tick.ms)}
            y1={4}
            y2={10}
            className="stroke-current text-border-strong"
            strokeWidth={1.5}
          />
          <text
            x={x(tick.ms)}
            y={27}
            textAnchor="middle"
            fontSize={16}
            className="fill-current text-muted"
          >
            {format.format(new Date(tick.ms))}
          </text>
        </g>
      ))}
    </svg>
  );
}
