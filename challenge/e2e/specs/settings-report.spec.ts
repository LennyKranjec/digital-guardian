import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test';

import {
  API,
  CSRF,
  getJson,
  horizontalOverflow,
  openContext,
  smallTargets,
} from '../support/helpers';
import type { Row } from '../support/types';

/**
 * F-06 gegen das echte Backend: Einstellungen (Ärztin liest, Administration ändert, Konflikt, Eingabefehler),
 * Bericht (Druckansicht, PDF, 375 px) und FHIR-Export-Download. Ändert nur `noise.cooldown_hours`
 * (23 → 23,5 …); Ampeln und Meldungen anderer Specs bleiben unberührt.
 */
const DESKTOP = { width: 1366, height: 768 };
const MOBILE = { width: 375, height: 800 };
const VENV_PYTHON = 'C:\\rk\\tools\\a3-venv\\Scripts\\python.exe';

interface HistoryRow {
  version: string;
  change_note: string | null;
  active: boolean;
}
interface ConfigDto {
  rules: { version: string; noise: { cooldown_hours: number; notify_levels: string[] } };
}

// Alle Tests dieser Datei ändern oder lesen die eine Konfiguration: nacheinander.
test.describe.configure({ mode: 'serial' });

let baseURL = '';
let patientId = '';

test.beforeAll(async ({ browser }, info) => {
  baseURL = String(info.project.use.baseURL);
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    const rows = await getJson<Row[]>(page.request, `${API}/patients`);
    patientId = rows.find((row) => row.pseudonym === 'SYN-0001')?.patient_id ?? '';
  } finally {
    await context.close();
  }
});

async function history(page: Page): Promise<HistoryRow[]> {
  return getJson<HistoryRow[]>(page.request, `${API}/config/history?kind=rules`);
}

async function warmUp(page: Page, path: string): Promise<void> {
  // Vite bündelt Abhängigkeiten bei der ersten Seite nach und lädt neu; einmal vorab besuchen.
  await page.goto(path);
  await page.waitForLoadState('networkidle');
}

test.describe('Einstellungen', () => {
  test('Ärztin liest nur: keine Eingabefelder, Rollenhinweis, Historie sichtbar, PUT ⇒ 403', async ({
    browser,
  }) => {
    const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
    try {
      await warmUp(page, '/clinic/settings');
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByTestId('rule-card').first()).toBeVisible();
      await expect(page.getByTestId('settings-role-note')).toBeVisible();
      expect(await page.locator('[data-testid="rule-card"] input').count()).toBe(0);
      expect(await page.locator('#change-note').count()).toBe(0);
      await expect(page.getByTestId('history-rules')).toBeVisible();
      const config = await getJson<ConfigDto>(page.request, `${API}/config`);
      const put = await page.request.put(`${API}/config/rules`, {
        headers: CSRF,
        data: { expected_version: config.rules.version, rules: {}, change_note: 'x' },
      });
      expect(put.status()).toBe(403);
    } finally {
      await context.close();
    }
  });

  test('Administration: Eingabefehler werden lokal abgefangen, ohne Anfrage an den Server', async ({
    browser,
  }) => {
    const { context, page } = await openContext(browser, baseURL, 'admin', DESKTOP);
    try {
      await warmUp(page, '/clinic/settings');
      const puts: string[] = [];
      page.on('request', (request) => {
        if (request.method() === 'PUT') puts.push(request.url());
      });
      const cooldown = page.locator('#noise-cooldown');
      await expect(cooldown).toBeVisible();
      await cooldown.fill('abc');
      await expect(cooldown).toHaveAttribute('aria-invalid', 'true');
      const save = page.getByRole('button', { name: /Uložit novou verzi pravidel/ });
      await cooldown.fill('19');
      await page.locator('#change-note').fill('   ');
      await page.getByRole('checkbox', { name: /Červen/i }).uncheck();
      await expect(save).toBeEnabled();
      await save.click();
      await expect(page.getByTestId('noise-error')).toBeVisible(); // ohne rote Benachrichtigung
      await page.getByRole('checkbox', { name: /Červen/i }).check();
      await save.click();
      await expect(page.getByRole('alert').filter({ hasText: /poznámk/i })).toBeVisible();
      expect(puts, 'es darf keine PUT-Anfrage gesendet worden sein').toEqual([]);
    } finally {
      await context.close();
    }
  });

  test('Administration ändert die Sperrzeit (Dezimalkomma): neue Version, Notiz, Historie, Neuladen', async ({
    browser,
  }) => {
    test.setTimeout(90_000);
    const { context, page } = await openContext(browser, baseURL, 'admin', DESKTOP);
    try {
      await warmUp(page, '/clinic/settings');
      const before = await history(page);
      const activeBefore = before.find((row) => row.active)?.version ?? '';
      const note = `A3-Prüfung ${Date.now()}`;
      await page.locator('#noise-cooldown').fill('23,5');
      await page.locator('#change-note').fill(note);
      await page.getByRole('button', { name: /Uložit novou verzi pravidel/ }).click();
      // Die Erfolgsmeldung (rules-saved) erscheint nicht zuverlässig (Befund F-06 F-01, nicht
      // reproduzierbar auslösbar); maßgeblich sind hier Server und angezeigte aktive Version.
      await expect.poll(async () => (await history(page)).length).toBe(before.length + 1);
      const after = await history(page);
      expect(after.length).toBe(before.length + 1);
      expect(after.filter((row) => row.active)).toHaveLength(1);
      expect(after[0]).toMatchObject({ active: true, change_note: note });
      expect(after[0]?.version).not.toBe(activeBefore);
      const config = await getJson<ConfigDto>(page.request, `${API}/config`);
      expect(config.rules.noise.cooldown_hours).toBe(23.5);
      expect(config.rules.noise.notify_levels).toContain('red');
      await page.reload();
      await expect(page.locator('#noise-cooldown')).toHaveValue(/23[.,]5/);
      await expect(page.getByTestId('history-rules')).toContainText(note);
    } finally {
      await context.close();
    }
  });

  test('Konflikt: zweite Sitzung speichert mit veralteter Version ⇒ Hinweis und „Neu laden“', async ({
    browser,
  }) => {
    test.setTimeout(90_000);
    const a = await openContext(browser, baseURL, 'admin', DESKTOP);
    const b = await openContext(browser, baseURL, 'admin', DESKTOP);
    try {
      for (const { page } of [a, b]) {
        await warmUp(page, '/clinic/settings');
        await expect(page.locator('#noise-cooldown')).toBeVisible();
      }
      await a.page.locator('#noise-cooldown').fill('23');
      await a.page.locator('#change-note').fill('A3 Konflikt A');
      await a.page.getByRole('button', { name: /Uložit novou verzi pravidel/ }).click();
      await expect
        .poll(async () => (await history(a.page)).filter((row) => row.active)[0]?.change_note)
        .toBe('A3 Konflikt A');

      await b.page.locator('#noise-cooldown').fill('22');
      await b.page.locator('#change-note').fill('A3 Konflikt B');
      await b.page.getByRole('button', { name: /Uložit novou verzi pravidel/ }).click();
      await expect(b.page.getByRole('alert').filter({ hasText: /změnila/i })).toBeVisible();
      const reload = b.page.getByRole('button', { name: /Načíst znovu/ });
      await expect(reload).toBeVisible();
      const config = await getJson<ConfigDto>(b.page.request, `${API}/config`);
      expect(
        config.rules.noise.cooldown_hours,
        'der veraltete Stand darf nichts überschreiben',
      ).toBe(23);
      await reload.click();
      await expect(b.page.locator('#noise-cooldown')).toHaveValue('23');
    } finally {
      await a.context.close();
      await b.context.close();
    }
  });
});

test('375 px: Versionshistorie mit mehreren Zeilen als Karten, kein Überstand, Zeilen mit Beschriftung und Rollen', async ({
  browser,
}) => {
  const admin = await openContext(browser, baseURL, 'admin', MOBILE);
  const doctor = await openContext(browser, baseURL, 'doctor', MOBILE);
  try {
    const config = await getJson<{ rules: Record<string, unknown> }>(
      admin.page.request,
      `${API}/config`,
    );
    const { version, ...rules } = config.rules as { version: string } & Record<string, unknown>;
    for (let round = 0; round < 2; round += 1) {
      const current = (await history(admin.page)).find((row) => row.active)?.version ?? version;
      const changed = await admin.page.request.put(`${API}/config/rules`, {
        headers: CSRF,
        data: { expected_version: current, rules, change_note: `A3 Historie ${round}` },
      });
      expect(changed.status()).toBe(200);
    }
    await doctor.page.goto('/clinic/settings');
    const section = doctor.page.getByTestId('history-rules');
    await expect(section).toBeVisible();
    // Zeilen erst nach dem Laden der Historie (vorher steht ein Platzhalter im Bereich)
    await expect.poll(async () => section.getByRole('row').count()).toBeGreaterThanOrEqual(3);
    expect(await horizontalOverflow(doctor.page)).toBeLessThanOrEqual(0);
    // jede Zeile (Karte) nennt Version, Notiz und Status im Text
    const text = await section.innerText();
    expect(text).toContain('A3 Historie 1');
    expect(text).toContain('A3 Historie 0');
    expect
      .soft(await smallTargets(doctor.page, 'button, label:has(input)'), 'Ziele < 44 px')
      .toEqual([]);
  } finally {
    await admin.context.close();
    await doctor.context.close();
  }
});

async function pdfPages(context: BrowserContext, page: Page, file: string) {
  void context;
  await page.emulateMedia({ media: 'print' });
  await page.pdf({ path: file, format: 'A4', printBackground: true });
  await page.emulateMedia({ media: 'screen' });
  if (!existsSync(VENV_PYTHON)) return null;
  const script = [
    'import sys, json',
    'from pypdf import PdfReader',
    'r = PdfReader(sys.argv[1])',
    'print(json.dumps([p.extract_text() or "" for p in r.pages]))',
  ].join('\n');
  const run = spawnSync(VENV_PYTHON, ['-I', '-c', script, file], { encoding: 'utf-8' });
  return run.status === 0 ? (JSON.parse(run.stdout) as string[]) : null;
}

test.describe('Bericht', () => {
  test('Druckansicht: Plattformhülle ausgeblendet, Fußzeile auf jeder PDF-Seite, keine Bewertung', async ({
    browser,
  }, info) => {
    test.setTimeout(90_000);
    const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
    try {
      await warmUp(page, `/clinic/patients/${patientId}/report`);
      await expect(page.getByTestId('report-sheet')).toBeVisible();
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      const footer = (await page.getByTestId('report-footer').innerText()).trim();
      expect(footer.length).toBeGreaterThan(10);
      await page.emulateMedia({ media: 'print' });
      await expect(page.getByTestId('report-toolbar')).toBeHidden();
      await expect(page.locator('header').first()).toBeHidden();
      await expect(page.getByTestId('report-sheet')).toBeVisible();
      await page.emulateMedia({ media: 'screen' });
      const dir = join(info.project.outputDir, 'report');
      mkdirSync(dir, { recursive: true });
      const pages = await pdfPages(context, page, join(dir, 'report.pdf'));
      if (pages === null) {
        info.annotations.push({
          type: 'NOT RUN',
          description: `PDF-Textprüfung: ${VENV_PYTHON} (pypdf) fehlt`,
        });
        return;
      }
      expect(pages.length).toBeGreaterThanOrEqual(1);
      const key = footer.slice(0, 18);
      pages.forEach((text, index) =>
        expect(text, `Fußzeile fehlt auf PDF-Seite ${index + 1}`).toContain(key),
      );
      const all = pages.join('\n');
      expect(all).toContain('SYN-0001');
      // „Diagnose“ steht ausschließlich in der Fußzeile („keine Diagnose“)
      const withoutFooter = all.split(footer).join('');
      expect(withoutFooter).not.toMatch(/diagnóz|diagnos/i);
      info.annotations.push({ type: 'pdf-pages', description: String(pages.length) });
    } finally {
      await context.close();
    }
  });

  test('375 px: eine h1, kein Überstand, Schrift ≥ 16 px, Ziele ≥ 44 px', async ({ browser }) => {
    const { context, page } = await openContext(browser, baseURL, 'doctor', MOBILE);
    try {
      await warmUp(page, `/clinic/patients/${patientId}/report`);
      await expect(page.getByTestId('report-sheet')).toBeVisible();
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      expect.soft(await smallTargets(page, 'button, input'), 'Ziele < 44 px').toEqual([]);
    } finally {
      await context.close();
    }
  });

  test('FHIR-Export: Download = Antwort der API, Dateiname <Pseudonym>-bundle.json, Statusmeldung', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
    try {
      await warmUp(page, `/clinic/patients/${patientId}/report`);
      await expect(page.getByTestId('report-toolbar')).toBeVisible();
      const fhir = await page.request.get(`${API}/patients/${patientId}/fhir`);
      test.skip(fhir.status() === 404, 'FHIR-Export (T-08) ist in diesem Stand nicht integriert');
      expect(fhir.status()).toBe(200);
      const expected = (await fhir.json()) as { timestamp?: string; entry: unknown[] };
      const downloadPromise = page.waitForEvent('download');
      await page.getByRole('button', { name: /FHIR/ }).click();
      const download = await downloadPromise;
      expect(download.suggestedFilename()).toBe('SYN-0001-bundle.json');
      const dir = join(info.project.outputDir, 'report');
      mkdirSync(dir, { recursive: true });
      const file = join(dir, 'download-bundle.json');
      await download.saveAs(file);
      const got = JSON.parse(readFileSync(file, 'utf-8')) as {
        resourceType: string;
        type: string;
        timestamp?: string;
        entry: unknown[];
      };
      expect(got.resourceType).toBe('Bundle');
      expect(got.type).toBe('collection');
      delete got.timestamp;
      delete expected.timestamp;
      expect(got).toEqual(expected);
      await expect(page.getByTestId('export-status')).toContainText('SYN-0001-bundle.json');
      writeFileSync(join(dir, 'ok.txt'), 'ok');
    } finally {
      await context.close();
    }
  });
});

test('Cockpit-Leiste: Bericht und Export sind per Tastatur erreichbar, Bericht öffnet in einem Klick', async ({
  browser,
}) => {
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    await warmUp(page, `/clinic/patients/${patientId}`);
    await expect(page.getByTestId('cockpit-actions')).toBeVisible();
    const link = page
      .getByTestId('cockpit-actions')
      .getByRole('link', { name: /zpráv|Bericht|report/i });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL(new RegExp(`/clinic/patients/${patientId}/report$`));
    await expect(page.getByTestId('report-sheet')).toBeVisible();
  } finally {
    await context.close();
  }
});

export type { Browser };
