import { expect, test, type Browser, type Page } from '@playwright/test';

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
import type { AlertDto, Row } from '../support/types';

/**
 * UI-Prüfung F-01…F-05 (nur lesend, parallel-sicher): h1, Überstand, Schrift, Touchziele, Sprachen,
 * Fehler-/Leerzustände, Rollen, Tastatur. Der Zustandswechsel des Kernpfads liegt in core-path.spec.ts.
 */
const MOBILE = { width: 375, height: 800 };
const DESKTOP = { width: 1366, height: 768 };
const WORKLIST = /\/api\/v1\/waechter\/patients(\?.*)?$/;
const CONTROLS =
  'button, input:not([type=radio]):not([type=checkbox]), select, textarea, label:has(input)';

interface Target {
  name: string;
  user: string;
  path: (ids: Ids) => string;
  ready: string;
}
interface Ids {
  withAlert: string;
  alertId: string;
  patient2: string;
}

async function ids(browser: Browser, baseURL: string): Promise<Ids> {
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    const rows = await getJson<Row[]>(page.request, `${API}/patients`);
    const red = rows.find((r) => r.pseudonym === 'SYN-0001');
    const patient2 = rows.find((r) => r.pseudonym === 'SYN-0002');
    const alerts = await getJson<AlertDto[]>(
      page.request,
      `${API}/patients/${red?.patient_id ?? ''}/alerts?status=all`,
    );
    return {
      withAlert: red?.patient_id ?? '',
      alertId: alerts[0]?.alert_id ?? '',
      patient2: patient2?.patient_id ?? '',
    };
  } finally {
    await context.close();
  }
}

const TARGETS: Target[] = [
  {
    name: 'Check-in (Vollformular)',
    user: 'patient2',
    path: () => '/patient/full',
    ready: 'checkin-form',
  },
  { name: 'Check-in (Sitzung)', user: 'patient2', path: () => '/patient', ready: 'session-card' },
  { name: 'Arbeitsliste', user: 'doctor', path: () => '/clinic', ready: 'worklist-row' },
  {
    name: 'Cockpit',
    user: 'doctor',
    path: (i) => `/clinic/patients/${i.withAlert}`,
    ready: 'cockpit-header',
  },
  {
    name: 'CTCAE-Aufnahme',
    user: 'doctor',
    path: (i) => `/clinic/patients/${i.patient2}/assess`,
    ready: 'assessment-form',
  },
  {
    name: 'Meldungsdetail',
    user: 'doctor',
    path: (i) => `/clinic/alerts/${i.alertId}`,
    ready: 'explanation',
  },
  {
    name: 'Einstellungen (Ärztin)',
    user: 'doctor',
    path: () => '/clinic/settings',
    ready: 'rules-section',
  },
  {
    name: 'Einstellungen (Administration)',
    user: 'admin',
    path: () => '/clinic/settings',
    ready: 'rules-section',
  },
  {
    name: 'Bericht',
    user: 'doctor',
    path: (i) => `/clinic/patients/${i.withAlert}/report`,
    ready: 'report-sheet',
  },
];

let known: Ids;
let baseURL = '';

test.beforeAll(async ({ browser }, info) => {
  test.setTimeout(240_000);
  baseURL = String(info.project.use.baseURL);
  await warmTriage(browser, baseURL);
  known = await ids(browser, baseURL);
});

for (const target of TARGETS) {
  for (const [label, viewport] of [
    ['375 px', MOBILE],
    ['1366×768', DESKTOP],
  ] as const) {
    test(`${target.name} bei ${label}: eine h1, kein Überstand, Schrift ≥ 16 px, Steuerelemente ≥ 44 px, keine Rohschlüssel`, async ({
      browser,
    }) => {
      const { context, page } = await openContext(browser, baseURL, target.user, viewport);
      try {
        await page.goto(target.path(known));
        await expect(page.getByTestId(target.ready).first()).toBeVisible();
        await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
        expect(await horizontalOverflow(page), 'horizontaler Überstand').toBeLessThanOrEqual(0);
        expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
        expect.soft(await smallTargets(page, CONTROLS), 'Steuerelemente < 44 px').toEqual([]);
        // keine unübersetzten Schlüssel („waechter.clinic.…“) und kein „undefined“/„[object“
        const text = await page.locator('body').innerText();
        expect(text).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
        expect(text).not.toMatch(/undefined|\[object|NaN/);
      } finally {
        await context.close();
      }
    });
  }
}

for (const [locale, code] of [
  ['en-US', 'en'],
  ['de-DE', 'de'],
  ['cs-CZ', 'cs'],
] as const) {
  test(`Patientenseite in ${code}: Texte, Verbotsliste, Sprachumschaltung, keine Ampel`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL, viewport: MOBILE, locale });
    const page = await context.newPage();
    try {
      await page.request.post('/api/v1/auth/login', {
        headers: { 'X-Requested-With': 'fetch' },
        data: { username: 'patient2', password: 'demo-passwort-2026' },
      });
      await page.goto('/patient/full');
      await expect(page.getByTestId('checkin-form')).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${code}`));
      // Pflichthinweis zum PRO-CTCAE-Wortlaut (DR-040, wörtlich: „PRO-CTCAE®“, „not for diagnostic …“)
      // gehört nicht zur Verbotslistenprüfung der Oberfläche, muss aber vorhanden sein.
      const notice = page.getByTestId('pro-ctcae-notice');
      await expect(notice).toBeVisible();
      expect(await notice.innerText()).toMatch(/PRO-CTCAE/);
      await notice.evaluate((element) => ((element as HTMLElement).style.display = 'none'));
      const text = await page.locator('body').innerText();
      expect(text).not.toMatch(FORBIDDEN);
      expect(text).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
      await expect(page.locator('[data-traffic-light]')).toHaveCount(0);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    } finally {
      await context.close();
    }
  });
}

test('Rollen: Patientin sieht keine Klinikseiten und ruft keine Klinik-API; Ärztin keine Patientenseite', async ({
  browser,
}) => {
  const { context: pctx, page } = await openContext(browser, baseURL, 'patient2', MOBILE);
  try {
    const clinicCalls: string[] = [];
    page.on('request', (r) => {
      const url = r.url();
      if (/\/waechter\/(patients|alerts|notifications|config)/.test(url)) clinicCalls.push(url);
    });
    await page.goto('/clinic');
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
    await expect(page.getByTestId('worklist-row')).toHaveCount(0);
    expect(await page.locator('body').innerText()).not.toMatch(/SYN-000[1-5]/);
    expect(clinicCalls, 'Klinik-API aus der Patientenseite aufgerufen').toEqual([]);
  } finally {
    await pctx.close();
  }
  const { context: dctx, page: doctor } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    await doctor.goto('/patient');
    await expect(doctor.getByTestId('checkin-form')).toHaveCount(0);
  } finally {
    await dctx.close();
  }
});

test('Zustände: Serverfehler zeigt Wiederholen, leere Liste einen Leerzustand, unbekannte Patientin 404', async ({
  browser,
}) => {
  test.setTimeout(120_000);
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    await page.route(WORKLIST, (route) => {
      if (route.request().method() === 'GET') return route.fulfill({ status: 500, body: '{}' });
      return route.continue();
    });
    await page.goto('/clinic');
    await expect(page.getByRole('alert').first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button').filter({ hasText: /\S/ }).first()).toBeVisible();
    await page.unroute(WORKLIST);

    await page.route(WORKLIST, (route) =>
      route.request().method() === 'GET'
        ? route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
        : route.continue(),
    );
    await page.reload();
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    await expect(page.getByTestId('worklist-row')).toHaveCount(0);
    expect(await page.locator('main').innerText()).not.toMatch(/undefined|\[object/);
    await page.unroute(WORKLIST);

    await page.goto('/clinic/patients/00000000-0000-0000-0000-000000000000');
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
    await expect(page.getByTestId('cockpit-header')).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('Tastatur: jeder Knopf der Arbeitsliste und des Cockpits ist per Tab erreichbar, kein Tastaturfang', async ({
  browser,
}) => {
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    for (const path of [
      '/clinic',
      `/clinic/patients/${known.withAlert}`,
      '/clinic/settings',
      `/clinic/patients/${known.withAlert}/report`,
    ]) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
      await expect(
        page
          .getByTestId('worklist-row')
          .or(page.getByTestId('cockpit-header'))
          .or(page.getByTestId('rules-section'))
          .or(page.getByTestId('report-sheet'))
          .first(),
      ).toBeVisible();
      const wanted = await focusables(page);
      const reached = new Set<string>();
      for (let i = 0; i < wanted.size + 25; i += 1) {
        await page.keyboard.press('Tab');
        const key = await page.evaluate(() => {
          const el = document.activeElement as HTMLElement | null;
          if (!el || el === document.body) return '';
          return `${el.tagName}|${el.getAttribute('href') ?? ''}|${el.id}|${(el.innerText || el.getAttribute('aria-label') || '').slice(0, 30)}`;
        });
        if (key) reached.add(key);
      }
      const missing = [...wanted].filter((k) => !reached.has(k));
      expect(missing, `per Tab nicht erreichbar auf ${path}`).toEqual([]);
    }
  } finally {
    await context.close();
  }
});

async function focusables(page: Page): Promise<Set<string>> {
  const list = await page.evaluate(() => {
    const result: string[] = [];
    const seenRadioGroups = new Set<string>();
    for (const el of Array.from(
      document.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([type=radio]):not([disabled]), select:not([disabled]), textarea:not([disabled]), summary',
      ),
    )) {
      const box = el.getBoundingClientRect();
      if (box.width === 0 || box.height === 0 || el.tabIndex < 0) continue;
      // Inhalt eines geschlossenen <details> ist nicht fokussierbar (nur die <summary> selbst)
      if (el.closest('details:not([open])') && el.tagName !== 'SUMMARY' && !el.closest('summary'))
        continue;
      const name = (el as HTMLInputElement).name ?? '';
      if (name && seenRadioGroups.has(name)) continue;
      result.push(
        `${el.tagName}|${el.getAttribute('href') ?? ''}|${el.id}|${(el.innerText || el.getAttribute('aria-label') || '').slice(0, 30)}`,
      );
    }
    return result;
  });
  return new Set(list);
}

interface TimelineBody {
  series: { points: { value: number | null }[] }[];
  missing_days: string[];
}

test('Verlauf (F-04): Messpunkte und Lücken im Bild = Server, jedes Diagramm beschriftet, Punkte per Tastatur', async ({
  browser,
}) => {
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    const timeline = page.waitForResponse(
      (r) => /\/waechter\/patients\/[^/]+\/timeline/.test(r.url()) && r.status() === 200,
    );
    await page.goto(`/clinic/patients/${known.withAlert}`);
    const body = (await (await timeline).json()) as TimelineBody;
    const charts = page.getByTestId('timeline-chart');
    await expect(charts.first()).toBeVisible();
    const values = body.series.flatMap((s) => s.points).filter((p) => p.value !== null).length;
    const gaps = body.series.flatMap((s) => s.points).filter((p) => p.value === null).length;
    await expect(page.getByTestId('value-point')).toHaveCount(values);
    await expect(page.getByTestId('gap-marker')).toHaveCount(gaps);
    expect(gaps, 'Fixture hat übersprungene Antworten (Lücken)').toBeGreaterThan(0);
    // Zugänglichkeit: jedes Bild hat einen Namen, die Datenpunkte erreichen die Tastatur
    const labels = await charts
      .locator('[role="img"]')
      .evaluateAll((els) => els.map((el) => el.getAttribute('aria-label') ?? ''));
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.every((label) => label.trim().length > 3)).toBe(true);
    await charts.first().getByTestId('chart-item').first().focus();
    await page.keyboard.press('ArrowRight');
    await expect(charts.first().getByTestId('chart-caption')).not.toBeEmpty();
    // fehlende Tage sind markiert
    if (body.missing_days.length > 0)
      expect(await page.getByTestId('missing-day').count()).toBeGreaterThan(0);
  } finally {
    await context.close();
  }
});

// Zustandsunabhängig: die Höhe von alerts-section hängt von Anzahl/Status der Meldungen ab, die die
// parallel laufende Kernpfad-Spec ändert; sie wird dort (frisch) und für SYN-0001 (test.fail) geprüft.
const FIRST_SCREEN = ['cockpit-header', 'summary-panel', 'timeline-compact'];

for (const [label, viewport] of [
  ['1366×768', { width: 1366, height: 768 }],
  ['1280×720', { width: 1280, height: 720 }],
] as const) {
  test(`S5 (F-07) bei ${label}: alle fünf Patientinnen zeigen Ampel, Meldungen, Kurzfassung und kompakten Verlauf im ersten Bildschirm`, async ({
    browser,
  }, info) => {
    test.setTimeout(120_000);
    const { context, page } = await openContext(browser, baseURL, 'doctor', viewport);
    try {
      const rows = await getJson<Row[]>(page.request, `${API}/patients`);
      expect(rows.length).toBeGreaterThanOrEqual(5);
      const report: string[] = [];
      for (const row of rows) {
        await page.goto(`/clinic/patients/${row.patient_id}`);
        await expect(page.getByTestId('cockpit-header')).toBeVisible();
        await expect(page.getByTestId('timeline-compact-card').first()).toBeVisible(); // nicht der Platzhalter
        await page.evaluate(() => window.scrollTo(0, 0));
        for (const id of FIRST_SCREEN) {
          const box = await page.getByTestId(id).boundingBox();
          const bottom = box ? Math.round(box.y + box.height) : -1;
          report.push(`${row.pseudonym} ${id}=${bottom}`);
          if (label === '1366×768') {
            expect.soft(box, `${row.pseudonym}: ${id} fehlt`).not.toBeNull();
            if (box)
              expect
                .soft(bottom, `${row.pseudonym}: ${id} unterhalb von ${viewport.height} px`)
                .toBeLessThanOrEqual(viewport.height);
          }
        }
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      }
      info.annotations.push({ type: `S5 ${label}`, description: report.join('; ') });
    } finally {
      await context.close();
    }
  });
}

test('Cockpit (F-07) bei 375 px: alle Bereiche erreichbar, kein Überstand, kompakter Verlauf lesbar', async ({
  browser,
}) => {
  const { context, page } = await openContext(browser, baseURL, 'doctor', MOBILE);
  try {
    await page.goto(`/clinic/patients/${known.withAlert}`);
    await expect(page.getByTestId('cockpit-header')).toBeVisible();
    await expect(page.getByTestId('timeline-compact-card').first()).toBeVisible();
    for (const id of ['alerts-section', 'summary-panel', 'timeline-compact', 'timeline-section'])
      await expect(page.getByTestId(id).first()).toBeAttached();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
    expect.soft(await smallTargets(page, CONTROLS), 'Steuerelemente < 44 px').toEqual([]);
  } finally {
    await context.close();
  }
});

test('S5 (F-07) bei 1366×768, Ausgangszustand von SYN-0001: auch die zweite Meldung liegt im ersten Bildschirm', async ({
  browser,
}) => {
  const { context, page } = await openContext(browser, baseURL, 'doctor', {
    width: 1366,
    height: 768,
  });
  try {
    await page.goto(`/clinic/patients/${known.withAlert}`);
    await expect(page.getByTestId('alert-card')).toHaveCount(2);
    await expect(page.getByTestId('timeline-compact-card').first()).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    const cards = page.getByTestId('alert-card');
    for (const index of [0, 1]) {
      const box = await cards.nth(index).boundingBox();
      expect(box, `Meldung ${index + 1} fehlt`).not.toBeNull();
      if (box) expect(box.y + box.height, `Meldung ${index + 1}`).toBeLessThanOrEqual(768);
    }
  } finally {
    await context.close();
  }
});

test('Bericht: Schrift ≥ 16 px (Fußnotenmarken)', async ({ browser }) => {
  const { context, page } = await openContext(browser, baseURL, 'doctor', DESKTOP);
  try {
    await page.goto(`/clinic/patients/${known.withAlert}/report`);
    await expect(page.getByTestId('report-sheet')).toBeVisible();
    expect(await smallText(page)).toEqual([]);
  } finally {
    await context.close();
  }
});

for (const code of ['en', 'de'] as const) {
  test(`S5 (F-08) in ${code}: SYN-0001 hält Kopf, Meldungen, Kurzfassung und Verlauf im ersten Bildschirm (längere Texte)`, async ({
    browser,
  }) => {
    const { context, page } = await openContext(browser, baseURL, 'doctor', {
      width: 1366,
      height: 768,
    });
    try {
      await page.goto(`/clinic/patients/${known.withAlert}`);
      await expect(page.getByTestId('cockpit-header')).toBeVisible();
      await page.locator('select').first().selectOption(code);
      await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${code}`));
      await expect(page.getByTestId('alert-card')).toHaveCount(2);
      await expect(page.getByTestId('timeline-compact-card').first()).toBeVisible();
      await page.evaluate(() => window.scrollTo(0, 0));
      for (const id of ['cockpit-header', 'alerts-section', 'summary-panel', 'timeline-compact']) {
        const box = await page.getByTestId(id).boundingBox();
        expect.soft(box, `${code}: ${id} fehlt`).not.toBeNull();
        if (box)
          expect
            .soft(box.y + box.height, `${code}: ${id} unterhalb von 768 px`)
            .toBeLessThanOrEqual(768);
      }
    } finally {
      await context.close();
    }
  });
}
