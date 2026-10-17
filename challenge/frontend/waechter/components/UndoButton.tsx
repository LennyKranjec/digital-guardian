import { useTranslation } from 'react-i18next';

/** Runder Teal-Icon-Knopf (44 px) „Zurück“: nimmt die letzte Antwort der offenen Sitzung zurück. */
export function UndoButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={t('waechter.patient.session.back')}
      data-testid="session-undo"
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent hover:bg-accent-hover focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60"
    >
      <svg
        aria-hidden="true"
        focusable="false"
        viewBox="0 0 24 24"
        width="24"
        height="24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M15 5l-7 7 7 7" />
      </svg>
    </button>
  );
}
