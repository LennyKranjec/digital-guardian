import {
  expect,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';

/** Gemeinsame Hilfen für den Kernpfad (E2E-1). Alle Selektoren: data-testid, Rollen oder API-Daten. */

export const API = '/api/v1/waechter';
export const CSRF = { 'X-Requested-With': 'fetch' } as const;
export const PASSWORD = 'demo-passwort-2026';
/** Ankerzeit des Szenarios (APP_FROZEN_NOW in tests/e2e/playwright.config.ts). */
export const ANCHOR = '2026-10-17T09:00:00+02:00';

/**
 * Verbotsliste der Patientenseite (COMMON §2): Bewertung, Alarm, Diagnose, Beruhigung, Zusage.
 * Entspricht der Liste in challenge/backend/test_a3_realcontent.py.
 */
export const FORBIDDEN =
  /ampel|semafor|traffic|alarm|\balert|červen|žlut|\bred\b|yellow|\bgrade\b|stupeň|ctcae|diagnos|doporuč|recommend|empfehl|keine sorge|don.?t worry|no need to worry|nemusíte se bát|v pořádku|alles in ordnung|all is (fine|well)|we will (contact|call)|ozveme se|zavoláme|wir (melden|rufen)|notfall|emergency|nouz/i;

export async function apiLogin(request: APIRequestContext, username: string): Promise<void> {
  const response = await request.post('/api/v1/auth/login', {
    headers: CSRF,
    data: { username, password: PASSWORD },
  });
  expect(response.status(), `Login ${username}`).toBe(200);
}

export async function getJson<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(path);
  expect(response.status(), path).toBe(200);
  return (await response.json()) as T;
}

/** Neuer Browserkontext mit eigener Größe, Sprache und angemeldetem Konto (Cookie per API-Login). */
export async function openContext(
  browser: Browser,
  baseURL: string,
  username: string,
  viewport: { width: number; height: number },
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL, viewport, locale: 'cs-CZ' });
  const page = await context.newPage();
  await apiLogin(page.request, username);
  return { context, page };
}

export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

/** Kleinste berechnete Schriftgröße sichtbarer Textknoten (px) und die Verursacher. */
export async function smallText(page: Page, minimum = 16): Promise<string[]> {
  return page.evaluate((min) => {
    const found: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const text = (node.textContent ?? '').trim();
      const element = node.parentElement;
      if (text && element && element.getClientRects().length > 0) {
        const style = getComputedStyle(element);
        const size = parseFloat(style.fontSize);
        if (style.visibility !== 'hidden' && size < min)
          found.push(`${size}px: ${text.slice(0, 40)}`);
      }
      node = walker.nextNode();
    }
    return found;
  }, minimum);
}

/** Interaktive Elemente, die kleiner als 44 × 44 px sind (Touchziel). */
export async function smallTargets(page: Page, selector: string, minimum = 44): Promise<string[]> {
  return page.evaluate(
    ([sel, min]) => {
      const bad: string[] = [];
      for (const element of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
        const box = element.getBoundingClientRect();
        if (box.width === 0 || box.height === 0) continue;
        if (box.height < min || box.width < min)
          bad.push(
            `${Math.round(box.width)}x${Math.round(box.height)}: ${(element.innerText || element.tagName).slice(0, 30)}`,
          );
      }
      return bad;
    },
    [selector, minimum] as const,
  );
}

/**
 * Triage-Kaltstart abwarten (T-16: Kompilieren und Verifizieren aller Profile beim ersten Zugriff je
 * Prozess, gemessen 25-45 s; der Hintergrund-Warmup läuft beim Start des Backends). Ohne diesen Schritt
 * überschreitet die erste Sitzung oder Regelkarte das Testzeitlimit. Gibt die Wartezeit in ms zurück.
 */
export async function warmTriage(browser: Browser, baseURL: string): Promise<number> {
  const started = Date.now();
  const { context, page } = await openContext(browser, baseURL, 'doctor', {
    width: 1366,
    height: 768,
  });
  try {
    const response = await page.request.get(`${API}/config/triage?lang=cs`, { timeout: 170_000 });
    expect([200, 404], 'Triage-Regelkarte').toContain(response.status());
  } finally {
    await context.close();
  }
  return Date.now() - started;
}
