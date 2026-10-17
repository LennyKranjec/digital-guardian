import { useTranslation } from 'react-i18next';

/** Dauerhafter Demo-Hinweis (ui.md §3): nicht schließbar, immer im Layout, kein Sprung. */
export function DemoBanner() {
  const { t } = useTranslation();
  return (
    <div
      role="note"
      data-testid="demo-banner"
      className="border-b border-border bg-accent-subtle px-4 py-2 text-center text-sm font-semibold text-accent-subtle-ink"
    >
      {t('banner.demo')}
    </div>
  );
}
