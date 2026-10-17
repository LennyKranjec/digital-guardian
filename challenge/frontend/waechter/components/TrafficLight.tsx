import { useTranslation } from 'react-i18next';

import type { TrafficLightLevel } from '../api/client';

/**
 * Ampel der Arbeitsliste: Icon + Text, nie nur Farbe. Vier unterscheidbare Formen
 * (Achteck = rot, Dreieck = gelb, Auge mit Fragezeichen = grau/unbekannt, Haken = grün);
 * grau heißt „Daten fehlen“, nie „gut“ (Vertrag §3).
 */
const STYLE: Record<TrafficLightLevel, string> = {
  red: 'bg-status-critical-bg text-status-critical-fg',
  yellow: 'bg-status-caution-bg text-status-caution-fg',
  grey: 'bg-status-neutral-bg text-status-neutral-fg',
  green: 'bg-status-info-bg text-status-info-fg',
};

function Icon({ level }: { level: TrafficLightLevel }) {
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
  switch (level) {
    case 'red':
      return (
        <svg {...common}>
          <path d="M6.5 2.5h7l4 4v7l-4 4h-7l-4-4v-7z" />
          <path d="M10 6.5v4.5" />
          <path d="M10 13.8h.01" />
        </svg>
      );
    case 'yellow':
      return (
        <svg {...common}>
          <path d="M10 2.5l8 14H2z" />
          <path d="M10 8v4" />
          <path d="M10 14.5h.01" />
        </svg>
      );
    case 'grey':
      return (
        <svg {...common}>
          <path d="M1.5 10S5 4.5 10 4.5 18.5 10 18.5 10 15 15.5 10 15.5 1.5 10 1.5 10z" />
          <path d="M8.2 8.6c0-.9.8-1.5 1.8-1.5s1.8.6 1.8 1.5-.8 1.2-1.8 1.7" />
          <path d="M10 12.6h.01" />
        </svg>
      );
    case 'green':
      return (
        <svg {...common}>
          <circle cx="10" cy="10" r="8" />
          <path d="M6.5 10.5l2.5 2.5 4.5-5" />
        </svg>
      );
  }
}

export function TrafficLight({
  level,
  size = 'normal',
  label,
}: {
  level: TrafficLightLevel;
  size?: 'normal' | 'large';
  /** eigener Text statt der Standardbeschriftung (z. B. Stufe der Triage) */
  label?: string;
}) {
  const { t } = useTranslation();
  return (
    <span
      data-traffic-light={level}
      className={`inline-flex items-center gap-2 rounded-md border border-current font-semibold ${
        size === 'large' ? 'min-h-11 px-4 py-2 text-xl' : 'min-h-8 px-3 py-1 text-base'
      } ${STYLE[level]}`}
    >
      <Icon level={level} />
      <span>{label ?? t(`waechter.clinic.light.${level}`)}</span>
    </span>
  );
}
