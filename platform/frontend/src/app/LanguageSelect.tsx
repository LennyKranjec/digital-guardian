import { useTranslation } from 'react-i18next';

import { LOCALE_NAMES, SUPPORTED_LOCALES, isLocale, setLocale } from '../shared/i18n';

/** Sprachwahl mit Globus-Symbol statt Textbeschriftung (Name für Screenreader bleibt „Sprache“). */
export function LanguageSelect() {
  const { t, i18n } = useTranslation();
  return (
    <label className="inline-flex items-center gap-1 text-sm" title={t('language.label')}>
      <GlobeIcon />
      <span className="sr-only">{t('language.label')}</span>
      <select
        value={i18n.resolvedLanguage ?? i18n.language}
        onChange={(event) => {
          if (isLocale(event.target.value)) setLocale(event.target.value);
        }}
        className="min-h-11 rounded-full border border-border-strong bg-surface px-3 text-base text-ink"
      >
        {SUPPORTED_LOCALES.map((locale) => (
          <option key={locale} value={locale} lang={locale}>
            {LOCALE_NAMES[locale]}
          </option>
        ))}
      </select>
    </label>
  );
}

function GlobeIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      className="text-muted"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.8 3 2.8 15 0 18M12 3c-2.8 3-2.8 15 0 18" />
    </svg>
  );
}
