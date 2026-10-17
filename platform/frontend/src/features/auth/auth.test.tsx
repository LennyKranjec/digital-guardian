import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Outlet } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { registerRoutes, resetRegistry } from '../../registry';
import {
  ADMIN,
  USER,
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../../test/render';
import { RequireRole } from './RequireRole';

afterEach(() => {
  vi.unstubAllGlobals();
  resetRegistry();
});

describe('Anmeldung', () => {
  it('meldet über die Demo-Schnellauswahl an (füllt nur die Felder) und zeigt Name und Rolle', async () => {
    let loggedIn = false;
    const fetchMock = mockFetch((url, init) => {
      if (url.endsWith('/auth/login') && init?.method === 'POST') {
        loggedIn = true;
        return jsonResponse(ADMIN);
      }
      if (url.endsWith('/auth/me')) return loggedIn ? jsonResponse(ADMIN) : defaultApiResponse(url);
      return defaultApiResponse(url);
    });
    const user = userEvent.setup();
    renderApp('/login');
    await user.click(await screen.findByTestId('demo-account-admin'));
    expect(screen.getByLabelText('Benutzername')).toHaveValue('admin');
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Anmelden' }));
    expect(await screen.findByTestId('session-info')).toHaveTextContent('Admin (Demo)');
    expect(screen.getByTestId('session-info')).toHaveTextContent('Administration');
  });

  it('zeigt bei falschen Zugangsdaten eine Meldung ohne Details', async () => {
    mockFetch((url, init) =>
      url.endsWith('/auth/login') && init?.method === 'POST'
        ? jsonResponse({ code: 'invalid_credentials', message: 'x', field_errors: [] }, 401)
        : defaultApiResponse(url),
    );
    const user = userEvent.setup();
    renderApp('/login');
    await user.type(await screen.findByLabelText('Benutzername'), 'admin');
    await user.type(screen.getByLabelText('Passwort'), 'falsch');
    await user.click(screen.getByRole('button', { name: 'Anmelden' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Benutzername oder Passwort stimmt nicht.',
    );
  });

  it('hat genau eine h1 und beschriftete Felder', async () => {
    mockFetch(defaultApiResponse);
    renderApp('/login');
    expect(await screen.findByLabelText('Passwort')).toHaveAttribute('type', 'password');
    expect(screen.getByLabelText('Benutzername')).toBeRequired();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });
});

describe('Rollenwächter (nur Navigationshilfe, Autorisierung liegt im Backend)', () => {
  function guarded() {
    registerRoutes({
      element: <RequireRole roles={['admin']} />,
      children: [
        { path: 'secret', element: <h1>Geheim</h1> },
        { path: 'outlet', element: <Outlet /> },
      ],
    });
  }

  it('leitet nicht Angemeldete zur Anmeldung um', async () => {
    guarded();
    mockFetch(defaultApiResponse);
    renderApp('/secret');
    expect(await screen.findByLabelText('Benutzername')).toBeInTheDocument();
    expect(screen.queryByText('Geheim')).not.toBeInTheDocument();
  });

  it('zeigt Personen mit falscher Rolle „Kein Zugriff“', async () => {
    guarded();
    mockFetch((url) => (url.endsWith('/auth/me') ? jsonResponse(USER) : defaultApiResponse(url)));
    renderApp('/secret');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
    expect(screen.queryByText('Geheim')).not.toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('lässt Personen mit passender Rolle durch', async () => {
    guarded();
    mockFetch((url) => (url.endsWith('/auth/me') ? jsonResponse(ADMIN) : defaultApiResponse(url)));
    renderApp('/secret');
    expect(await screen.findByRole('heading', { level: 1, name: 'Geheim' })).toBeVisible();
  });
});
