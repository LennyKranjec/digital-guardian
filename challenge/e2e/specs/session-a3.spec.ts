import { expect, test, type Page, type Route } from '@playwright/test';

import {
  FORBIDDEN,
  horizontalOverflow,
  openContext,
  smallTargets,
  smallText,
  warmTriage,
} from '../support/helpers';

/**
 * A3-Gegenproben zu F-10 (adaptiver Check-in der Patientin) gegen eine EIGENE zustandsbehaftete
 * Attrappe der Sitzungs-API nach openapi v2.0/v2.1 (`page.route`). Das echte Backend (T-16) liegt noch
 * nicht vor; diese Prüfungen betreffen nur die Oberfläche. Patientinnen sehen nie ein Level, Platzhalter,
 * Skripte oder Bewertungen.
 */
test.beforeAll(async ({ browser }, info) => {
  test.setTimeout(240_000);
  await warmTriage(browser, String(info.project.use.baseURL)); // Kaltstart blockiert sonst Anmeldung und Seiten
});

const PHONE = { width: 375, height: 667 };
const SESSIONS = '**/api/v1/waechter/me/sessions';
const ANSWERS = '**/api/v1/waechter/me/sessions/*/answers';
const SESSION_GET = '**/api/v1/waechter/me/sessions/*';

interface Question {
  symptom_key: string;
  attribute: string;
  label: string;
  text: string;
  options: { value: number; label: string }[];
  kind: 'gate' | 'cascade' | 'escalation' | 'slot';
  safety?: boolean;
}

const OPTIONS = ['Vůbec ne', 'Trochu', 'Středně', 'Hodně', 'Velmi'].map((label, value) => ({
  value,
  label,
}));
const q = (symptom: string, attribute: string, label: string, text = `Jak moc: ${label}?`) =>
  ({
    symptom_key: symptom,
    attribute,
    label,
    text,
    options: OPTIONS,
    kind: 'gate',
  }) satisfies Question;

const RECEIPT = {
  response_id: 'resp-1',
  recorded_at: '2026-10-17T09:00:00+02:00',
  answered: 2,
  skipped: 0,
  message_key: 'patient.response.saved',
  escalation: {
    level: 'general',
    text: 'Při akutních obtížích kontaktujte ambulanci nebo volejte 155.',
  },
  advice: [],
};

const ACUTE = {
  ...RECEIPT,
  escalation: {
    level: 'acute',
    text: 'Při akutních obtížích kontaktujte ambulanci nebo volejte 155.',
  },
};

type Json = Record<string, unknown>;

class SessionMock {
  starts: Json[] = [];
  answers: Json[] = [];
  gets = 0;
  getStatus: number | null = null; // Fehlerstatus für GET /me/sessions/{id} (404 unbekannt, 500 Serverfehler)
  idempotent = false; // Vertrag v2.5: identische Wiederholung der letzten Antwort ⇒ 200 + gleicher Beleg
  clientId: string | null = null;
  lastAnswer: Json | null = null;
  index = 0;
  closed = false;
  failNextAnswer: 'network' | 'ghost' | null = null;
  conflictOnce = false;
  constructor(
    public questions: Question[],
    public receipt: Json = RECEIPT,
    public extra: Json = {},
  ) {}

  step(): Json {
    const next = this.questions[this.index] ?? null;
    return {
      session_id: 'sess-1',
      next,
      progress: { asked: this.index, max: 6 },
      stop: next ? null : { reason: 'decided', incomplete: false },
      receipt: next ? null : this.receipt,
      selection_reason: 'Zvolené podle vašeho léčebného plánu.',
      ...this.extra,
    };
  }

  async install(page: Page): Promise<void> {
    await page.route(SESSIONS, async (route: Route) => {
      const startBody = route.request().postDataJSON() as Json;
      this.starts.push(startBody);
      if (this.closed && this.clientId !== null && startBody.client_session_id !== this.clientId) {
        this.closed = false; // neue Kennung nach „Neuer Check-in“ ⇒ frische Sitzung
        this.index = 0;
      }
      this.clientId = String(startBody.client_session_id);
      if (this.closed) {
        await route.fulfill({ status: 409, json: { code: 'session_closed', message: 'closed' } });
        return;
      }
      await route.fulfill({ status: this.starts.length === 1 ? 201 : 200, json: this.step() });
    });
    // Vertrag v2.5: GET /me/sessions/{id} = aktueller Stand (offen: nächste Frage; beendet: stop + receipt)
    await page.route(SESSION_GET, async (route: Route) => {
      if (route.request().method() !== 'GET') {
        await route.fallback();
        return;
      }
      this.gets += 1;
      if (this.getStatus !== null) {
        await route.fulfill({ status: this.getStatus, json: { code: 'x', message: 'x' } });
        return;
      }
      await route.fulfill({ status: 200, json: this.step() });
    });
    await page.route(ANSWERS, async (route: Route) => {
      const body = route.request().postDataJSON() as Json;
      this.answers.push(body);
      if (this.conflictOnce) {
        this.conflictOnce = false; // Server war schon weiter (z. B. zweiter Tab)
        this.index = Math.max(this.index, 1);
        await route.fulfill({ status: 409, json: { code: 'not_current_question', message: 'no' } });
        return;
      }
      const current = this.questions[this.index];
      if (
        this.idempotent &&
        this.closed &&
        JSON.stringify(body) === JSON.stringify(this.lastAnswer)
      ) {
        await route.fulfill({ status: 200, json: this.step() });
        return;
      }
      if (this.closed || !current) {
        await route.fulfill({ status: 409, json: { code: 'session_closed', message: 'closed' } });
        return;
      }
      if (body.symptom_key !== current.symptom_key || body.attribute !== current.attribute) {
        await route.fulfill({ status: 409, json: { code: 'not_current_question', message: 'no' } });
        return;
      }
      if (this.failNextAnswer === 'network') {
        this.failNextAnswer = null;
        await route.abort('failed');
        return;
      }
      this.lastAnswer = body;
      this.index += 1;
      if (!this.questions[this.index]) this.closed = true;
      if (this.failNextAnswer === 'ghost') {
        this.failNextAnswer = null;
        await route.abort('failed'); // Server hat verarbeitet, die Antwort ging verloren
        return;
      }
      await route.fulfill({ status: 200, json: this.step() });
    });
  }
}

async function open(page: Page, mock: SessionMock, path = '/patient'): Promise<void> {
  await mock.install(page);
  await page.goto(path);
}

const tiles = (page: Page) => page.getByTestId('session-card').getByRole('radio');
const next = (page: Page) => page.getByRole('button', { name: /^Další$/ });

test.describe('Adaptiver Check-in (Attrappe der Sitzungs-API)', () => {
  test('eine Frage je Karte, Auswahl sendet noch nichts, „Další“ sendet genau eine Antwort', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([
        q('fever', 'presence', 'Horečka'),
        q('diarrhea', 'frequency', 'Průjem'),
      ]);
      await open(page, mock);
      await expect(page.getByTestId('session-card')).toBeVisible();
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
      await expect(page.getByTestId('session-progress')).toContainText('0 / 6');
      await expect(page.getByTestId('session-progress').getByRole('progressbar')).toHaveAttribute(
        'aria-valuetext',
        /Otázka 1/,
      );
      expect(await page.getByTestId('session-progress').innerText()).not.toMatch(/%/);
      await expect(next(page)).toBeDisabled();
      await tiles(page).nth(1).check();
      await page.keyboard.press('ArrowDown'); // Pfeiltasten ändern nur die Auswahl
      expect(mock.answers, 'Auswahl darf nichts senden').toEqual([]);
      await next(page).click();
      await expect(page.getByTestId('session-card')).toContainText('Průjem');
      expect(mock.answers).toEqual([{ symptom_key: 'fever', attribute: 'presence', value: 2 }]);
      // Fokus liegt auf der neuen Karte (Überschrift), nicht auf dem Seitenanfang
      await expect(page.locator('#session-card-title')).toBeFocused();
      // Start-Anfrage: zufällige UUID, Sprache
      expect(mock.starts[0]).toMatchObject({ lang: 'cs' });
      expect(String(mock.starts[0]?.client_session_id)).toMatch(/^[0-9a-f-]{36}$/);
    } finally {
      await context.close();
    }
  });

  test('Überspringen sendet null; Doppelklick sendet genau einmal', async ({ browser }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([
        q('nausea', 'frequency', 'Nevolnost'),
        q('pain', 'severity', 'Bolest'),
      ]);
      await open(page, mock);
      await page
        .getByTestId('session-card')
        .getByLabel(/Přeskočit/)
        .check();
      await next(page).dblclick();
      await expect(page.getByTestId('session-card')).toContainText('Bolest');
      expect(mock.answers).toEqual([
        { symptom_key: 'nausea', attribute: 'frequency', value: null },
      ]);
    } finally {
      await context.close();
    }
  });

  test('375 px: Ziele ≥ 44 px, Schrift ≥ 16 px, kein Überstand, keine Rohschlüssel', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      await open(page, new SessionMock([q('fever', 'presence', 'Horečka')]));
      await expect(page.getByTestId('session-card')).toBeVisible();
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
      expect.soft(await smallText(page), 'Text < 16 px').toEqual([]);
      expect
        .soft(
          await smallTargets(page, 'button, label:has(input), a[href]:not([href="#main"])'),
          'Ziele < 44 px',
        )
        .toEqual([]);
      expect(await page.locator('body').innerText()).not.toMatch(
        /\bwaechter\.[a-z]+\.[a-zA-Z.]+|undefined|\[object/,
      );
    } finally {
      await context.close();
    }
  });

  test('Neuladen mitten in der Sitzung setzt mit derselben client_session_id fort; Speicher enthält nur die Kennung', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([
        q('fever', 'presence', 'Horečka'),
        q('diarrhea', 'frequency', 'Průjem'),
      ]);
      await open(page, mock);
      await tiles(page).first().check();
      await next(page).click();
      await expect(page.getByTestId('session-card')).toContainText('Průjem');
      await page.reload();
      await expect(page.getByTestId('session-card')).toContainText('Průjem');
      // Entwicklungsserver (StrictMode) startet beim Einhängen doppelt: nur Kennung vergleichen
      expect(mock.starts.length).toBeGreaterThanOrEqual(2);
      expect(new Set(mock.starts.map((s) => s.client_session_id)).size).toBe(1);
      const storage = await page.evaluate(() =>
        JSON.stringify({ ...sessionStorage, ...localStorage }),
      );
      expect(storage).not.toMatch(/fever|Horečka|presence|diarrhea/i); // keine Antworten im Browserspeicher
    } finally {
      await context.close();
    }
  });

  test('Netzfehler beim Senden: Auswahl bleibt, neutrale Meldung, Wiederholen sendet dieselbe Antwort', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([
        q('fever', 'presence', 'Horečka'),
        q('pain', 'severity', 'Bolest'),
      ]);
      await open(page, mock);
      mock.failNextAnswer = 'network';
      await tiles(page).nth(3).check();
      await next(page).click();
      await expect(page.getByRole('alert')).toBeVisible();
      await expect(tiles(page).nth(3)).toBeChecked();
      await next(page).click();
      await expect(page.getByTestId('session-card')).toContainText('Bolest');
      expect(mock.answers.length).toBe(2);
      expect(mock.answers[1]).toEqual(mock.answers[0]);
    } finally {
      await context.close();
    }
  });

  test('409 not_current_question lädt die aktuelle Frage des Servers mit derselben Kennung', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([
        q('fever', 'presence', 'Horečka'),
        q('pain', 'severity', 'Bolest'),
      ]);
      await open(page, mock);
      mock.conflictOnce = true;
      await tiles(page).first().check();
      await next(page).click();
      await expect(page.getByTestId('session-card')).toContainText('Bolest');
      expect(new Set(mock.starts.map((s) => s.client_session_id)).size).toBe(1);
    } finally {
      await context.close();
    }
  });

  test('Abschluss mit Akut-Hinweis: Hinweis zuerst und ohne Scrollen, Platzhalter nie sichtbar, keine Verbotswörter, kein Level', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const receipt = {
        ...RECEIPT,
        escalation: {
          level: 'acute',
          text: 'Při akutních obtížích kontaktujte ambulanci [telefon ambulance] nebo volejte 155.',
          ambulance_phone: '[telefon ambulance]',
        },
        advice: [
          {
            rule_id: 'ADV-NAUSEA-01',
            symptom_key: 'nausea',
            label: 'Nevolnost',
            tips: ['Popíjejte tekutiny po malých doušcích.'],
            sources: [{ id: 'SRC-NCI', title: 'NCI', url: 'https://www.cancer.gov/' }],
          },
        ],
        level: 'red', // Server liefert (fälschlich) ein Level mit: die Seite darf es nie zeigen
        triage: { level: 'RED', reason_codes: ['F_FEVER'] },
      };
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], receipt, { level: 'RED' });
      await open(page, mock);
      await tiles(page).nth(1).check();
      await next(page).click();
      const acute = page.getByTestId('escalation-acute');
      await expect(acute).toBeVisible();
      const box = await acute.boundingBox();
      expect(box && box.y + box.height, 'Akut-Hinweis im ersten Bildschirm').toBeLessThanOrEqual(
        667,
      );
      // Reihenfolge im Dokument: Akut-Hinweis → Tipps → Bestätigung
      const order = await page
        .locator('[data-testid="escalation-acute"], [data-testid="advice"], h2')
        .evaluateAll((els) =>
          els.map((el) => el.getAttribute('data-testid') ?? el.textContent ?? ''),
        );
      expect(order.indexOf('escalation-acute')).toBeLessThan(order.indexOf('advice'));
      const text = await page.locator('main').innerText();
      expect(text).not.toMatch(/\[[^\]]*\]/); // keine Platzhalter in eckigen Klammern
      expect(text).toContain('155');
      expect(text).not.toMatch(/ADV-/); // Regel-ID nie anzeigen
      expect(text).not.toMatch(/\bRED\b|\bred\b|červen|Ampel|semafor|traffic/i);
      await expect(page.locator('[data-traffic-light]')).toHaveCount(0);
      expect(text.replace(/Při akutních[^.]*155\./, '')).not.toMatch(FORBIDDEN);
      expect(await page.locator('a[href^="tel:"]').count()).toBe(0); // Platzhalter-Nummer nicht anrufbar
      const links = await page
        .locator('main a[href]')
        .evaluateAll((els) => els.map((a) => a.getAttribute('href')));
      expect(links.every((href) => /^https?:[/][/]/.test(href ?? ''))).toBe(true);
    } finally {
      await context.close();
    }
  });

  test('Texte der Sitzungs-API werden als Text angezeigt, nie als HTML oder Skript', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const hostile = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>';
      const question = {
        ...q('fever', 'presence', hostile, hostile),
        options: [
          { value: 0, label: hostile },
          { value: 1, label: 'Ano' },
        ],
      };
      const receipt = {
        ...RECEIPT,
        advice: [
          {
            rule_id: 'ADV-X-01',
            symptom_key: 'x',
            label: hostile,
            tips: [hostile],
            sources: [{ id: 's', title: hostile, url: 'javascript:window.__xss=3' }],
          },
        ],
      };
      await open(page, new SessionMock([question], receipt));
      await expect(page.getByTestId('session-card')).toBeVisible();
      expect(await page.locator('main img, main script').count()).toBe(0);
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByTestId('checkin-confirmation')).toBeVisible();
      expect(await page.locator('main img, main script').count()).toBe(0);
      expect(await page.locator('main a[href^="javascript"]').count()).toBe(0);
      expect(
        await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
      ).toBeUndefined();
    } finally {
      await context.close();
    }
  });

  test('fehlende Sitzungs-API (404) ⇒ Vollformular als Rückfall; Serverfehler ⇒ Wiederholen und Link, kein Rohtext', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      await page.route(SESSIONS, (route) =>
        route.fulfill({ status: 404, json: { code: 'not_found', message: 'x' } }),
      );
      await page.goto('/patient');
      await expect(page.getByTestId('checkin-form')).toBeVisible();
      await page.unroute(SESSIONS);
      await page.route(SESSIONS, (route) =>
        route.fulfill({
          status: 500,
          json: { code: 'boom', message: 'Traceback (most recent call last)' },
        }),
      );
      await page.goto('/patient');
      await expect(page.getByTestId('session-error')).toBeVisible();
      expect(await page.locator('main').innerText()).not.toMatch(/Traceback|boom|500/);
      await expect(page.getByRole('link', { name: /celý dotazník/i })).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test('Sprachwechsel mitten in der Sitzung lädt dieselbe Sitzung neu (gleiche Kennung, neue Sprache)', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([
        q('fever', 'presence', 'Horečka'),
        q('pain', 'severity', 'Bolest'),
      ]);
      await open(page, mock);
      await expect(page.getByTestId('session-card')).toBeVisible();
      await page.locator('select').first().selectOption('en');
      await expect.poll(() => mock.starts.at(-1)?.lang).toBe('en');
      expect(new Set(mock.starts.map((s) => s.client_session_id)).size).toBe(1);
    } finally {
      await context.close();
    }
  });
});

test.describe('Adaptiver Check-in – Verlust des Abschlusses', () => {
  test('Neuladen der Abschlussseite behält den Akut-Hinweis', async ({ browser }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const receipt = {
        ...RECEIPT,
        escalation: {
          level: 'acute',
          text: 'Při akutních obtížích kontaktujte ambulanci nebo volejte 155.',
        },
      };
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], receipt);
      await open(page, mock);
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByTestId('escalation-acute')).toBeVisible();
      const startsBefore = mock.starts.length;
      await page.reload();
      await expect(page.getByTestId('escalation-acute')).toBeVisible({ timeout: 3000 });
      // v2.5: beim Neuladen zuerst GET (Beleg), nie eine neue Sitzung (POST) und keine zweite Antwort
      expect(mock.gets).toBeGreaterThanOrEqual(1);
      expect(mock.starts.length, 'kein neuer POST /me/sessions beim Neuladen').toBe(startsBefore);
      expect(mock.answers.length, 'keine zweite Antwort').toBe(1);
      await expect(page.getByRole('button', { name: 'Nový dotazník' })).toBeVisible();
      // Datenschutz: im Browserspeicher steht nur Kennung/Zustand/Fälligkeit, kein Beleg- oder Antworttext
      const storage = await page.evaluate(() =>
        JSON.stringify({ ...sessionStorage, ...localStorage }),
      );
      expect(storage).not.toMatch(/akutních|Horečka|fever|presence|resp-1|escalation/i);
    } finally {
      await context.close();
    }
  });

  test('Antwort des Abschlusses geht verloren: die Patientin bekommt den Akut-Hinweis trotzdem', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const receipt = {
        ...RECEIPT,
        escalation: {
          level: 'acute',
          text: 'Při akutních obtížích kontaktujte ambulanci nebo volejte 155.',
        },
      };
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], receipt);
      await open(page, mock);
      mock.failNextAnswer = 'ghost';
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByRole('alert')).toBeVisible();
      const startsBefore = mock.starts.length;
      await next(page).click(); // Wiederholen ⇒ 409 session_closed ⇒ zuerst GET, nie neue Sitzung
      await expect(page.getByTestId('escalation-acute')).toBeVisible({ timeout: 3000 });
      expect(mock.gets).toBeGreaterThanOrEqual(1);
      expect(mock.starts.length, 'keine neue Sitzung nach 409').toBe(startsBefore);
    } finally {
      await context.close();
    }
  });

  test('identische Wiederholung der Stopp-Antwort (Server 200 + Beleg) zeigt den Akut-Hinweis', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], ACUTE);
      mock.idempotent = true;
      await open(page, mock);
      mock.failNextAnswer = 'ghost';
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByRole('alert')).toBeVisible();
      await next(page).click();
      await expect(page.getByTestId('escalation-acute')).toBeVisible({ timeout: 3000 });
      expect(mock.answers.length).toBe(2); // beide identisch, keine dritte
      expect(mock.answers[0]).toEqual(mock.answers[1]);
    } finally {
      await context.close();
    }
  });

  test('„Nový dotazník“: neue Kennung, erste Frage; danach Neuladen setzt den NEUEN Check-in fort', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], ACUTE);
      await open(page, mock);
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByTestId('escalation-acute')).toBeVisible();
      const firstId = mock.clientId;
      await page.getByRole('button', { name: 'Nový dotazník' }).click();
      await expect(page.getByTestId('session-card')).toContainText('Horečka');
      await expect(page.getByTestId('escalation-acute')).toHaveCount(0);
      expect(mock.clientId).not.toBe(firstId);
      const secondId = mock.clientId;
      await page.reload(); // offener neuer Check-in: nicht der alte Beleg
      await expect(page.getByTestId('session-card')).toContainText('Horečka');
      await expect(page.getByTestId('escalation-acute')).toHaveCount(0);
      expect(mock.clientId).toBe(secondId);
    } finally {
      await context.close();
    }
  });

  test('nach der nächsten Fälligkeit (Serverzeit) beginnt nach Neuladen ein neuer Check-in, nicht der alte Beleg', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      await page.route('**/api/v1/meta', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1500)); // Serverzeit kommt erst nach dem Start
        await route.fallback();
      });
      // E2E-Backend läuft mit eingefrorener Uhr 2026-10-17T09:00+02:00; Fälligkeit liegt davor
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], ACUTE, {
        due: { next_due_at: '2026-10-16T09:00:00+02:00', overdue: false, interval_days: 3 },
      });
      await open(page, mock);
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByTestId('escalation-acute')).toBeVisible();
      const firstId = mock.clientId;
      await page.reload();
      await expect(page.getByTestId('session-card')).toContainText('Horečka', { timeout: 5000 });
      await expect(page.getByTestId('escalation-acute')).toHaveCount(0);
      expect(mock.clientId).not.toBe(firstId);
    } finally {
      await context.close();
    }
  });

  test('Beleg-Abruf: 404 ⇒ vergessen, normal starten; Serverfehler ⇒ Wiederholen, keine stille neue Sitzung', async ({
    browser,
  }, info) => {
    const { context, page } = await openContext(
      browser,
      String(info.project.use.baseURL),
      'patient2',
      PHONE,
    );
    try {
      const mock = new SessionMock([q('fever', 'presence', 'Horečka')], ACUTE);
      await open(page, mock);
      await tiles(page).nth(1).check();
      await next(page).click();
      await expect(page.getByTestId('escalation-acute')).toBeVisible();
      const startsBefore = mock.starts.length;
      mock.getStatus = 500;
      await page.reload();
      await expect(page.getByRole('alert')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Zkusit znovu' })).toBeVisible();
      await expect(page.getByTestId('escalation-acute')).toHaveCount(0);
      expect(mock.starts.length, 'Serverfehler startet keine neue Sitzung').toBe(startsBefore);
      mock.getStatus = null;
      await page.getByRole('button', { name: 'Zkusit znovu' }).click();
      await expect(page.getByTestId('escalation-acute')).toBeVisible({ timeout: 3000 });
      // 404 (unbekannt/fremd) ⇒ Kennungen vergessen ⇒ normaler Start (neue Kennung)
      const oldId = mock.clientId;
      mock.getStatus = 404;
      mock.closed = false;
      mock.index = 0;
      await page.reload();
      await expect(page.getByTestId('session-card')).toContainText('Horečka');
      expect(mock.clientId).not.toBe(oldId);
    } finally {
      await context.close();
    }
  });
});
