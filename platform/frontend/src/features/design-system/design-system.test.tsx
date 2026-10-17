import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  META_FIXTURE,
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../../test/render';

afterEach(() => vi.unstubAllGlobals());

describe('Design-System-Showcase', () => {
  it(
    'zeigt vier neutrale Status mit Icon und Text (nie nur Farbe)',
    { timeout: 45_000 },
    async () => {
      mockFetch(defaultApiResponse);
      renderApp('/design-system');
      // platform-fix: unter Rechnerlast lädt die Seite > 10 s (A3 INT-2 F-01) (Standard-Timeout von findBy*).
      const section = await screen.findByRole('region', { name: /Status/ }, { timeout: 30_000 });
      const badges = section.querySelectorAll('[data-status]');
      expect(badges).toHaveLength(4);
      for (const badge of badges) {
        expect(badge.querySelector('svg')).not.toBeNull();
        expect(badge.textContent?.trim().length).toBeGreaterThan(0);
      }
      expect(within(section).getByText('Kritisch')).toBeInTheDocument();
    },
  );

  it('liefert ohne Demo-Modus eine 404-Seite mit genau einer h1', { timeout: 45_000 }, async () => {
    mockFetch((url) =>
      url.endsWith('/meta')
        ? jsonResponse({ ...META_FIXTURE, demo_mode: false })
        : defaultApiResponse(url),
    );
    renderApp('/design-system');
    expect(
      await screen.findByText('Seite nicht gefunden', {}, { timeout: 30_000 }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });
});
