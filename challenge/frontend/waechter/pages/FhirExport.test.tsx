import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import {
  BASE,
  ERROR_BODY,
  callUrl,
  serve,
  setViewport,
  type ServeOptions,
} from '../testing/cockpit-server';
import { ADMIN, ANCHOR, CLINICIAN } from '../testing/fixtures';

const TX = 'Transaction-Bundle (JSON)';
const PUSH = 'An FHIR-Server senden';

let downloads: string[];

beforeEach(() => {
  register(pluginApi);
  setViewport(false);
  localStorage.clear();
  vi.setSystemTime(new Date(ANCHOR));
  downloads = [];
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: vi.fn(() => 'blob:test'),
  });
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    downloads.push(this.download);
  });
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  resetRegistry();
  localStorage.clear();
  await i18n.changeLanguage('de');
});

async function openCockpit(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  const toolbar = within(await screen.findByTestId('cockpit-actions'));
  await user.click(await screen.findByTestId('cockpit-tab-export')); // Tab „Export“ (T-32)
  // Transaction-Bundle und Push stehen im eingeklappten Bereich unter dem Raster (S5 bleibt unverändert)
  const panel = await screen.findByTestId('fhir-panel');
  expect(panel).not.toHaveAttribute('open'); // eingeklappt, bis die Ärztin es öffnet
  await user.click(panel.querySelector('summary') as HTMLElement);
  const actions = within(panel);
  return { fetchMock, user, actions, toolbar };
}

const calls = (fetchMock: ReturnType<typeof serve>, url: string) =>
  fetchMock.mock.calls.filter(([input]) => callUrl(input) === url);

describe('FHIR-Export im Cockpit (F-13)', () => {
  it('zeigt Ärztin beide Downloads, aber keinen „An FHIR-Server senden“-Knopf', async () => {
    const { actions, toolbar } = await openCockpit({ me: CLINICIAN });
    // der bisherige Export bleibt in der Aktionsleiste, das Transaction-Bundle steht im Bereich darunter
    expect(toolbar.getByRole('button', { name: 'FHIR-Bundle (JSON)' })).toBeEnabled();
    expect(toolbar.queryByRole('button', { name: TX })).toBeNull();
    expect(actions.getByRole('button', { name: TX })).toBeEnabled();
    expect(actions.queryByRole('button', { name: PUSH })).toBeNull();
  });

  it('zeigt der Administration zusätzlich „An FHIR-Server senden“', async () => {
    const { actions } = await openCockpit({ me: ADMIN });
    expect(await actions.findByRole('button', { name: PUSH })).toBeEnabled();
    expect(actions.getByRole('button', { name: TX })).toBeEnabled();
  });

  it('lädt das Transaction-Bundle über ?type=transaction als <pseudonym>-transaction-bundle.json', async () => {
    const { fetchMock, user, actions } = await openCockpit();
    await user.click(actions.getByRole('button', { name: TX }));
    expect(
      await screen.findByText('Gespeichert als SYN-0001-transaction-bundle.json'),
    ).toBeInTheDocument();
    expect(downloads).toEqual(['SYN-0001-transaction-bundle.json']);
    expect(calls(fetchMock, `${BASE}/fhir?type=transaction`)).toHaveLength(1);
    expect(calls(fetchMock, `${BASE}/fhir`)).toHaveLength(0); // Standard-Export unverändert und getrennt
    expect(screen.getByTestId('export-tx-status')).toHaveTextContent('transaction-bundle.json');
    expect(screen.getByTestId('export-status')).toHaveTextContent(''); // Status je Knopf getrennt
  });

  it('lässt den Standard-Export bei type=collection (ohne Parameter) wie bisher', async () => {
    const { fetchMock, user, toolbar } = await openCockpit();
    await user.click(toolbar.getByRole('button', { name: 'FHIR-Bundle (JSON)' }));
    expect(await screen.findByText('Gespeichert als SYN-0001-bundle.json')).toBeInTheDocument();
    expect(calls(fetchMock, `${BASE}/fhir`)).toHaveLength(1);
    expect(calls(fetchMock, `${BASE}/fhir?type=transaction`)).toHaveLength(0);
  });

  it('meldet beim Transaction-Bundle 404 als „Export noch nicht verfügbar“ und andere Fehler als Fehlschlag', async () => {
    let attempt = 0;
    const { user, actions } = await openCockpit({
      fhirTransaction: () => {
        attempt += 1;
        return attempt === 1
          ? jsonResponse(ERROR_BODY('not_found'), 404)
          : jsonResponse(ERROR_BODY('boom'), 500);
      },
    });
    await user.click(actions.getByRole('button', { name: TX }));
    expect(await screen.findByText('Export noch nicht verfügbar.')).toBeInTheDocument();
    await user.click(actions.getByRole('button', { name: TX }));
    expect(
      await screen.findByText('Der Export hat nicht geklappt. Bitte versuchen Sie es erneut.'),
    ).toBeInTheDocument();
    expect(downloads).toEqual([]);
  });
});

describe('FHIR-Push (F-13, nur Administration)', () => {
  async function openAdmin(options: ServeOptions = {}) {
    const opened = await openCockpit({ me: ADMIN, ...options });
    const button = await opened.actions.findByRole('button', { name: PUSH });
    return { ...opened, button };
  }

  it('sendet per POST …/fhir/push und zeigt „gesendet“ mit Einträgen, neu und aktualisiert', async () => {
    const { fetchMock, user, button } = await openAdmin();
    await user.click(button);
    const status = await screen.findByText(/Gesendet: 12 Einträge/);
    expect(status).toHaveTextContent('Gesendet: 12 Einträge (9 neu, 3 aktualisiert).');
    expect(screen.getByTestId('push-status')).toHaveAttribute('data-outcome', 'sent');
    const [push] = calls(fetchMock, `${BASE}/fhir/push`);
    expect((push?.[1] as RequestInit).method).toBe('POST');
    expect((push?.[1] as RequestInit).headers).toMatchObject({ 'X-Requested-With': 'fetch' });
  });

  it('zeigt „Kein FHIR-Server konfiguriert“ bei disabled (kein Fehler)', async () => {
    const { user, button } = await openAdmin({
      fhirPush: () => jsonResponse({ status: 'disabled' }),
    });
    await user.click(button);
    const status = await screen.findByText('Kein FHIR-Server konfiguriert.');
    expect(status).toBeVisible();
    expect(screen.getByTestId('push-status')).toHaveAttribute('data-outcome', 'disabled');
  });

  it('zeigt bei failed den Kurztext des Servers und den HTTP-Status', async () => {
    const { user, button } = await openAdmin({
      fhirPush: () =>
        jsonResponse({
          status: 'failed',
          http_status: 401,
          errors: ['Authentifizierung abgelehnt', 'zweiter'],
        }),
    });
    await user.click(button);
    const status = await screen.findByText(/Das Senden ist fehlgeschlagen\./);
    expect(status).toHaveTextContent(
      'Das Senden ist fehlgeschlagen. HTTP 401 · Authentifizierung abgelehnt',
    );
    expect(status).not.toHaveTextContent('zweiter'); // nur der erste Kurztext
    expect(screen.getByTestId('push-status')).toHaveAttribute('data-outcome', 'failed');
  });

  it('kürzt sehr lange Fehlertexte und zeigt failed auch ohne Text', async () => {
    const { user, button } = await openAdmin({
      fhirPush: () => jsonResponse({ status: 'failed', errors: ['x'.repeat(500)] }),
    });
    await user.click(button);
    const status = await screen.findByTestId('push-status');
    await screen.findByText(/Das Senden ist fehlgeschlagen\./);
    expect(status.textContent?.length ?? 0).toBeLessThan(200);
    expect(status.textContent).toContain('…');
  });

  it('zeigt bei failed ohne errors/http_status nur die kurze Meldung', async () => {
    const { user, button } = await openAdmin({
      fhirPush: () => jsonResponse({ status: 'failed' }),
    });
    await user.click(button);
    expect(await screen.findByText('Das Senden ist fehlgeschlagen.')).toBeVisible();
  });

  it('zeigt bei 409 not_synthetic den Hinweis „nur synthetische Daten“ ohne Rohcode', async () => {
    const { user, button } = await openAdmin({
      fhirPush: () => jsonResponse(ERROR_BODY('not_synthetic'), 409),
    });
    await user.click(button);
    const status = await screen.findByText('Es dürfen nur synthetische Daten gesendet werden.');
    expect(status).not.toHaveTextContent('not_synthetic');
    expect(screen.getByTestId('push-status')).toHaveAttribute('data-outcome', 'notSynthetic');
  });

  it.each([
    [403, 'forbidden', 'Für das Senden fehlt die Berechtigung.'],
    [404, 'unavailable', 'Das Senden ist noch nicht verfügbar.'],
    [500, 'generic', 'Das Senden hat nicht geklappt. Bitte versuchen Sie es erneut.'],
  ] as const)('zeigt bei HTTP %i die Meldung „%s“', async (status, outcome, text) => {
    const { user, button } = await openAdmin({
      fhirPush: () => jsonResponse(ERROR_BODY('x'), status),
    });
    await user.click(button);
    expect(await screen.findByText(text)).toBeVisible();
    expect(screen.getByTestId('push-status')).toHaveAttribute('data-outcome', outcome);
  });

  it('zeigt bei einem Netzfehler „Keine Verbindung“ und erlaubt eine Wiederholung', async () => {
    let attempt = 0;
    const { user, button } = await openAdmin({
      fhirPush: () => {
        attempt += 1;
        if (attempt === 1) throw new TypeError('offline');
        return jsonResponse({ status: 'sent', entries: 1, created: 1, updated: 0 });
      },
    });
    await user.click(button);
    expect(await screen.findByText('Keine Verbindung zum Server.')).toBeVisible();
    await user.click(button);
    expect(await screen.findByText(/Gesendet: 1 Einträge/)).toBeVisible();
  });

  it('sperrt den Knopf während des Sendens (kein Doppelversand)', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve({ me: ADMIN });
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (callUrl(input) === `${BASE}/fhir/push`) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await user.click(await screen.findByTestId('cockpit-tab-export'));
    await user.click(await screen.findByRole('button', { name: PUSH }));
    const working = await screen.findByRole('button', { name: 'Wird gesendet …' });
    expect(working).toBeDisabled();
    await user.click(working);
    release?.();
    await screen.findByText(/Gesendet:/);
    expect(calls(fetchMock, `${BASE}/fhir/push`)).toHaveLength(1);
  });

  it('übersetzt Knöpfe und Status (cs/en) ohne Rohschlüssel und ohne verbotene Wendungen', async () => {
    for (const [lang, push, expected] of [
      ['cs', 'Odeslat na server FHIR', /Odesláno: 12 záznamů/],
      ['en', 'Send to FHIR server', /Sent: 12 entries/],
    ] as const) {
      await i18n.changeLanguage(lang);
      const user = userEvent.setup();
      serve({ me: ADMIN });
      const view = renderApp('/clinic/patients/pat-1');
      await user.click(await screen.findByTestId('cockpit-tab-export'));
      await user.click(await screen.findByRole('button', { name: push }));
      const status = await screen.findByText(expected);
      expect(document.body.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
      expect(findForbiddenClinician(status.textContent)).toEqual([]);
      view.unmount();
    }
  });
});
