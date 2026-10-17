import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { callUrl, langOf, serve, setViewport } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

/**
 * Das Backend lokalisiert Meldungstexte, Begriffe und Regime nach `?lang=` (Standard cs). Jede
 * Ärztin-Abfrage muss daher die aktive UI-Sprache mitschicken (F-INT: Abweichung vom Vertragstext,
 * der `lang` nur beim Fragebogen nennt).
 */

type Calls = ReturnType<typeof serve>['mock']['calls'];

/** Sprache der ersten Anfrage, deren Pfad (ohne lang) auf `suffix` endet. */
function langFor(calls: Calls, suffix: string, method = 'GET'): string | null | undefined {
  const call = calls.find(
    ([url, init]) =>
      (callUrl(url).split('?')[0] ?? '').endsWith(suffix) && (init?.method ?? 'GET') === method,
  );
  return call ? langOf(call[0]) : undefined;
}

beforeEach(() => {
  register(pluginApi);
  setViewport(false);
  localStorage.clear();
  vi.setSystemTime(new Date(ANCHOR));
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  resetRegistry();
  localStorage.clear();
  await i18n.changeLanguage('de');
});

describe.each([['de'], ['en'], ['cs']] as const)('Ärztin-Abfragen mit UI-Sprache %s', (lang) => {
  beforeEach(async () => {
    await i18n.changeLanguage(lang);
  });

  it('schickt lang an Arbeitsliste', async () => {
    const fetchMock = serve();
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    expect(langFor(fetchMock.mock.calls, '/waechter/patients')).toBe(lang);
  });

  it('schickt lang an Übersicht, Verlauf, Beleg, Kurzfassung und Quittieren', async () => {
    const fetchMock = serve();
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await screen.findByTestId('cockpit-header');
    await screen.findByTestId('timeline-body');
    await user.click(screen.getAllByTestId('chart-item')[0] as HTMLElement);
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');

    const calls = fetchMock.mock.calls;
    expect(langFor(calls, '/patients/pat-1/overview')).toBe(lang);
    expect(langFor(calls, '/patients/pat-1/timeline')).toBe(lang);
    expect(calls.some(([url]) => callUrl(url).includes('/facts/') && langOf(url) === lang)).toBe(
      true,
    );
  });

  it('schickt lang an Meldungsdetail, Quittieren und Aufnahme-Vorlage', async () => {
    const fetchMock = serve();
    const user = userEvent.setup();
    renderApp('/clinic/alerts/al-1');
    await screen.findByTestId('alert-card');
    await user.click(
      screen.getByRole('button', { name: i18nText('waechter.clinic.actions.acknowledge') }),
    );
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getAllByRole('radio')[0] as HTMLElement);
    await user.click(dialog.getByRole('button', { name: i18nText('waechter.clinic.ack.confirm') }));
    await screen.findByTestId('alert-notice');
    expect(langFor(fetchMock.mock.calls, '/alerts/al-1')).toBe(lang);
    expect(langFor(fetchMock.mock.calls, '/alerts/al-1/acknowledge', 'POST')).toBe(lang);
  });

  it('schickt lang an die Aufnahme-Vorlage', async () => {
    const fetchMock = serve();
    renderApp('/clinic/patients/pat-1/assess');
    await screen.findByTestId('assessment-form');
    expect(langFor(fetchMock.mock.calls, '/patients/pat-1/assessment-template')).toBe(lang);
  });
});

describe('Sprachwechsel', () => {
  it('lädt die Arbeitsliste in der neuen Sprache neu', async () => {
    const fetchMock = serve();
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const before = fetchMock.mock.calls.filter(([url]) =>
      callUrl(url).endsWith('/waechter/patients'),
    );
    expect(before.map(([url]) => langOf(url))).toEqual(['de']);

    await i18n.changeLanguage('en');
    await vi.waitFor(() => {
      const langs = fetchMock.mock.calls
        .filter(([url]) => callUrl(url).endsWith('/waechter/patients'))
        .map(([url]) => langOf(url));
      expect(langs).toEqual(['de', 'en']);
    });
  });
});

function i18nText(key: string): string {
  return i18n.t(key);
}
