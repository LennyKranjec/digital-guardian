import { screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  challengeNav,
  homeFor,
  pluginApi,
  resetRegistry,
} from '../../platform/frontend/src/registry';
import {
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
  UNAUTHENTICATED,
} from '../../platform/frontend/src/test/render';
import { stripLang } from './waechter/testing/cockpit-server';
import { CLINICIAN, PATIENT, QUESTIONNAIRE } from './waechter/testing/fixtures';
import { register } from './plugin';

const ADMIN = { id: 'u1', username: 'admin', display_name: 'Admin (Demo)', role: 'admin' };

function serveAs(me: unknown) {
  return mockFetch((rawUrl) => {
    const url = stripLang(rawUrl);
    if (url.endsWith('/auth/me')) {
      return me === null ? jsonResponse(UNAUTHENTICATED, 401) : jsonResponse(me);
    }
    if (url.includes('/waechter/me/questionnaire')) return jsonResponse(QUESTIONNAIRE);
    if (url.endsWith('/waechter/patients')) return jsonResponse([]);
    if (url.includes('/waechter/notifications')) return jsonResponse([]);
    return defaultApiResponse(url);
  });
}

beforeEach(() => {
  register(pluginApi);
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetRegistry();
});

describe('Challenge-Plugin: Registrierung', () => {
  it('setzt Rollen-Startseiten patient→/patient, clinician→/clinic, admin→/clinic', () => {
    expect(homeFor('patient')).toBe('/patient');
    expect(homeFor('clinician')).toBe('/clinic');
    expect(homeFor('admin')).toBe('/clinic');
  });

  it('trägt Arzneimittel und Einstellungen als eigene Navigationseinträge ein (kein Duplikat zu „Mein Bereich“)', () => {
    const nav = challengeNav();
    // Arzneimittel (F-12/F-13, Navigation bricht seit fix/nav-wrap um) und Einstellungen; nur Klinikrollen
    expect(nav.map((item) => item.to)).toEqual(['/clinic/medications', '/clinic/settings']);
    expect(nav.every((item) => item.roles?.join() === 'clinician,admin')).toBe(true);
    expect(nav.every((item) => item.labelKey.startsWith('waechter.nav.'))).toBe(true);
  });
});

describe('Challenge-Plugin: Routen und Rollen', () => {
  it('zeigt der Patientin den Check-in und nur den Eintrag „Mein Bereich“', async () => {
    serveAs(PATIENT);
    renderApp('/patient');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Symptome erfassen' }),
    ).toBeVisible();
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    expect(within(nav).getByRole('link', { name: 'Mein Bereich' })).toHaveAttribute(
      'href',
      '/patient',
    );
    expect(within(nav).queryByRole('link', { name: 'Mein Check-in' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Arbeitsliste' })).not.toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Einstellungen' })).not.toBeInTheDocument();
  });

  it.each([
    ['Ärztin', CLINICIAN],
    ['Admin', ADMIN],
  ])('führt %s auf die (leere) Arbeitsliste mit genau einer h1', async (_label, account) => {
    serveAs(account);
    renderApp('/clinic');
    expect(await screen.findByRole('heading', { level: 1, name: 'Arbeitsliste' })).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(await screen.findByText('Noch keine Einträge')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    expect(within(nav).getByRole('link', { name: 'Mein Bereich' })).toHaveAttribute(
      'href',
      '/clinic',
    );
    expect(within(nav).queryByRole('link', { name: 'Mein Check-in' })).not.toBeInTheDocument();
    // kein zweiter Eintrag zur Arbeitsliste neben „Mein Bereich“; die Einstellungen bleiben
    expect(within(nav).queryByRole('link', { name: 'Arbeitsliste' })).not.toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Einstellungen' })).toHaveAttribute(
      'href',
      '/clinic/settings',
    );
  });

  it('verwehrt der Patientin die Klinikseite und der Ärztin den Check-in (Navigationshilfe)', async () => {
    serveAs(PATIENT);
    const first = renderApp('/clinic');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
    first.unmount();

    serveAs(CLINICIAN);
    renderApp('/patient');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('leitet Nicht-Angemeldete auf die Anmeldung um', async () => {
    serveAs(null);
    renderApp('/patient');
    expect(await screen.findByRole('heading', { level: 1, name: 'Anmelden' })).toBeVisible();
  });
});
