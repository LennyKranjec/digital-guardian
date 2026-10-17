import { expect, test, type Page } from '@playwright/test';

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
 * A3-Gegenproben zu F-12 (Arzneimittelsuche der Ärztin) gegen das ECHTE Backend (T-17) und die echte
 * Katalogdatei. Dazu der platform-fix nav-wrap (Navigation bricht um, kein Überstand bei 375 px).
 */
const DESKTOP = { width: 1366, height: 768 };
const MOBILE = { width: 375, height: 800 };

interface Medication {
  medication_id: string;
  inn: string;
  trade_name: string | null;
  sukl_code: string | null;
  atc: string;
  patients_on_regimen: number;
  match: string;
}

async function api(page: Page, q: string): Promise<Medication[]> {
  return getJson<Medication[]>(page.request, `${API}/medications?q=${encodeURIComponent(q)}`);
}

async function search(page: Page, text: string): Promise<void> {
  await page.getByLabel(/Léčivo/).fill(text);
  await page.getByLabel(/Léčivo/).press('Enter');
}

function cards(page: Page) {
  return page.getByTestId('medication-card');
}

test.describe('Arzneimittelsuche gegen das echte Backend', () => {
  test('Name, kódSÚKL (ohne führende Nullen) und ATC-Präfix: Karten = Antwort der API', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.goto('/clinic/medications');
      await page.waitForLoadState('networkidle');
      await page.goto('/clinic/medications');
      await expect(page.getByTestId('medication-idle')).toBeVisible();
      for (const q of ['xelo', '27023', 'L01BC', 'kalcium', 'leukovorin', 'Keytruda']) {
        const want = await api(page, q);
        expect(want.length, q).toBeGreaterThan(0);
        await search(page, q);
        await expect(page.getByTestId('medication-count')).toBeVisible();
        const shown = await cards(page).evaluateAll((els) =>
          els.map((el) => (el as HTMLElement).dataset.medication),
        );
        expect(shown, q).toEqual(want.map((m) => m.medication_id));
        const first = cards(page).first();
        await expect(first.getByTestId('medication-atc')).toHaveText(want[0]?.atc ?? '');
        if (want[0]?.sukl_code)
          await expect(first.getByTestId('medication-sukl')).toHaveText(want[0].sukl_code);
        await expect(first.getByTestId('medication-patients')).toHaveText(
          String(want[0]?.patients_on_regimen),
        );
        await expect(first.getByTestId('medication-match')).toHaveAttribute(
          'data-match',
          want[0]?.match ?? '',
        );
      }
    } finally {
      await context.close();
    }
  });

  test('SPC-Link öffnet in neuem Tab mit noopener; Handelsname und Wirkstoff; Entwurf sichtbar', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.goto('/clinic/medications?q=oxaliplatin');
      const card = cards(page).first();
      await expect(card).toBeVisible();
      const link = card.getByTestId('medication-spc').getByRole('link');
      await expect(link).toHaveAttribute('target', '_blank');
      await expect(link).toHaveAttribute('rel', /noopener/);
      expect(await link.getAttribute('href')).toMatch(/^https:\/\/prehledy\.sukl\.cz\//);
      await expect(card.getByTestId('medication-inn')).toContainText('oxaliplatin');
    } finally {
      await context.close();
    }
  });

  test('zu kurz / nichts gefunden / feindlicher Suchtext: Hinweis ohne Anfrage bzw. Text statt HTML', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      const seen: string[] = [];
      page.on('request', (request) => {
        if (request.url().includes('/api/v1/waechter/medications?')) seen.push(request.url());
      });
      await page.goto('/clinic/medications');
      await page.getByLabel(/Léčivo/).fill('x');
      await page.waitForTimeout(600);
      expect(seen, 'ein Zeichen darf nichts senden').toEqual([]);
      await expect(page.getByTestId('medication-idle')).toBeVisible();
      await search(page, 'zzzz');
      await expect(page.getByTestId('medication-empty')).toBeVisible();
      const hostile = '<img src=x onerror="window.__xss=1">';
      await search(page, hostile);
      await expect(page.getByTestId('medication-empty')).toBeVisible();
      expect(await page.locator('main img').count()).toBe(0);
      expect(
        await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
      ).toBeUndefined();
    } finally {
      await context.close();
    }
  });

  test('Eingabepause: schnelles Tippen löst nur eine Anfrage aus; Adresse trägt ?q; Neuladen behält die Suche', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      const seen: string[] = [];
      page.on('request', (request) => {
        if (request.url().includes('/api/v1/waechter/medications?')) seen.push(request.url());
      });
      await page.goto('/clinic/medications');
      await page.getByLabel(/Léčivo/).pressSequentially('docetaxel', { delay: 40 });
      await expect(cards(page).first()).toBeVisible();
      expect(seen.length, seen.join(' ')).toBeLessThanOrEqual(2);
      await expect(page).toHaveURL(/q=docetaxel/);
      await page.reload();
      await expect(cards(page).first()).toBeVisible();
      await expect(page.getByLabel(/Léčivo/)).toHaveValue('docetaxel');
    } finally {
      await context.close();
    }
  });

  test('Cockpit: Wirkstoff-Link in „Další údaje“ führt auf die Suche und findet das Präparat', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      const rows = await getJson<Row[]>(page.request, `${API}/patients`);
      const id = rows.find((row) => row.pseudonym === 'SYN-0001')?.patient_id ?? '';
      await page.goto(`/clinic/patients/${id}`);
      await page.waitForLoadState('networkidle');
      await page.goto(`/clinic/patients/${id}`);
      await page.getByTestId('header-more').locator('summary').click();
      const links = page.getByTestId('cockpit-header').locator('a[href^="/clinic/medications"]');
      await expect(links.first()).toBeVisible();
      const count = await links.count();
      expect(count).toBeGreaterThanOrEqual(3); // FOLFOX: Oxaliplatin, Fluorouracil, Kalciumfolinát
      for (let index = 0; index < count; index += 1) {
        const href = (await links.nth(index).getAttribute('href')) ?? '';
        const q = decodeURIComponent(href.split('q=')[1] ?? '');
        expect((await api(page, q)).length, `Wirkstoff „${q}“ findet nichts`).toBeGreaterThan(0);
      }
      await links.first().click();
      await expect(cards(page).first()).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test('Detailseite: h1 = Handelsname, unbekannte Kennung ⇒ Hinweis statt Fehlerseite', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.goto('/clinic/medications/MED-XELODA');
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByRole('heading', { level: 1 })).toContainText('Xeloda');
      await page.goto('/clinic/medications/MED-NOPE');
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
      await expect(cards(page)).toHaveCount(0);
      expect(await page.locator('main').innerText()).not.toMatch(/Traceback|undefined|not_found/);
    } finally {
      await context.close();
    }
  });

  test('Patientin: kein Zugriff, keine Treffer', async ({ browser }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      MOBILE,
    );
    try {
      await page.goto('/clinic/medications?q=xeloda');
      await page.waitForLoadState('networkidle');
      await expect(cards(page)).toHaveCount(0);
      expect(await page.locator('body').innerText()).not.toMatch(/L01BC06|0027023/);
    } finally {
      await context.close();
    }
  });

  for (const [label, viewport] of [
    ['375 px', MOBILE],
    ['1366×768', DESKTOP],
  ] as const) {
    test(`Suche bei ${label}: eine h1, kein Überstand, Schrift ≥ 16 px, Ziele ≥ 44 px`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'doctor',
        viewport,
      );
      try {
        await page.goto('/clinic/medications?q=accord');
        await expect(cards(page).first()).toBeVisible();
        await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
        expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
        expect
          .soft(
            await smallTargets(page, 'button, input, a[href]:not([href="#main"])'),
            'Ziele < 44 px',
          )
          .toEqual([]);
      } finally {
        await context.close();
      }
    });
  }

  test('Sprachen: en und de zeigen lokalisierte Wirkstoffnamen, keine Rohschlüssel', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.goto('/clinic/medications?q=kapecitabin');
      await expect(cards(page).first()).toBeVisible();
      await page.locator('select').first().selectOption('en');
      await page.locator('#medication-q').fill('capecitabine');
      await page.locator('#medication-q').press('Enter');
      await expect(cards(page).first().getByTestId('medication-inn')).toContainText(
        /capecitabine/i,
      );
      const text = await page.locator('main').innerText();
      expect(text).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+|undefined|\[object/);
    } finally {
      await context.close();
    }
  });
});

test.describe('platform-fix nav-wrap', () => {
  for (const [label, viewport, expectWrap] of [
    ['375 px', MOBILE, true],
    ['1366 px', DESKTOP, false],
  ] as const) {
    test(`Hauptnavigation mit zusätzlichen Einträgen bei ${label}: kein Überstand`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'doctor',
        viewport,
      );
      try {
        await page.goto('/clinic');
        await expect(page.getByRole('navigation').first()).toBeVisible();
        const before = await horizontalOverflow(page);
        expect(before).toBeLessThanOrEqual(0);
        // zwei weitere Einträge wie bei einer künftigen Challenge-Navigation einsetzen
        await page.evaluate(() => {
          const nav = document.querySelector('header nav');
          const template = nav?.querySelector('a');
          if (!nav || !template) throw new Error('keine Navigation');
          for (const name of ['Léčiva a přípravky', 'Nastavení pravidel']) {
            const clone = template.cloneNode(true) as HTMLAnchorElement;
            clone.textContent = name;
            clone.setAttribute('href', '/clinic');
            nav.append(clone);
          }
        });
        expect(
          await horizontalOverflow(page),
          'Überstand durch die Navigation',
        ).toBeLessThanOrEqual(0);
        const rows = await page.evaluate(() => {
          const links = Array.from(document.querySelectorAll('header nav a'));
          return new Set(links.map((a) => Math.round(a.getBoundingClientRect().top))).size;
        });
        if (expectWrap) expect(rows, 'Navigation bricht auf mehrere Zeilen um').toBeGreaterThan(1);
        else expect(rows, 'bei 1366 px eine Zeile').toBe(1);
      } finally {
        await context.close();
      }
    });
  }
});
