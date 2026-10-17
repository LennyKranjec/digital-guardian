import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// Tests laufen deterministisch auf Deutsch (jsdom meldet sonst en-US).
Object.defineProperty(navigator, 'language', { value: 'de-DE', configurable: true });

// Lazy geladene Seiten brauchen beim ersten Lauf (kalter Vite-Cache) länger als die Standardfrist.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
});

// jsdom kennt matchMedia nicht; Standard in Tests: helle Systemdarstellung.
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
});
