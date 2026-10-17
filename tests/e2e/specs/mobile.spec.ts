import { expect, test, type Page } from '@playwright/test';

/** Basis-Smoke bei 375 px Breite: h1 sichtbar, kein horizontales Scrollen (docs/RULES.md §4). */
test.use({ viewport: { width: 375, height: 800 } });

async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, 'horizontaler Überstand in px').toBeLessThanOrEqual(0);
}

test('Startseite bei 375 px', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  // platform-fix G-07: Platzhalter nur ohne Challenge-Paket.
  await expect(page.getByTestId('meta-list')).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test('Anmeldung bei 375 px', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expect(page.getByLabel('Benutzername')).toBeVisible();
  await expect(page.getByTestId('demo-accounts')).toBeVisible();
  await expectNoHorizontalScroll(page);
});

test('Design-System-Showcase bei 375 px', async ({ page }) => {
  await page.goto('/design-system');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
});
