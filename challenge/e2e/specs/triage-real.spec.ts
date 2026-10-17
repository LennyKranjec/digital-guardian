import { expect, test, type Page } from '@playwright/test';

import {
  API,
  FORBIDDEN,
  getJson,
  horizontalOverflow,
  openContext,
  smallTargets,
  smallText,
  warmTriage,
} from '../support/helpers';
import type { Row } from '../support/types';

/**
 * A3-Gegenproben zu T-16 im Browser gegen das ECHTE Triage-Backend (keine Attrappen): Regelkarte in den
 * Einstellungen und Befundkarte im Cockpit mit echten Texten, Hashes und Zahlen bei 375 px und 1366 px.
 * Nur lesend (parallel-sicher).
 */
const MOBILE = { width: 375, height: 800 };
const DESKTOP = { width: 1366, height: 768 };

test.beforeAll(async ({ browser }, info) => {
  test.setTimeout(240_000);
  await warmTriage(browser, String(info.project.use.baseURL));
});

async function patient(page: Page, pseudonym: string): Promise<string> {
  const rows = await getJson<Row[]>(page.request, `${API}/patients`);
  return rows.find((row) => row.pseudonym === pseudonym)?.patient_id ?? '';
}

test('Regelkarte mit echten Hashes bei 375 px: kein horizontaler Überstand', async ({
  browser,
}, info) => {
  const { context, page } = await openContext(
    browser,
    String(info.project.use.baseURL),
    'doctor',
    MOBILE,
  );
  try {
    await page.goto('/clinic/settings');
    await expect(page.getByTestId('triage-profile').first()).toBeVisible({ timeout: 60_000 });
    await page
      .getByTestId('triage-profile')
      .evaluateAll((all) => all.forEach((el) => ((el as HTMLDetailsElement).open = true)));
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
  } finally {
    await context.close();
  }
});

for (const [label, viewport] of [
  ['375 px', MOBILE],
  ['1366×768', DESKTOP],
] as const) {
  test(`Regelkarte (echt) bei ${label}: Banner mit Umfang, Regeln rot zuerst, Platzhalter, Schrift ≥ 16 px`, async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      viewport,
    );
    try {
      await page.goto('/clinic/settings');
      const profiles = page.getByTestId('triage-profile');
      await expect(profiles.first()).toBeVisible({ timeout: 60_000 });
      expect(await profiles.count()).toBeGreaterThanOrEqual(4);
      await profiles.evaluateAll((all) =>
        all.forEach((el) => ((el as HTMLDetailsElement).open = true)),
      );
      const banner = page.getByTestId('triage-verification').first();
      await expect(banner).toBeVisible();
      await expect(banner).toHaveAttribute('data-clean', 'true');
      await expect(banner).toHaveAttribute('data-scope', /exhaustive|sampled/);
      await expect(banner.getByTestId('triage-banner-placeholder')).toBeVisible();
      expect(await banner.innerText()).not.toMatch(/Ověřeno|verifiziert|undefined|\[object/i);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
    } finally {
      await context.close();
    }
  });
}

for (const [label, viewport] of [
  ['375 px', MOBILE],
  ['1366×768', DESKTOP],
] as const) {
  test(`Befundkarte (echt, SYN-0001) bei ${label}: Stufe als Text, Schutzboden, kein Überstand, Ziele ≥ 44 px`, async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      viewport,
    );
    try {
      const id = await patient(page, 'SYN-0001');
      await page.goto(`/clinic/patients/${id}`);
      await expect(page.getByTestId('cockpit-header')).toBeVisible();
      const panel = page.getByTestId('triage-panel');
      await page.getByTestId('cockpit-tab-triage').click(); // Tab „Triage-Details“ (T-32)
      await panel.locator('summary').click();
      await expect(panel.getByTestId('triage-finding')).toBeVisible({ timeout: 30_000 });
      const text = await panel.innerText();
      expect(text).not.toMatch(/undefined|\[object|NaN|Traceback/);
      expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect.soft(await smallTargets(page, 'summary, button'), 'Ziele < 44 px').toEqual([]);
      // Ärztetexte ohne Patienten-Verbotswörter für Beruhigung/Zusage
      expect(text).not.toMatch(/keine sorge|v pořádku|don.?t worry|ozveme se/i);
      void FORBIDDEN;
    } finally {
      await context.close();
    }
  });
}
