import { useTranslation } from 'react-i18next';

/** Vier neutrale Status; die Bedeutung legt das Challenge-Paket fest (die Plattform wertet nie). */
export const STATUSES = ['neutral', 'info', 'caution', 'critical'] as const;
export type Status = (typeof STATUSES)[number];

const STYLE: Record<Status, string> = {
  neutral: 'bg-status-neutral-bg text-status-neutral-fg',
  info: 'bg-status-info-bg text-status-info-fg',
  caution: 'bg-status-caution-bg text-status-caution-fg',
  critical: 'bg-status-critical-bg text-status-critical-fg',
};

/** Vier unterscheidbare Formen: ein Status ist nie nur über Farbe erkennbar. */
function StatusIcon({ status }: { status: Status }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: '0 0 20 20',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
  };
  switch (status) {
    case 'neutral':
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="8" />
          <path d="M6.5 10.5l2.5 2.5 4.5-5" />
        </svg>
      );
    case 'info':
      return (
        <svg {...common}>
          <path d="M1.5 10S5 4.5 10 4.5 18.5 10 18.5 10 15 15.5 10 15.5 1.5 10 1.5 10z" />
          <circle cx="10" cy="10" r="2.5" />
        </svg>
      );
    case 'caution':
      return (
        <svg {...common}>
          <path d="M10 2.5l8 14H2z" />
          <path d="M10 8v4" />
          <path d="M10 14.5h.01" />
        </svg>
      );
    case 'critical':
      return (
        <svg {...common}>
          <path d="M6.5 2.5h7l4 4v7l-4 4h-7l-4-4v-7z" />
          <path d="M10 6.5v4.5" />
          <path d="M10 13.8h.01" />
        </svg>
      );
  }
}

export function StatusBadge({ status }: { status: Status }) {
  const { t } = useTranslation();
  return (
    <span
      data-status={status}
      className={`inline-flex min-h-8 items-center gap-2 rounded-md border border-current px-3 py-1 text-sm font-semibold ${STYLE[status]}`}
    >
      <StatusIcon status={status} />
      <span>{t(`status.${status}`)}</span>
    </span>
  );
}
