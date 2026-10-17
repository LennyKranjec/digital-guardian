import { useTranslation } from 'react-i18next';

import type { AlertLevel } from '../api/client';

/** Stufe einer Regel (rot/gelb/grau) als Form + Text; dieselben Formen wie die Meldungsmarker des Verlaufs. */
const COLOR: Record<AlertLevel, string> = {
  red: 'text-status-critical-fg',
  yellow: 'text-status-caution-fg',
  grey: 'text-status-neutral-fg',
};

export function LevelBadge({ level }: { level: AlertLevel }) {
  const { t } = useTranslation();
  return (
    <span
      data-level={level}
      className={`inline-flex min-h-8 items-center gap-2 text-base font-semibold ${COLOR[level]}`}
    >
      <svg
        aria-hidden="true"
        focusable="false"
        width={20}
        height={20}
        viewBox="0 0 20 20"
        className="stroke-current"
        strokeWidth={2}
      >
        {level === 'red' ? (
          <polygon points="10,1 19,10 10,19 1,10" className="fill-current" />
        ) : null}
        {level === 'yellow' ? <polygon points="10,2 19,18 1,18" className="fill-current" /> : null}
        {level === 'grey' ? (
          <>
            <circle cx={10} cy={10} r={7.5} className="fill-surface" />
            <line x1={6} y1={10} x2={14} y2={10} />
          </>
        ) : null}
      </svg>
      <span className="text-ink">{t(`waechter.clinic.timeline.levels.${level}`)}</span>
    </span>
  );
}
