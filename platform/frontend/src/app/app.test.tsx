import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { registerNav, registerRoleHome, registerRoutes, resetRegistry } from '../registry';
import {
  ADMIN,
  META_FIXTURE,
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../test/render';

afterEach(() => {
  vi.unstubAllGlobals();
  resetRegistry();
});

describe('Plattform ohne Challenge', () => {
  it('zeigt den Platzhalter „Noch keine Challenge-Funktionen geladen“', async () => {
    mockFetch(defaultApiResponse);
    renderApp('/');
    expect(await screen.findByTestId('no-challenge')).toHaveTextContent(
      'Noch keine Challenge-Funktionen geladen',
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Test-Plattform');
  });

  it('zeigt den Platzhalter nicht mehr, wenn ein Challenge-Paket geladen ist', async () => {
    mockFetch((url) =>
      url.endsWith('/meta')
        ? jsonResponse({ ...META_FIXTURE, challenge_loaded: true })
        : defaultApiResponse(url),
    );
    renderApp('/');
    expect(await screen.findByTestId('meta-list')).toBeInTheDocument();
    expect(screen.queryByTestId('no-challenge')).not.toBeInTheDocument();
  });

  it('hat einen nicht schließbaren Demo-Hinweis, Skip-Link und genau eine h1', async () => {
    mockFetch(defaultApiResponse);
    renderApp('/');
    const banner = await screen.findByTestId('demo-banner');
    expect(banner).toHaveTextContent('Demo · synthetische Daten');
    expect(within(banner).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Zum Inhalt springen' })).toHaveAttribute(
      'href',
      '#main',
    );
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('antwortet auf unbekannte Adressen mit 404-Seite und genau einer h1', async () => {
    mockFetch(defaultApiResponse);
    renderApp('/gibt-es-nicht');
    expect(await screen.findByText('Seite nicht gefunden')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('zeigt den Fehlerzustand mit „Erneut versuchen“, wenn /meta ausfällt', async () => {
    mockFetch((url) =>
      url.endsWith('/meta')
        ? jsonResponse({ code: 'x', message: 'x', field_errors: [] }, 500)
        : defaultApiResponse(url),
    );
    renderApp('/');
    expect(await screen.findByText('Das hat nicht geklappt')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Erneut versuchen' })).toBeInTheDocument();
  });
});

describe('Registry-Erweiterung (docs/EXTENDING.md: neue Seite)', () => {
  it('trägt eine Route samt Navigationseintrag und Rollen-Startseite ein', async () => {
    registerRoutes({ path: 'example', element: <h1>Beispielseite</h1> });
    registerNav({ to: '/example', labelKey: 'example.nav', roles: ['admin'] });
    registerRoleHome('admin', '/example');
    const { default: i18n } = await import('../shared/i18n');
    i18n.addResourceBundle('de', 'translation', { example: { nav: 'Beispiel' } }, true, false);
    mockFetch((url) => (url.endsWith('/auth/me') ? jsonResponse(ADMIN) : defaultApiResponse(url)));
    const user = userEvent.setup();
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Hauptnavigation' });
    await user.click(await within(nav).findByRole('link', { name: 'Beispiel' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Beispielseite' })).toBeVisible();
    // „Mein Bereich“ führt zur registrierten Startseite der Rolle
    expect(within(nav).getByRole('link', { name: 'Mein Bereich' })).toHaveAttribute(
      'href',
      '/example',
    );
  });

  it('blendet Navigationseinträge anderer Rollen aus', async () => {
    registerNav({ to: '/example', labelKey: 'example.nav', roles: ['reviewer'] });
    mockFetch((url) => (url.endsWith('/auth/me') ? jsonResponse(ADMIN) : defaultApiResponse(url)));
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Hauptnavigation' });
    await within(nav).findByRole('link', { name: 'Mein Bereich' });
    expect(within(nav).queryByRole('link', { name: /example/i })).not.toBeInTheDocument();
  });
});
