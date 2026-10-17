import { useSyncExternalStore } from 'react';

import { currentTheme, type Theme } from './theme';

function subscribe(callback: () => void): () => void {
  const observer = new MutationObserver(callback);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  return () => {
    observer.disconnect();
  };
}

/** Wirksame Darstellung als React-State; reagiert auf Änderungen von `data-theme`. */
export function useCurrentTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme, () => 'light');
}
