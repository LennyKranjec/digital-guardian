import { expect, test, type Page, type Route } from '@playwright/test';

import {
  API,
  FORBIDDEN,
  horizontalOverflow,
  openContext,
  smallTargets,
  smallText,
} from '../support/helpers';

/**
 * Adaptiver Check-in (F-10) im echten Browser bei 375 px: Layout, Schrift, Touchziele, Akut-Hinweis ohne
 * Scrollen. Die Sitzungs-API (openapi v2.0) wird mit `page.route` GEMOCKT, solange das Backend (T-16)
 * fehlt; geprüft wird nur die Oberfläche, nicht der Server. Anmeldung und übrige Anfragen sind echt.
 * Sobald T-16 auf main ist, kann A3 die Mocks durch den echten Server ersetzen.
 */
const MOBILE = { width: 375, height: 667 };
const CONTROLS =
  'button, input:not([type=radio]):not([type=checkbox]), select, textarea, label:has(input)';

const OPTIONS = [0, 1, 2, 3].map((value) => ({
  value,
  label: ['Nikdy', 'Zřídka', 'Občas', 'Často'][value] ?? '',
}));

const FIRST = {
  session_id: 'mock-sess',
  next: {
    symptom_key: 'nausea',
    attribute: 'frequency',
    label: 'Nevolnost',
    text: 'Jak často se vám dělalo nevolno?',
    options: OPTIONS,
    kind: 'gate',
    safety: false,
  },
  progress: { asked: 0, max: 8 },
  stop: null,
  receipt: null,
  selection_reason: 'Otázky odpovídají vaší léčbě a diagnóze.',
  due: { next_due_at: '2026-10-20T09:00:00+02:00', overdue: false, interval_days: 3 },
};

const STOP = {
  session_id: 'mock-sess',
  next: null,
  progress: { asked: 1, max: 8 },
  stop: { reason: 'decided', incomplete: false },
  receipt: {
    response_id: 'mock-resp',
    recorded_at: '2026-10-17T09:00:00+02:00',
    answered: 1,
    skipped: 0,
    message_key: 'patient.response.saved',
    escalation: {
      level: 'acute',
      text: 'Při akutních obtížích kontaktujte ambulanci nebo volejte 155.',
      ambulance_phone: '[telefon ambulance]',
    },
    advice: [
      {
        symptom_key: 'nausea',
        label: 'Nevolnost',
        tips: ['Pijte po malých douškách.', 'Jezte častěji menší porce.'],
        sources: [{ id: 'spc', title: 'SPC (SÚKL)', url: 'https://www.sukl.cz/' }],
      },
    ],
  },
  selection_reason: FIRST.selection_reason,
  due: { next_due_at: '2026-10-20T09:00:00+02:00', overdue: false, interval_days: 3 },
};

async function mockSessions(page: Page): Promise<void> {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  await page.route(`**${API}/me/sessions`, (route) => json(route, FIRST, 201));
  await page.route(`**${API}/me/sessions/*/answers`, (route) => json(route, STOP));
}

test('Adaptiver Check-in bei 375 px: Karte, Abschluss mit Akut-Hinweis ohne Scrollen, 16 px, 44 px, kein Überstand', async ({
  browser,
}, info) => {
  const baseURL = String(info.project.use.baseURL);
  const { context, page } = await openContext(browser, baseURL, 'patient2', MOBILE);
  try {
    await mockSessions(page);
    await page.goto('/patient');

    const card = page.getByTestId('session-card');
    await expect(card).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    expect(await horizontalOverflow(page), 'Überstand Karte').toBeLessThanOrEqual(0);
    expect.soft(await smallText(page), 'Text < 16 px (Karte)').toEqual([]);
    expect.soft(await smallTargets(page, CONTROLS), 'Ziele < 44 px (Karte)').toEqual([]);
    // keine Ampel/Stufe in der Patientenoberfläche
    await expect(page.locator('[data-traffic-light]')).toHaveCount(0);

    // Kachel wählen, „Weiter“ erst danach aktiv
    const next = card.getByRole('button', { name: 'Další' });
    await expect(next).toBeDisabled();
    await card.getByRole('radio', { name: 'Občas' }).check();
    await expect(next).toBeEnabled();
    await next.click();

    // Abschluss: Akut-Hinweis ist das erste Element und liegt vollständig im ersten Bildschirm
    const acute = page.getByTestId('escalation-acute');
    await expect(acute).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 0));
    const box = await acute.boundingBox();
    expect(box, 'Akut-Hinweis fehlt').not.toBeNull();
    if (box)
      expect(
        box.y + box.height,
        'Akut-Hinweis unterhalb des ersten Bildschirms',
      ).toBeLessThanOrEqual(MOBILE.height);
    await expect(acute).toContainText('155');
    await expect(page.getByTestId('advice-block')).toHaveCount(1);
    expect(await horizontalOverflow(page), 'Überstand Abschluss').toBeLessThanOrEqual(0);
    expect.soft(await smallText(page), 'Text < 16 px (Abschluss)').toEqual([]);
    expect
      .soft(await smallTargets(page, `${CONTROLS}, main a`), 'Ziele < 44 px (Abschluss)')
      .toEqual([]);

    const text = await page.locator('body').innerText();
    expect(text).not.toMatch(FORBIDDEN);
    expect(text).not.toMatch(/\[[^\]]*\]/); // keine Platzhalter in eckigen Klammern
    expect(text).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
    await expect(page.locator('[data-traffic-light]')).toHaveCount(0);
  } finally {
    await context.close();
  }
});
