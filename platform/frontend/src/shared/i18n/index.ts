import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

import cs from './cs.json';
import de from './de.json';
import en from './en.json';

/** Reihenfolge = Reihenfolge im Umschalter; Tschechisch ist Standard, Deutsch optional (T-215). */
export const SUPPORTED_LOCALES = ['cs', 'en', 'de'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: Locale = 'cs';

/** Eigenbezeichnungen der Sprachen (nicht übersetzt, damit sie in jeder Sprache auffindbar sind). */
export const LOCALE_NAMES: Record<Locale, string> = {
  cs: 'Čeština',
  en: 'English',
  de: 'Deutsch',
};

const STORAGE_KEY = 'rk-lang';

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

function readStoredLocale(): Locale | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isLocale(stored) ? stored : null;
  } catch {
    return null;
  }
}

function detectLocale(): Locale {
  const stored = readStoredLocale();
  if (stored) return stored;
  const browser = typeof navigator === 'undefined' ? '' : navigator.language.slice(0, 2);
  return isLocale(browser) ? browser : DEFAULT_LOCALE;
}

export function setLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Speicher blockiert: Sprache gilt nur für diese Sitzung.
  }
  void i18n.changeLanguage(locale);
}

void i18n.use(initReactI18next).init({
  resources: { de: { translation: de }, en: { translation: en }, cs: { translation: cs } },
  lng: detectLocale(),
  // cs und en sind vollständig (Paritätstest); de ist optional und fällt auf en, dann cs zurück.
  fallbackLng: { de: ['en', 'cs'], default: ['cs', 'en'] },
  interpolation: { escapeValue: false },
  initAsync: false,
});

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng;
});
document.documentElement.lang = i18n.language;

export default i18n;
