import { useTranslation } from 'react-i18next';

import { Bodlik } from './Bodlik';

interface PatientProgressBarProps {
  value: number;
  max: number;
  /** Sprechender Text (Screenreader); Standard „x / y“ */
  valueText?: string;
  /** Sichtbarer Text statt „x / y“ (z. B. „1 von 3 beantwortet“), damit nichts doppelt erscheint */
  label?: string;
}

/**
 * Ein abgerundeter Balken (Teal auf Sand) mit dem Igel Bodlík an der Füllkante. Die Werte trägt
 * `role="progressbar"` (aria-valuenow/min/max) und der sichtbare Text „x / y“; Igel und Füllung
 * sind nur Zierde. Keine Ampel, keine Stufe, kein Prozentwert.
 */
export function PatientProgressBar({ value, max, valueText, label }: PatientProgressBarProps) {
  const { t } = useTranslation();
  const safeMax = Math.max(0, max);
  const now = Math.min(Math.max(0, value), safeMax);
  const percent = safeMax === 0 ? 0 : (now / safeMax) * 100;
  const count = t('waechter.patient.session.progressCount', { current: now, max: safeMax });
  return (
    <div className="flex min-w-0 flex-1 items-center gap-3">
      <div
        role="progressbar"
        aria-label={t('waechter.patient.session.progressLabel')}
        aria-valuemin={0}
        aria-valuemax={safeMax}
        aria-valuenow={now}
        aria-valuetext={valueText ?? count}
        data-testid="patient-progressbar"
        className="relative h-11 min-w-0 flex-1"
      >
        <div className="absolute inset-x-5 top-1/2 h-4 -translate-y-1/2 rounded-full bg-[var(--wp-track)]">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-300 motion-reduce:transition-none"
            style={{ width: `${percent}%` }}
          />
        </div>
        <div aria-hidden="true" className="pointer-events-none absolute inset-x-5 inset-y-0">
          <Bodlik
            size={40}
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 transition-[left] duration-300 motion-reduce:transition-none"
            style={{ left: `${percent}%` }}
          />
        </div>
      </div>
      <span
        className={`text-base font-semibold tabular-nums ${label ? 'min-w-0 max-w-[50%] break-words' : 'shrink-0'}`}
        data-testid="progress-count"
      >
        {label ?? count}
      </span>
    </div>
  );
}
