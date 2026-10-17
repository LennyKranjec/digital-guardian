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
 * Triage-Befundkarte (Cockpit) und Regelkarte/Tipp-Regeln (Einstellungen) im echten Browser (F-11):
 * Überstand, Schrift, Touchziele, S5 unverändert. Die Triage-Endpunkte (openapi v2.0/v2.1) und der
 * `advice`-Block von `GET /config` werden mit `page.route` GEMOCKT, solange das Backend (T-15/T-16)
 * fehlt; geprüft wird nur die Oberfläche. Anmeldung und übrige Anfragen sind echt.
 */
const MOBILE = { width: 375, height: 800 };
const DESKTOP = { width: 1366, height: 768 };
const CONTROLS =
  'button, input:not([type=radio]):not([type=checkbox]), select, textarea, label:has(input), summary';

/** Verbotsliste für Texte an die Ärztin (keine Diagnose, Therapieempfehlung, Beruhigung); Ampel-Wörter sind hier erlaubt. */
const FORBIDDEN_CLINICIAN =
  /diagnos|diagnóz|doporuč|recommend|empfehl|keine sorge|harmless|nebojte|v pořádku|dosis|dávkov/i;

const DECISION = {
  response_id: 'mock-resp',
  level: 'RED',
  level_lo: 'YELLOW',
  level_hi: 'RED',
  incomplete: true,
  profile_id: 'chemo-folfox',
  rule_version: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
  tree_version: 'tree-7f3a',
  reason_codes: [
    { code: 'SHIELD-FEVER', text: 'Fieber ja: Mindeststufe Rot', items: ['fever'], kind: 'shield' },
    {
      code: 'PATH-1',
      text: 'Durchfall Schwere ≥ 3 und Häufigkeit ≥ 3',
      items: ['diarrhea'],
      kind: 'path',
    },
    { code: 'INC', text: 'Sicherheitsfrage nicht beantwortet', kind: 'incomplete' },
  ],
  counterfactuals: [
    {
      direction: 'lower',
      text: 'Durchfall Schwere auf 2 sinkt – Boden Fieber verhindert die Senkung',
    },
    { direction: 'raise', text: 'ein weiteres Symptom Stufe 3 erreicht' },
  ],
  recommendations: [
    { rule_id: 'ADV-DIARRHEA-01', symptom_key: 'diarrhea', outcome: 'shown', value: 3 },
    { rule_id: 'ADV-FEVER-01', symptom_key: 'fever', outcome: 'suppressed_acute', value: 1 },
  ],
  asked_questions: 5,
  full_questions: 14,
  status: 'placeholder',
};

const RULE_CARD = {
  kb_version: '0123456789abcdef0123456789abcdef',
  compiler_version: 'compiler-1',
  profiles: [
    {
      profile_id: 'chemo-folfox',
      regimen_ids: ['regimen-folfox'],
      tree_version: 'tree-7f3a',
      trees: { yellow: { leaves: 9, depth: 4 }, red: { leaves: 5, depth: 3 } },
      verification: {
        points: 12345,
        under: 0,
        over: 0,
        monotone_violations: 0,
        scope: 'exhaustive',
      },
      rules: [
        { level: 'YELLOW', text: 'Übelkeit Häufigkeit ≥ 2', leaf_id: 'Y-1a2b3c4d5e6f7a8b' },
        { level: 'RED', text: 'Durchfall Schwere ≥ 3', leaf_id: 'R-3c4d5e6f7a8b9c0d' },
      ],
      floors: [{ id: 'FLOOR-FEVER', text: 'Fieber ja', min_level: 'RED', locked: true }],
      placeholders: ['Schwellen: Platzhalter, nicht klinisch freigegeben'],
    },
  ],
};

const ADVICE = {
  version: 'advice-v1',
  advice: [
    {
      id: 'ADV-NAUSEA-01',
      symptom_key: 'nausea',
      status: 'draft',
      min_value: 2,
      max_value: 4,
      tips: ['a', 'b'],
      source_ids: ['SRC-NCI-NAUSEA-VOMITING'],
    },
  ],
  sources: [{ id: 'SRC-NCI-NAUSEA-VOMITING', title: 'Nausea and Vomiting and Cancer, NCI' }],
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

async function mockTriage(page: Page): Promise<void> {
  await page.route(/\/api\/v1\/waechter\/patients\/[^/]+\/triage(\?.*)?$/, (route) =>
    json(route, DECISION),
  );
  await page.route(/\/api\/v1\/waechter\/config\/triage(\?.*)?$/, (route) =>
    json(route, RULE_CARD),
  );
  // echter /config, ergänzt um den (noch fehlenden) advice-Block
  await page.route(/\/api\/v1\/waechter\/config(\?.*)?$/, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    await json(route, { ...body, advice: ADVICE });
  });
}

for (const [label, viewport] of [
  ['375 px', MOBILE],
  ['1366×768', DESKTOP],
] as const) {
  test(`Cockpit-Triage-Befund bei ${label}: aufklappbar, kein Überstand, Schrift ≥ 16 px, Ziele ≥ 44 px`, async ({
    browser,
  }, info) => {
    const baseURL = String(info.project.use.baseURL);
    const { context, page } = await openContext(browser, baseURL, 'doctor', viewport);
    try {
      await mockTriage(page);
      const rows = await getJson<Row[]>(page.request, `${API}/patients`);
      const red = rows.find((row) => row.pseudonym === 'SYN-0001');
      await page.goto(`/clinic/patients/${red?.patient_id ?? ''}`);
      await expect(page.getByTestId('cockpit-header')).toBeVisible();

      const panel = page.getByTestId('triage-panel');
      await expect(panel).toBeAttached();
      // eingeklappt: nimmt dem ersten Bildschirm nichts weg (Kopf, Kurzfassung und Verlauf wie in ui-checks)
      if (label === '1366×768') {
        await page.evaluate(() => window.scrollTo(0, 0));
        for (const id of ['cockpit-header', 'summary-panel', 'timeline-compact']) {
          const box = await page.getByTestId(id).boundingBox();
          expect(box, `${id} fehlt`).not.toBeNull();
          if (box)
            expect(box.y + box.height, `${id} unterhalb von 768 px`).toBeLessThanOrEqual(768);
        }
      }

      await page.getByTestId('cockpit-tab-triage').click(); // Tab „Triage-Details“ (T-32)
      await panel.locator('summary').click();
      const finding = page.getByTestId('triage-finding');
      await expect(finding).toBeVisible();
      await expect(finding).toContainText('Úroveň červená');
      await expect(finding).toContainText('Možné rozpětí');
      await expect(page.getByTestId('triage-incomplete')).toBeVisible();
      await expect(
        page.getByTestId('triage-reasons').getByRole('listitem').first(),
      ).toHaveAttribute('data-kind', 'shield');
      await expect(page.getByTestId('triage-tips-table')).toBeVisible();

      expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect.soft(await smallTargets(page, CONTROLS), 'Ziele < 44 px').toEqual([]);
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      const text = await finding.innerText();
      expect(text).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
      expect(text).not.toMatch(/undefined|\[object|NaN/);
      expect(FORBIDDEN_CLINICIAN.test(text)).toBe(false);
    } finally {
      await context.close();
    }
  });

  test(`Einstellungen: Regelkarte und Tipp-Regeln bei ${label}: kein Überstand, Schrift ≥ 16 px, Ziele ≥ 44 px`, async ({
    browser,
  }, info) => {
    const baseURL = String(info.project.use.baseURL);
    const { context, page } = await openContext(browser, baseURL, 'doctor', viewport);
    try {
      await mockTriage(page);
      await page.goto('/clinic/settings');
      const card = page.getByTestId('triage-rules-section');
      await expect(card.getByTestId('triage-profile').first()).toBeVisible();
      await expect(card.getByTestId('triage-verification').first()).toContainText('podtriáž 0');
      await expect(card.getByTestId('triage-floors')).toContainText('zamčeno');
      const advice = page.getByTestId('advice-rules');
      await expect(advice.getByTestId('advice-rules-table')).toBeVisible();
      await expect(advice).toContainText('ADV-NAUSEA-01');

      expect(await horizontalOverflow(page), 'Überstand').toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect.soft(await smallTargets(page, CONTROLS), 'Ziele < 44 px').toEqual([]);
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    } finally {
      await context.close();
    }
  });
}
