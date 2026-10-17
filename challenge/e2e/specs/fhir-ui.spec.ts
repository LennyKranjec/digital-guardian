import { expect, test, type Page, type Route } from '@playwright/test';

import {
  API,
  getJson,
  horizontalOverflow,
  openContext,
  smallTargets,
  smallText,
  warmTriage,
} from '../support/helpers';
import type { Row } from '../support/types';

/**
 * FHIR-Export und -Push im Cockpit (F-13) im echten Browser: Knöpfe je Rolle, Statuszeile, Überstand,
 * Schrift, Touchziele, Erstbildschirm S5 und Kopfnavigation (fix/nav-wrap) bei 375 px. `GET …/fhir?type=
 * transaction` und `POST …/fhir/push` (openapi v2.6) werden mit `page.route` GEMOCKT, solange das Backend
 * (T-18) fehlt; Anmeldung und übrige Anfragen sind echt.
 */
test.beforeAll(async ({ browser }, info) => {
  test.setTimeout(240_000);
  await warmTriage(browser, String(info.project.use.baseURL)); // Kaltstart blockiert sonst die ersten Seiten
});

const MOBILE = { width: 375, height: 800 };
const DESKTOP = { width: 1366, height: 768 };
const CONTROLS = 'button, input:not([type=radio]):not([type=checkbox]), select, textarea, summary';

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

async function mockFhir(page: Page, pushes: string[]): Promise<void> {
  await page.route(/\/api\/v1\/waechter\/patients\/[^/]+\/fhir\?type=transaction$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/fhir+json',
      body: JSON.stringify({ resourceType: 'Bundle', type: 'transaction', entry: [] }),
    }),
  );
  await page.route(/\/api\/v1\/waechter\/patients\/[^/]+\/fhir\/push$/, (route) => {
    pushes.push(route.request().method());
    return json(route, {
      status: 'sent',
      http_status: 200,
      entries: 12,
      created: 9,
      updated: 3,
      errors: [],
    });
  });
}

async function openCockpit(page: Page): Promise<void> {
  const rows = await getJson<Row[]>(page.request, `${API}/patients`);
  const red = rows.find((row) => row.pseudonym === 'SYN-0001');
  await page.goto(`/clinic/patients/${red?.patient_id ?? ''}`);
  await expect(page.getByTestId('cockpit-header')).toBeVisible();
}

for (const [label, viewport] of [
  ['375 px', MOBILE],
  ['1366×768', DESKTOP],
] as const) {
  test(`Administration bei ${label}: Transaction-Bundle und „An FHIR-Server senden“, kein Überstand, ≥ 16 px, ≥ 44 px, S5 bleibt`, async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'admin',
      viewport,
    );
    const pushes: string[] = [];
    try {
      await mockFhir(page, pushes);
      await openCockpit(page);
      const actions = page.getByTestId('fhir-panel');
      await page.getByTestId('cockpit-tab-export').click(); // Tab „Export“ (T-32)
      await actions.locator('summary').click();
      await expect(
        actions.getByRole('button', { name: 'Transakční balíček (JSON)' }),
      ).toBeVisible();
      const push = actions.getByRole('button', { name: 'Odeslat na server FHIR' });
      await expect(push).toBeVisible();

      // Erstbildschirm S5 (nur Desktop): Kopf, Kurzfassung, Verlauf bleiben im ersten Bildschirm
      if (label === '1366×768') {
        await page.evaluate(() => window.scrollTo(0, 0));
        for (const id of ['cockpit-header', 'summary-panel', 'timeline-compact']) {
          const box = await page.getByTestId(id).boundingBox();
          expect(box, `${id} fehlt`).not.toBeNull();
          if (box)
            expect(box.y + box.height, `${id} unterhalb von 768 px`).toBeLessThanOrEqual(768);
        }
      }

      await push.click();
      await expect(page.getByTestId('push-status')).toContainText('Odesláno: 12 záznamů');
      expect(pushes).toEqual(['POST']);

      expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect.soft(await smallTargets(page, CONTROLS), 'Ziele < 44 px').toEqual([]);
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    } finally {
      await context.close();
    }
  });
}

test('Ärztin sieht das Transaction-Bundle, aber keinen Push-Knopf', async ({ browser }, info) => {
  const { context, page } = await openContext(
    browser,
    String(info.project.use.baseURL),
    'doctor',
    DESKTOP,
  );
  try {
    await mockFhir(page, []);
    await openCockpit(page);
    const actions = page.getByTestId('fhir-panel');
    await page.getByTestId('cockpit-tab-export').click(); // Tab „Export“ (T-32)
    await actions.locator('summary').click();
    await expect(actions.getByRole('button', { name: 'Transakční balíček (JSON)' })).toBeVisible();
    await expect(actions.getByRole('button', { name: 'Odeslat na server FHIR' })).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('Kopfnavigation bei 375 px: Eintrag „Léčiva“ vorhanden, kein Überstand (fix/nav-wrap)', async ({
  browser,
}, info) => {
  const { context, page } = await openContext(
    browser,
    String(info.project.use.baseURL),
    'doctor',
    MOBILE,
  );
  try {
    await page.goto('/clinic');
    const nav = page.getByRole('navigation', { name: /./ }).first();
    await expect(page.getByRole('link', { name: 'Léčiva' }).first()).toBeVisible();
    await expect(nav).toBeAttached();
    expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
    expect
      .soft(await smallTargets(page, 'header a, nav a'), 'Navigationsziele < 44 px')
      .toEqual([]);
  } finally {
    await context.close();
  }
});
