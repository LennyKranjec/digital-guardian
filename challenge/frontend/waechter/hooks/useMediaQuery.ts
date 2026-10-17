import { useSyncExternalStore } from 'react';

/** Reagiert auf eine CSS-Medienabfrage (z. B. Breite ≥ 768 px für die Tabellenansicht). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener('change', onChange);
      return () => list.removeEventListener('change', onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
