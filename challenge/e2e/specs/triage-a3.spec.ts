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
 * A3-Gegenproben zu F-11 (Triage-Befundkarte im Cockpit, Regelkarte in den Einstellungen) gegen EIGENE
 * Attrappen der Triage-Endpunkte nach openapi v2.0/v2.5 (`page.route`). Das echte Backend (T-15/T-16)
 * liegt noch nicht vor: geprüft wird nur die Oberfläche der Ärztin (nie Patientinnen).
 */
const DESKTOP = { width: 1366, height: 768 };
const MOBILE = { width: 375, height: 800 };
const TRIAGE = '**/api/v1/waechter/patients/*/triage*';
const TRIAGE_CONFIG = '**/api/v1/waechter/config/triage*';

type Json = Record<string, unknown>;

function decision(extra: Json = {}): Json {
  return {
    response_id: 'resp-1',
    decided_at: '2026-10-17T09:00:00+02:00',
    level: 'RED',
    level_lo: 'RED',
    level_hi: 'RED',
    incomplete: false,
    profile_id: 'FOLFOX',
    rule_version: 'abcdef0123456789abcdef',
    tree_version: 'tree-7',
    reason_codes: [
      {
        code: 'R_CRIT_G3',
        text: 'Kritický příznak ve stupni 3',
        items: ['diarrhea'],
        kind: 'path',
      },
      { code: 'F_FEVER', text: 'Hlášena horečka', items: ['fever'], kind: 'shield' },
    ],
    counterfactuals: [
      { direction: 'lower', text: 'průjem (závažnost) klesl na ≤ 1' },
      { direction: 'raise', text: 'další příznak ve stupni 3' },
    ],
    recommendations: [
      { rule_id: 'ADV-NAUSEA-01', symptom_key: 'nausea', outcome: 'shown', value: 2 },
      { rule_id: 'ADV-FEVER-01', symptom_key: 'fever', outcome: 'suppressed_acute', value: 1 },
    ],
    asked_questions: 6,
    full_questions: 17,
    status: 'placeholder',
    ...extra,
  };
}

async function patientId(page: Page, pseudonym = 'SYN-0001'): Promise<string> {
  const rows = await getJson<Row[]>(page.request, `${API}/patients`);
  return rows.find((row) => row.pseudonym === pseudonym)?.patient_id ?? '';
}

async function openPanel(page: Page): Promise<void> {
  await page.getByTestId('cockpit-tab-triage').click(); // Tab „Triage-Details“ (T-32)
  await page.getByTestId('triage-panel').locator('summary').click();
}

test.describe('Triage-Befundkarte im Cockpit', () => {
  test('lädt erst beim Öffnen (Tastatur), nicht vorab; S5-Erstbildschirm unverändert', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      let requests = 0;
      await page.route(TRIAGE, (route) => {
        requests += 1;
        return route.fulfill({ json: decision() });
      });
      const target = `/clinic/patients/${await patientId(page)}`;
      await page.goto(target); // Vite bündelt beim ersten Besuch nach und lädt neu
      await page.waitForLoadState('networkidle');
      requests = 0;
      await page.goto(target);
      await expect(page.getByTestId('timeline-compact-card').first()).toBeVisible();
      await expect(page.getByTestId('triage-panel')).toBeAttached();
      expect(requests, 'darf vor dem Öffnen nichts laden').toBe(0);
      for (const id of ['cockpit-header', 'summary-panel', 'timeline-compact']) {
        const box = await page.getByTestId(id).boundingBox();
        expect(box && box.y + box.height, id).toBeLessThanOrEqual(768);
      }
      await page.getByTestId('cockpit-tab-triage').click(); // Tab „Triage-Details“ (T-32)
      await page.getByTestId('triage-panel').locator('summary').focus();
      await page.keyboard.press('Enter');
      await expect(page.getByTestId('triage-finding')).toBeVisible();
      expect(requests).toBe(1);
      await page.keyboard.press('Enter'); // schließen
      await expect(page.getByTestId('triage-finding')).toHaveCount(0);
    } finally {
      await context.close();
    }
  });

  test('Rot mit Schutzboden: Schloss und Wort zuerst, Stufe als Text, nie nur Farbe, keine Empfehlungswörter', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE, (route) => route.fulfill({ json: decision() }));
      await page.goto(`/clinic/patients/${await patientId(page)}`);
      await openPanel(page);
      const first = page.getByTestId('triage-reasons').locator('li').first();
      await expect(first).toHaveAttribute('data-kind', 'shield');
      await expect(first.locator('svg')).toHaveCount(1); // Schloss
      await expect(first).toContainText('Ochranná hranice');
      const finding = page.getByTestId('triage-finding');
      await expect(finding).toContainText('Úroveň červená');
      const light = finding.locator('[data-traffic-light]').first();
      expect((await light.innerText()).trim().length).toBeGreaterThan(3); // Text trägt die Aussage
      const text = await finding.innerText();
      expect(text).not.toMatch(
        /doporuč|empfehl|recommend|diagnóz|diagnos|nasadit|vysadit|snížit dávk/i,
      );
      await expect(page.getByTestId('triage-versions')).toContainText('abcdef01');
      await expect(page.getByTestId('triage-placeholder')).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test('Gelb mit Spanne und Unvollständig-Hinweis; Tipps: angezeigt/unterdrückt mit Wort', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE, (route) =>
        route.fulfill({
          json: decision({
            level: 'YELLOW',
            level_lo: 'YELLOW',
            level_hi: 'RED',
            incomplete: true,
          }),
        }),
      );
      await page.goto(`/clinic/patients/${await patientId(page)}`);
      await openPanel(page);
      await expect(page.getByTestId('triage-span')).toContainText('žlutá');
      await expect(page.getByTestId('triage-span')).toContainText('červená');
      await expect(page.getByTestId('triage-incomplete')).toBeVisible();
      const tips = page.getByTestId('triage-tips-table');
      await expect(tips).toContainText('zobrazeno');
      await expect(tips).toContainText('potlačeno (akutní)');
      await expect(page.getByTestId('triage-asked')).toContainText('6');
    } finally {
      await context.close();
    }
  });

  test('Kontrafaktische: normale Einträge lesbar, der Schildeintrag steht nicht hinter „Klesla by, kdyby …“', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE, (route) =>
        route.fulfill({
          json: decision({
            counterfactuals: [
              { direction: 'lower', text: 'průjem (závažnost) klesl na ≤ 1' },
              { direction: 'lower', kind: 'shield', text: 'Boden F_FEVER verhindert Senkung' },
              { direction: 'raise', text: 'další příznak ve stupni 3' },
            ],
          }),
        }),
      );
      await page.goto(`/clinic/patients/${await patientId(page)}`);
      await openPanel(page);
      await expect(page.getByTestId('triage-lower')).toContainText(
        'průjem (závažnost) klesl na ≤ 1',
      );
      await expect(page.getByTestId('triage-raise')).toContainText('další příznak ve stupni 3');
      // der Schildeintrag ist kein Teil des Bedingungssatzes
      await expect(page.getByTestId('triage-lower')).not.toContainText('Boden F_FEVER');
    } finally {
      await context.close();
    }
  });

  test('404 ⇒ dezenter Hinweis, 500 ⇒ Meldung ohne Rohtext, „Erneut versuchen“ lädt neu', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE, (route) =>
        route.fulfill({ status: 404, json: { code: 'not_found', message: 'x' } }),
      );
      await page.goto(`/clinic/patients/${await patientId(page)}`);
      await openPanel(page);
      await expect(page.getByTestId('triage-unavailable')).toBeVisible();
      await page.unroute(TRIAGE);
      let calls = 0;
      await page.route(TRIAGE, (route) => {
        calls += 1;
        return calls === 1
          ? route.fulfill({
              status: 500,
              json: { code: 'boom', message: 'Traceback (most recent call last)' },
            })
          : route.fulfill({ json: decision() });
      });
      await page.reload();
      await openPanel(page);
      await expect(page.getByRole('status').filter({ hasText: /nepodařilo/i })).toBeVisible();
      expect(await page.getByTestId('triage-panel').innerText()).not.toMatch(/Traceback|boom/);
      await page.getByTestId('triage-panel').getByRole('button', { name: /znovu/i }).click();
      await expect(page.getByTestId('triage-finding')).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test('feindliche Texte der Triage-API werden als Text angezeigt', async ({ browser }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      const hostile = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>';
      await page.route(TRIAGE, (route) =>
        route.fulfill({
          json: decision({
            profile_id: hostile,
            reason_codes: [{ code: hostile, text: hostile, items: [hostile], kind: 'path' }],
            counterfactuals: [{ direction: 'lower', text: hostile }],
            recommendations: [
              { rule_id: hostile, symptom_key: hostile, outcome: 'shown', value: 1 },
            ],
          }),
        }),
      );
      await page.goto(`/clinic/patients/${await patientId(page)}`);
      await openPanel(page);
      await expect(page.getByTestId('triage-finding')).toBeVisible();
      expect(await page.getByTestId('triage-panel').locator('img, script').count()).toBe(0);
      expect(
        await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
      ).toBeUndefined();
    } finally {
      await context.close();
    }
  });

  for (const [label, viewport] of [
    ['375 px', MOBILE],
    ['1366×768', DESKTOP],
  ] as const) {
    test(`geöffnete Befundkarte bei ${label}: kein Überstand, Schrift ≥ 16 px, Ziele ≥ 44 px`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'doctor',
        viewport,
      );
      try {
        await page.route(TRIAGE, (route) => route.fulfill({ json: decision() }));
        await page.goto(`/clinic/patients/${await patientId(page)}`);
        await openPanel(page);
        await expect(page.getByTestId('triage-finding')).toBeVisible();
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
        expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
        expect
          .soft(await smallTargets(page, 'summary, button, label:has(input)'), 'Ziele < 44 px')
          .toEqual([]);
      } finally {
        await context.close();
      }
    });
  }

  test('Patientinnen laden nie die Triage (Rollenprüfung im Browser)', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      MOBILE,
    );
    try {
      const seen: string[] = [];
      page.on('request', (request) => {
        if (/\/api\/v1\/waechter\/(patients\/[^/]+\/triage|config\/triage)/.test(request.url()))
          seen.push(request.url());
      });
      await page.goto('/clinic/settings');
      await page.goto('/clinic/patients/00000000-0000-0000-0000-000000000001');
      await page.waitForLoadState('networkidle');
      expect(seen).toEqual([]);
      await expect(page.getByTestId('triage-panel')).toHaveCount(0);
    } finally {
      await context.close();
    }
  });
});

test.describe('Meldung mit Triage-Erklärung („Warum?“, explanation.kind triage, v2.8)', () => {
  const EVIL = '<img src=x onerror="window.__pwned=1">Boden <b>F_FEVER</b>';

  test('Stufe als Text, Schutzboden zuerst, feindliche Texte nur als Text, Befund lädt erst beim Öffnen', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      const id = await patientId(page);
      const seen: string[] = [];
      await page.route(`**/api/v1/waechter/patients/${id}/overview*`, async (route) => {
        const real = await route.fetch();
        const body = (await real.json()) as { open_alerts: Json[] };
        for (const alert of body.open_alerts) {
          alert.explanation = {
            kind: 'triage',
            params: {},
            observed: {},
            evidence: [],
            rationale: EVIL,
            triage: {
              level: 'RED',
              level_lo: 'YELLOW',
              level_hi: 'RED',
              incomplete: true,
              response_id: 'resp-1',
              reason_codes: [
                { code: 'R_CRIT_G3', text: EVIL, items: ['diarrhea'], kind: 'path' },
                { code: 'F_FEVER', text: 'Hlášena horečka', items: ['fever'], kind: 'shield' },
              ],
            },
          };
        }
        await route.fulfill({ response: real, json: body });
      });
      page.on('request', (request) => {
        if (/\/api\/v1\/.*\/triage/.test(request.url())) seen.push(request.url());
      });
      await page.route(TRIAGE, (route) => route.fulfill({ json: decision() }));
      await page.goto(`/clinic/patients/${id}`);
      const cardEl = page.getByTestId('alert-card').first();
      await cardEl.getByRole('button', { name: 'Proč?' }).click();
      const triage = page.getByTestId('explanation-triage');
      await expect(triage).toBeVisible();
      // Stufe und Spanne als Wort, nicht nur Farbe
      await expect(triage).toContainText(/Červen|Rot|Red|červen/i);
      await expect(page.getByTestId('explanation-triage-span')).toBeVisible();
      // feindliche Texte sind Text
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBe(
        undefined,
      );
      await expect(page.locator('img[src="x"]')).toHaveCount(0);
      // Schutzboden steht vor dem Pfad
      const reasons = triage.locator('li');
      await expect(reasons.first()).toContainText('horečka');
      // die Befundkarte lädt erst beim Öffnen
      expect(seen).toEqual([]);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    } finally {
      await context.close();
    }
  });
});

function card(verification: Json): Json {
  return {
    kb_version: 'triage-v1#abc123',
    compiler_version: 'c-1',
    profiles: [
      {
        profile_id: 'FOLFOX',
        regimen_ids: ['FOLFOX'],
        tree_version: 'tree-7',
        trees: { yellow: { leaves: 12, depth: 6 }, red: { leaves: 9, depth: 5 } },
        verification,
        rules: [
          { level: 'yellow', text: 'Příznak ve stupni 2' },
          { level: 'red', text: 'Kritický příznak ve stupni 3' },
        ],
        floors: [{ id: 'F_FEVER', text: 'Hlášena horečka', min_level: 'RED', locked: true }],
        placeholders: ['A-TRI-01'],
      },
    ],
  };
}

test.describe('Triage-Regelkarte in den Einstellungen', () => {
  test('sauber verifiziert: Banner mit Zahlen, Regeln rot zuerst, Boden mit Schloss, Platzhalter sichtbar', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE_CONFIG, (route) =>
        route.fulfill({
          json: card({
            points: 221184,
            under: 0,
            over: 0,
            monotone_violations: 0,
            scope: 'exhaustive_raw',
          }),
        }),
      );
      await page.goto('/clinic/settings');
      const banner = page.getByTestId('triage-verification');
      await expect(banner).toContainText('221184');
      await expect(banner).toHaveAttribute('data-clean', 'true');
      const rules = page.getByTestId('triage-rules').locator('li');
      await expect(rules.first()).toContainText('Kritický příznak');
      await expect(page.getByTestId('triage-floors')).toContainText('zamčeno');
      await expect(page.getByTestId('triage-placeholders')).toBeVisible();
      expect(await page.locator('input:not([disabled]), textarea').count()).toBe(0); // nur lesen
    } finally {
      await context.close();
    }
  });

  test('Abweichungen werden nie als bestanden gezeigt', async ({ browser }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE_CONFIG, (route) =>
        route.fulfill({
          json: card({
            points: 1000,
            under: 2,
            over: 0,
            monotone_violations: 1,
            scope: 'exhaustive_raw',
          }),
        }),
      );
      await page.goto('/clinic/settings');
      const banner = page.getByTestId('triage-verification');
      await expect(banner).toHaveAttribute('data-clean', 'false');
      await expect(banner).toContainText('odchylkami');
      await expect(banner).not.toContainText(/^Ověřeno:/);
    } finally {
      await context.close();
    }
  });

  test('Stichprobe statt vollständiger Prüfung wird als solche benannt', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE_CONFIG, (route) =>
        route.fulfill({
          json: card({
            points: 5000,
            under: 0,
            over: 0,
            monotone_violations: 0,
            scope: 'sampled_raw',
          }),
        }),
      );
      await page.goto('/clinic/settings');
      const banner = page.getByTestId('triage-verification');
      await expect(banner).toBeVisible();
      await expect(banner).toContainText(/vzork|sampl|Stichprobe/i);
    } finally {
      await context.close();
    }
  });

  const SCOPES: [string, string | undefined, boolean, string, RegExp][] = [
    ['vollständig (exhaustive_raw)', 'exhaustive_raw', true, 'exhaustive', /úplně/],
    ['vollständig (exhaustive_orbit)', 'exhaustive_orbit', true, 'exhaustive', /úplně/],
    ['Stichprobe (sampled_raw)', 'sampled_raw', false, 'sampled', /vzorku/],
    ['Umfang fehlt', undefined, false, 'unknown', /rozsah neuveden/],
  ];
  for (const [label, scope, passed, dataScope, text] of SCOPES) {
    test(`Prüfumfang ${label}: Haken nur bei vollständiger sauberer Prüfung, Umfang als Wort`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'doctor',
        DESKTOP,
      );
      try {
        const verification: Json = { points: 4321, under: 0, over: 0, monotone_violations: 0 };
        if (scope) verification.scope = scope;
        await page.route(TRIAGE_CONFIG, (route) => route.fulfill({ json: card(verification) }));
        await page.goto('/clinic/settings');
        const banner = page.getByTestId('triage-verification');
        await expect(banner).toBeVisible();
        await expect(banner).toHaveAttribute('data-scope', dataScope);
        await expect(banner).toHaveAttribute('data-passed', String(passed));
        await expect(banner).toContainText(text);
        await expect(banner).toContainText('4321');
        // der Haken ist das erste Zeichen der Kopfzeile, sonst ein Ausrufezeichen – beides mit Worten daneben
        const mark =
          (await banner.locator('p').first().locator('span').first().textContent()) ?? '';
        expect(mark.trim()).toBe(passed ? '✓' : '!');
        // alter Wortlaut „Ověřeno/Verifiziert“ nie, Platzhalter-Hinweis immer direkt im Banner
        const body = (await banner.innerText()).trim();
        expect(body).not.toMatch(/Ověřeno|verifiziert|verified/i);
        await expect(banner.getByTestId('triage-banner-placeholder')).toBeVisible();
      } finally {
        await context.close();
      }
    });
  }

  test('Abweichung bei vollständigem Umfang: kein Haken, Zahlen sichtbar', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE_CONFIG, (route) =>
        route.fulfill({
          json: card({
            points: 100,
            under: 0,
            over: 1,
            monotone_violations: 0,
            scope: 'exhaustive_raw',
          }),
        }),
      );
      await page.goto('/clinic/settings');
      const banner = page.getByTestId('triage-verification');
      await expect(banner).toHaveAttribute('data-passed', 'false');
      await expect(banner).toHaveAttribute('data-clean', 'false');
      await expect(banner).toContainText('odchylkami');
    } finally {
      await context.close();
    }
  });

  for (const [lang, option, wording, placeholder] of [
    ['de', 'Deutsch', 'Umsetzungstreue geprüft (Baum = Regelwerk)', /Platzhalter/],
    ['en', 'English', /Implementation fidelity|fidelity|faithful/i, /placeholder/i],
  ] as const) {
    test(`Banner in ${lang}: Wortlaut ohne „verifiziert“, Platzhalter-Hinweis, Umfang`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'doctor',
        DESKTOP,
      );
      try {
        await page.route(TRIAGE_CONFIG, (route) =>
          route.fulfill({
            json: card({
              points: 55,
              under: 0,
              over: 0,
              monotone_violations: 0,
              scope: 'sampled_raw',
            }),
          }),
        );
        await page.goto('/clinic/settings');
        await page.getByRole('combobox', { name: 'Jazyk' }).selectOption({ label: option });
        const banner = page.getByTestId('triage-verification');
        await expect(banner).toContainText(wording);
        await expect(banner).toContainText(placeholder);
        await expect(banner).toContainText('55');
        await expect(banner).toHaveAttribute('data-passed', 'false');
        expect(await banner.innerText()).not.toMatch(/verifiziert|Ověřeno|\bverified\b/i);
      } finally {
        await context.close();
      }
    });
  }

  test('404 der Regelkarte ⇒ ehrlicher Leerzustand', async ({ browser }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'doctor',
      DESKTOP,
    );
    try {
      await page.route(TRIAGE_CONFIG, (route) =>
        route.fulfill({ status: 404, json: { code: 'not_found', message: 'x' } }),
      );
      await page.goto('/clinic/settings');
      await expect(page.getByTestId('triage-rules-unavailable')).toBeVisible();
    } finally {
      await context.close();
    }
  });

  for (const [label, viewport] of [
    ['375 px', MOBILE],
    ['1366×768', DESKTOP],
  ] as const) {
    test(`Regelkarte bei ${label}: kein Überstand, Schrift ≥ 16 px, Ziele ≥ 44 px`, async ({
      browser,
    }, info) => {
      const { context, page } = await openContext(
        browser,
        String(info.project.use.baseURL),
        'doctor',
        viewport,
      );
      try {
        await page.route(TRIAGE_CONFIG, (route) =>
          route.fulfill({
            json: card({
              points: 221184,
              under: 0,
              over: 0,
              monotone_violations: 0,
              scope: 'exhaustive_raw',
            }),
          }),
        );
        await page.goto('/clinic/settings');
        await expect(page.getByTestId('triage-verification')).toBeVisible();
        expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
        expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
        expect
          .soft(await smallTargets(page, 'summary, button, label:has(input)'), 'Ziele < 44 px')
          .toEqual([]);
      } finally {
        await context.close();
      }
    });
  }
});
