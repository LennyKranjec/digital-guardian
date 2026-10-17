import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { HatchPattern, Marker, VerticalLine } from './TimelineMarkers';

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={32}
      height={24}
      viewBox="0 0 32 24"
      className="shrink-0"
    >
      {children}
    </svg>
  );
}

/** Legende mit Text: jede Darstellungsart (Form, Linie, Schraffur) ist beschriftet, nie nur farbcodiert. */
export function TimelineLegend({ thresholdSource }: { thresholdSource: string | null }) {
  const { t } = useTranslation();
  const entries: { key: string; glyph: ReactNode; text: string }[] = [
    {
      key: 'value',
      glyph: (
        <g className="stroke-current text-accent" strokeWidth={2.5}>
          <line x1={3} y1={12} x2={29} y2={12} />
          <circle cx={16} cy={12} r={4.5} className="fill-surface" />
        </g>
      ),
      text: t('waechter.clinic.timeline.legend.value'),
    },
    {
      key: 'gap',
      glyph: (
        <g className="stroke-current text-muted" strokeWidth={2.5}>
          <line x1={11} y1={7} x2={21} y2={17} />
          <line x1={11} y1={17} x2={21} y2={7} />
        </g>
      ),
      text: t('waechter.clinic.timeline.legend.gap'),
    },
    {
      key: 'missing',
      glyph: (
        <>
          <defs>
            <HatchPattern id="legend-hatch" />
          </defs>
          <rect x={4} y={3} width={24} height={18} fill="url(#legend-hatch)" opacity={0.6} />
        </>
      ),
      text: t('waechter.clinic.timeline.legend.missing'),
    },
    {
      key: 'threshold',
      glyph: (
        <line
          x1={2}
          y1={12}
          x2={30}
          y2={12}
          strokeDasharray="7 5"
          strokeWidth={2}
          className="stroke-current text-ink"
        />
      ),
      text: thresholdSource ?? t('waechter.clinic.timeline.legend.threshold'),
    },
    {
      key: 'red',
      glyph: <Marker kind={{ type: 'alert', level: 'red' }} x={16} y={12} />,
      text: t('waechter.clinic.timeline.legend.red'),
    },
    {
      key: 'yellow',
      glyph: <Marker kind={{ type: 'alert', level: 'yellow' }} x={16} y={12} />,
      text: t('waechter.clinic.timeline.legend.yellow'),
    },
    {
      key: 'grey',
      glyph: <Marker kind={{ type: 'alert', level: 'grey' }} x={16} y={12} />,
      text: t('waechter.clinic.timeline.legend.grey'),
    },
    {
      key: 'visit-past',
      glyph: <VerticalLine x={16} top={2} bottom={22} style="visit-past" />,
      text: t('waechter.clinic.timeline.legend.visitPast'),
    },
    {
      key: 'visit-planned',
      glyph: <VerticalLine x={16} top={2} bottom={22} style="visit-planned" />,
      text: t('waechter.clinic.timeline.legend.visitPlanned'),
    },
    {
      key: 'assessment',
      glyph: <VerticalLine x={16} top={2} bottom={22} style="assessment" />,
      text: t('waechter.clinic.timeline.legend.assessment'),
    },
  ];

  return (
    <section aria-labelledby="legend-title" className="space-y-2" data-testid="timeline-legend">
      <h3 id="legend-title" className="text-base font-semibold">
        {t('waechter.clinic.timeline.legend.title')}
      </h3>
      <ul className="m-0 grid list-none grid-cols-1 gap-x-6 gap-y-1 p-0 sm:grid-cols-2">
        {entries.map((entry) => (
          <li key={entry.key} className="flex items-center gap-2 text-base" data-legend={entry.key}>
            <Glyph>{entry.glyph}</Glyph>
            <span className="min-w-0 break-words">{entry.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
