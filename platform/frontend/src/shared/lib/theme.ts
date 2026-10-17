export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'rk-theme';

export function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark';
}

export function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isTheme(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Aktuell wirksame Darstellung: Attribut (vom Inline-Script in index.html gesetzt) vor Speicher vor System. */
export function currentTheme(): Theme {
  const attr = document.documentElement.getAttribute('data-theme');
  if (isTheme(attr)) return attr;
  return readStoredTheme() ?? systemTheme();
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Speicher blockiert: Wahl gilt nur für diese Sitzung.
  }
}
