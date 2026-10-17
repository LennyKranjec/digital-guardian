import { useTranslation } from 'react-i18next';

/**
 * Pflichthinweis zum PRO-CTCAE-Wortlaut (T-23, DR-040): Markenhinweis der NCI wörtlich (Englisch, wie im
 * Dokument) und Prototyp-Hinweis in der Sprache der Oberfläche. Steht unter jedem Fragebogen der Patientin.
 */
export function ProCtcaeNotice() {
  const { t } = useTranslation();
  return (
    <footer
      className="space-y-1 border-t border-border pt-4 text-base text-muted"
      data-testid="pro-ctcae-notice"
    >
      <p lang="en">{t('waechter.legal.proCtcae')}</p>
      <p>{t('waechter.legal.prototype')}</p>
    </footer>
  );
}
