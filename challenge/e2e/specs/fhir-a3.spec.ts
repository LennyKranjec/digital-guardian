import { expect, test, type Page, type Route } from '@playwright/test';

import { API, getJson, horizontalOverflow, openContext, warmTriage } from '../support/helpers';
import type { Row } from '../support/types';

/**
 * A3-Gegenproben zu F-13 (FHIR Transaction-Bundle und Push im Cockpit) gegen EIGENE Attrappen der
 * Endpunkte nach openapi v2.6 (`page.route`): kein Senden ohne Klick, genau ein Versand beim
 * Doppelklick, jede Fehlerart ehrlich benannt, feindliche Servertexte nur als Text, nichts in
 * Konsole oder Dateiname, was Patientendaten verrät. Das echte Backend (T-18) fehlt noch.
 */
const DESKTOP = { width: 1366, height: 768 };
const MOBILE = { width: 375, height: 800 };
const PUSH = /\/api\/v1\/waechter\/patients\/[^/]+\/fhir\/push$/;
const TRANSACTION = /\/api\/v1\/waechter\/patients\/[^/]+\/fhir\?type=transaction$/;
const BUTTON = 'Odeslat na server FHIR';

type Json = Record<string, unknown>;

test.beforeAll(async ({ browser }, info) => {
  test.setTimeout(240_000);
  await warmTriage(browser, String(info.project.use.baseURL)); // Kaltstart der Triage nicht im Testzeitlimit
});

async function cockpit(page: Page): Promise<string> {
  const rows = await getJson<Row[]>(page.request, `${API}/patients`);
  const row = rows.find((r) => r.pseudonym === 'SYN-0001');
  await page.goto(`/clinic/patients/${row?.patient_id ?? ''}`);
  await expect(page.getByTestId('cockpit-header')).toBeVisible();
  return row?.patient_id ?? '';
}

async function open(page: Page): Promise<void> {
  await page.getByTestId('cockpit-tab-export').click(); // Tab „Export“ (T-32)
  await page.getByTestId('fhir-panel').locator('summary').click();
}

const reply = (route: Route, status: number, body: Json) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

test.describe('FHIR-Push (Administration)', () => {
  test('nichts wird ohne Klick gesendet; Doppelklick sendet genau einmal', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'admin',
      DESKTOP,
    );
    const pushes: string[] = [];
    try {
      await page.route(PUSH, async (route) => {
        pushes.push(route.request().method());
        await new Promise((resolve) => setTimeout(resolve, 700));
        await reply(route, 200, { status: 'sent', http_status: 200, entries: 4, created: 4 });
      });
      await cockpit(page);
      await open(page);
      await page.waitForTimeout(500);
      expect(pushes, 'Versand ohne Klick').toEqual([]);
      await page.getByRole('button', { name: BUTTON }).dblclick();
      await expect(page.getByTestId('push-status')).toHaveAttribute('data-outcome', 'sent');
      expect(pushes).toEqual(['POST']);
    } finally {
      await context.close();
    }
  });

  const CASES: [string, number, Json, string][] = [
    ['nicht konfiguriert', 200, { status: 'disabled' }, 'disabled'],
    [
      'Server lehnt ab',
      200,
      { status: 'failed', http_status: 422, errors: ['Ressource ungültig'] },
      'failed',
    ],
    ['nicht synthetisch', 409, { code: 'not_synthetic', message: 'x' }, 'notSynthetic'],
    ['keine Berechtigung', 403, { code: 'forbidden', message: 'x' }, 'forbidden'],
    ['Route fehlt', 404, { code: 'not_found', message: 'x' }, 'unavailable'],
    ['Serverfehler', 500, { code: 'boom', message: 'Stacktrace at line 1' }, 'generic'],
  ];
  for (const [label, status, body, outcome] of CASES) {
    test(`Ausgang „${label}“ wird als eigener Zustand gezeigt, ohne Rohtext`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'admin',
        MOBILE,
      );
      try {
        await page.route(PUSH, (route) => reply(route, status, body));
        await cockpit(page);
        await open(page);
        await page.getByRole('button', { name: BUTTON }).click();
        const state = page.getByTestId('push-status');
        await expect(state).toHaveAttribute('data-outcome', outcome);
        const text = (await state.innerText()).trim();
        expect(text.length).toBeGreaterThan(0);
        expect(text).not.toMatch(/Stacktrace|\{|undefined|\[object|NaN/);
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
        // nach einem Fehler ist erneutes Senden möglich (Knopf nicht dauerhaft gesperrt)
        await expect(page.getByRole('button', { name: BUTTON })).toBeEnabled();
      } finally {
        await context.close();
      }
    });
  }

  test('Netzfehler wird benannt; feindlicher Servertext wird gekürzt und nur als Text gezeigt', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'admin',
      MOBILE,
    );
    try {
      let mode: 'network' | 'evil' = 'network';
      const evil = `<img src=x onerror="window.__pwned=1">${'A'.repeat(400)}`;
      await page.route(PUSH, (route) =>
        mode === 'network'
          ? route.abort('failed')
          : reply(route, 200, { status: 'failed', http_status: 400, errors: [evil, 'zweiter'] }),
      );
      await cockpit(page);
      await open(page);
      await page.getByRole('button', { name: BUTTON }).click();
      await expect(page.getByTestId('push-status')).toHaveAttribute('data-outcome', 'network');
      mode = 'evil';
      await page.getByRole('button', { name: BUTTON }).click();
      const state = page.getByTestId('push-status');
      await expect(state).toHaveAttribute('data-outcome', 'failed');
      expect((await state.innerText()).length).toBeLessThan(400);
      expect(await state.innerText()).not.toContain('zweiter');
      await expect(page.locator('img[src="x"]')).toHaveCount(0);
      expect(
        await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
      ).toBeUndefined();
    } finally {
      await context.close();
    }
  });
});

test.describe('Transaction-Bundle', () => {
  test('Dateiname nur aus dem Pseudonym; Inhalt erscheint weder in der Konsole noch im DOM', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    const logs: string[] = [];
    page.on('console', (message) => logs.push(message.text()));
    try {
      const secret = 'GEHEIM-A3-INHALT';
      await page.route(TRANSACTION, (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/fhir+json',
          body: JSON.stringify({ resourceType: 'Bundle', type: 'transaction', note: secret }),
        }),
      );
      await cockpit(page);
      await open(page);
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: 'Transakční balíček (JSON)' }).click();
      const file = await download;
      expect(file.suggestedFilename()).toMatch(/^SYN-0001-transaction-bundle\.json$/);
      expect(file.suggestedFilename()).not.toMatch(/Alena|Dem/i);
      expect(logs.join('\n')).not.toContain(secret);
      expect(await page.locator('body').innerText()).not.toContain(secret);
    } finally {
      await context.close();
    }
  });

  test('Patientinnen erreichen die Aktionen nie; Ärztin sieht keinen Push', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      MOBILE,
    );
    const calls: string[] = [];
    try {
      await page.route(/\/fhir/, (route) => {
        calls.push(route.request().url());
        return route.fallback();
      });
      await page.goto('/clinic');
      await page.waitForLoadState('networkidle');
      expect(calls.filter((url) => url.includes('/api/v1/'))).toEqual([]);
      await expect(page.getByRole('button', { name: BUTTON })).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
});
