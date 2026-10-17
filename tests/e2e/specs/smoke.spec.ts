import { expect, test } from '@playwright/test';

/** E2E-Smoke der leeren Plattform gegen das echte Backend (Wegwerf-DB, neutrale Demo-Konten). */

test('Start: Platzhalter ohne Challenge, Demo-Hinweis, eine h1', async ({ page }) => {
  const meta = (await (await page.request.get('/api/v1/meta')).json()) as {
    challenge_loaded: boolean;
  };
  await page.goto('/');
  // platform-fix G-07: mit geladenem Challenge-Paket gibt es den Platzhalter nicht.
  if (meta.challenge_loaded) {
    await expect(page.getByTestId('meta-list')).toBeVisible();
    await expect(page.getByTestId('no-challenge')).toHaveCount(0);
  } else {
    await expect(page.getByTestId('no-challenge')).toHaveText(
      'Noch keine Challenge-Funktionen geladen',
    );
  }
  await expect(page.getByTestId('demo-banner')).toBeVisible();
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(page.getByTestId('meta-version')).toHaveText('0.1.0');
});

test('Anmeldung mit Demo-Konto und Abmeldung', async ({ page }) => {
  await page.goto('/login');
  await page.getByTestId('demo-account-admin').click();
  await expect(page.getByLabel('Benutzername')).toHaveValue('admin');
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click();
  await expect(page.getByTestId('session-info')).toContainText('Admin (Demo)');
  await page.getByRole('button', { name: 'Abmelden' }).click();
  await expect(page).toHaveURL(/\/login$/);
  const me = await page.request.get('/api/v1/auth/me');
  expect(me.status()).toBe(401);
});

test('Serverseitige Autorisierung: ohne Sitzung 401, Sicherheitsheader gesetzt', async ({
  request,
}) => {
  const response = await request.get('/api/v1/auth/me');
  expect(response.status()).toBe(401);
  expect(response.headers()['cache-control']).toBe('no-store');
  expect(response.headers()['x-content-type-options']).toBe('nosniff');
});

test('Design-System-Showcase im Demo-Modus', async ({ page }) => {
  await page.goto('/design-system');
  await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  await expect(page.locator('[data-status]')).toHaveCount(4);
});
