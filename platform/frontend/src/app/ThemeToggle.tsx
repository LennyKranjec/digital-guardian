import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { applyTheme, currentTheme, type Theme } from '../shared/lib/theme';

/** Ein Symbol-Knopf: Sonne (hell) ⇄ Mond (dunkel). Beschriftung für Screenreader über aria-label. */
export function ThemeToggle() {
  const { t } = useTranslation();
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';

  return (
    <button
      type="button"
      data-testid="theme-toggle"
      aria-label={`${t('theme.label')}: ${t(`theme.${next}`)}`}
      title={t(`theme.${next}`)}
      aria-pressed={theme === 'dark'}
      onClick={() => {
        applyTheme(next);
        setTheme(next);
      }}
      className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-border-strong bg-surface text-ink hover:bg-sunken"
    >
      {theme === 'dark' ? <MoonIcon /> : <SunIcon />}
    </button>
  );
}

function SunIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
      <circle cx="12" cy="12" r="4.5" />
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
        <rect
          key={angle}
          x="11"
          y="1.5"
          width="2"
          height="4"
          rx="1"
          transform={`rotate(${angle} 12 12)`}
        />
      ))}
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
      <path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1Z" />
    </svg>
  );
}
