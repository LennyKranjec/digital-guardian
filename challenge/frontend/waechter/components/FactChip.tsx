import { useTranslation } from 'react-i18next';

/** Kurzform der Fakt-ID für den sichtbaren Chip: die letzten vier Zeichen des letzten Teils. */
export function shortFactId(factId: string): string {
  const last = factId.split('-').pop() ?? factId;
  return last.slice(-4);
}

/**
 * Beleg als Chip: Klick öffnet die Belegschublade (GET facts). Sichtbar stehen ein Belegsymbol und
 * das Ende der Fakt-ID (kurz, damit Kurzfassung und Meldungen auf einen Bildschirm passen); der
 * zugängliche Name und der Tooltip nennen die volle ID und die Aktion. Touchziel ≥ 44 px.
 */
export function FactChip({ factId, onOpen }: { factId: string; onOpen: (factId: string) => void }) {
  const { t } = useTranslation();
  const label = t('waechter.clinic.fact.open', { id: factId });
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-label={label}
      title={label}
      onClick={() => onOpen(factId)}
      className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-md border border-border-strong bg-surface px-2 text-base font-semibold text-ink hover:bg-sunken"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M3.5 1.5h6l3 3v10h-9z" />
        <path d="M9.5 1.5v3h3" />
      </svg>
      <span>{shortFactId(factId)}</span>
    </button>
  );
}
