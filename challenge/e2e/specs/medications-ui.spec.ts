import { expect, test, type Page, type Route } from '@playwright/test';

import {
  API,
  getJson,
  horizontalOverflow,
  openContext,
  smallTargets,
  smallText,
} from '../support/helpers';
import type { Row } from '../support/types';

/**
 * Arzneimittelsuche der Ärztin (F-12) im echten Browser: Suche per Name/Nummer/ATC, Überstand, Schrift,
 * Touchziele, Tastatur, S5 unverändert. `GET /medications` (openapi v2.3) wird mit `page.route` GEMOCKT,
 * solange das Backend (T-17) fehlt; geprüft wird nur die Oberfläche. Anmeldung und übrige Anfragen sind echt.
 */
const MOBILE = { width: 375, height: 800 };
const DESKTOP = { width: 1366, height: 768 };
const CONTROLS =
  'button, input:not([type=radio]):not([type=checkbox]), select, textarea, label:has(input), summary';

const OXALIPLATIN = {
  medication_id: 'MED-OXALIPLATIN-ACCORD',
  inn: 'oxaliplatin',
  trade_name: 'Oxaliplatin Accord 5 mg/ml',
  sukl_code: '0239968',
  atc: 'L01XA03',
  status: 'reviewed',
  regimens: [
    {
      regimen_id: 'FOLFOX',
      label: 'FOLFOX (oxaliplatin, fluorouracil, kalciumfolinát)',
      symptom_keys: ['nausea', 'fever', 'fatigue', 'peripheral_neuropathy'],
    },
  ],
  spc: {
    title: 'Oxaliplatin Accord – souhrn údajů o přípravku (SÚKL)',
    url: 'https://prehledy.sukl.cz/',
  },
  match: 'name',
  patients_on_regimen: 2,
};
const FOLINATE = {
  medication_id: 'MED-CALCIUM-FOLINATE',
  inn: 'kalcium-folinát',
  trade_name: null,
  sukl_code: null,
  atc: 'V03AF03',
  status: 'draft',
  regimens: [{ regimen_id: 'FOLFOX', label: 'FOLFOX', symptom_keys: ['nausea'] }],
  spc: null,
  match: 'synonym',
  patients_on_regimen: 2,
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

async function mockMedications(page: Page, queries: string[]): Promise<void> {
  await page.route(/\/api\/v1\/waechter\/medications\/MED-[^?]*(\?.*)?$/, (route) =>
    json(route, OXALIPLATIN),
  );
  await page.route(/\/api\/v1\/waechter\/medications\?.*$/, (route) => {
    const q = new URL(route.request().url()).searchParams.get('q') ?? '';
    queries.push(q);
    if (q.length < 2)
      return json(route, { code: 'validation_error', message: 'q', field_errors: [] }, 422);
    return json(route, q === 'nix' ? [] : [OXALIPLATIN, FOLINATE]);
  });
}

for (const [label, viewport] of [
  ['375 px', MOBILE],
  ['1366×768', DESKTOP],
] as const) {
  test(`Arzneimittelsuche bei ${label}: Name, Nummer, ATC, Leerzustand; kein Überstand, ≥ 16 px, ≥ 44 px`, async ({
    browser,
  }, info) => {
    const baseURL = String(info.project.use.baseURL);
    const { context, page } = await openContext(browser, baseURL, 'doctor', viewport);
    const queries: string[] = [];
    try {
      await mockMedications(page, queries);
      await page.goto('/clinic/medications');
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      const field = page.getByRole('searchbox', { name: 'Léčivo – název, kód SÚKL nebo ATC' });
      await expect(field).toBeVisible();
      expect(await horizontalOverflow(page), 'Überstand (leer)').toBeLessThanOrEqual(0);

      // Name (Debounce), dann Nummer und ATC per Enter
      await field.fill('oxali');
      await expect(page.getByTestId('medication-card')).toHaveCount(2);
      await field.fill('0239968');
      await field.press('Enter');
      await expect.poll(() => queries.includes('0239968')).toBe(true);
      await field.fill('L01XA');
      await field.press('Enter');
      await expect.poll(() => queries.includes('L01XA')).toBe(true);
      await expect(page.getByTestId('medication-card').first()).toBeVisible();
      // ein Zeichen ⇒ keine Anfrage
      const before = queries.length;
      await field.fill('o');
      await page.waitForTimeout(450);
      expect(queries.length).toBe(before);

      // Treffer: alle Angaben, SPC-Link im neuen Tab
      await field.fill('oxaliplatin');
      await field.press('Enter');
      const first = page.getByTestId('medication-card').first();
      await expect(first.getByTestId('medication-sukl')).toHaveText('0239968');
      await expect(first.getByTestId('medication-atc')).toHaveText('L01XA03');
      await expect(first.getByTestId('medication-match')).toContainText('název');
      const spc = first.getByTestId('medication-spc').getByRole('link');
      await expect(spc).toHaveAttribute('target', '_blank');
      await expect(spc).toHaveAttribute('rel', /noopener/);
      await expect(page.getByTestId('medication-note')).toContainText('ne úplný registr SÚKL');
      expect(await horizontalOverflow(page), 'Überstand (Treffer)').toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect.soft(await smallTargets(page, `${CONTROLS}, main a`), 'Ziele < 44 px').toEqual([]);

      // Leerzustand
      await field.fill('nix');
      await field.press('Enter');
      await expect(page.getByTestId('medication-empty')).toBeVisible();
      expect(await horizontalOverflow(page), 'Überstand (leer)').toBeLessThanOrEqual(0);
    } finally {
      await context.close();
    }
  });

  test(`Arzneimittel-Detail bei ${label}: eine h1, kein Überstand, ≥ 16 px, ≥ 44 px`, async ({
    browser,
  }, info) => {
    const baseURL = String(info.project.use.baseURL);
    const { context, page } = await openContext(browser, baseURL, 'doctor', viewport);
    try {
      await mockMedications(page, []);
      await page.goto('/clinic/medications/MED-OXALIPLATIN-ACCORD');
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(
        'Oxaliplatin Accord 5 mg/ml',
      );
      await expect(page.getByTestId('medication-card')).toBeVisible();
      await expect(page.getByTestId('medication-match')).toHaveCount(0);
      expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect.soft(await smallTargets(page, `${CONTROLS}, main a`), 'Ziele < 44 px').toEqual([]);
    } finally {
      await context.close();
    }
  });
}

test('Arbeitsliste: Link zur Arzneimittelsuche bei 375 px ohne Überstand (kein fünfter Navigationseintrag)', async ({
  browser,
}, info) => {
  const baseURL = String(info.project.use.baseURL);
  const { context, page } = await openContext(browser, baseURL, 'doctor', MOBILE);
  try {
    await page.goto('/clinic');
    const link = page.getByTestId('medications-link');
    await expect(link).toBeVisible();
    expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
    await link.click();
    await expect(page).toHaveURL(/\/clinic\/medications$/);
    await expect(page.getByRole('searchbox')).toBeVisible();
  } finally {
    await context.close();
  }
});

test('Cockpit: Wirkstoff-Link führt zur Suche; Erstbildschirm von SYN-0001 bleibt (S5)', async ({
  browser,
}, info) => {
  const baseURL = String(info.project.use.baseURL);
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  const queries: string[] = [];
  try {
    await mockMedications(page, queries);
    const rows = await getJson<Row[]>(page.request, `${API}/patients`);
    const red = rows.find((row) => row.pseudonym === 'SYN-0001');
    await page.goto(`/clinic/patients/${red?.patient_id ?? ''}`);
    await expect(page.getByTestId('cockpit-header')).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    for (const id of ['cockpit-header', 'summary-panel', 'timeline-compact']) {
      const box = await page.getByTestId(id).boundingBox();
      expect(box, `${id} fehlt`).not.toBeNull();
      if (box) expect(box.y + box.height, `${id} unterhalb von 768 px`).toBeLessThanOrEqual(768);
    }
    await page.getByTestId('header-more').locator('summary').click();
    const link = page.getByTestId('header-more').getByRole('link').first();
    await expect(link).toHaveAttribute('href', /\/clinic\/medications\?q=/);
    await link.click();
    await expect(page).toHaveURL(/\/clinic\/medications\?q=/);
    await expect(page.getByTestId('medication-card').first()).toBeVisible();
    await expect(page.getByRole('searchbox')).not.toHaveValue('');
  } finally {
    await context.close();
  }
});
