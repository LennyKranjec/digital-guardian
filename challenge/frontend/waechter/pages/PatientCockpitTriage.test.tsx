import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import { ERROR_BODY, BASE, callUrl, serve, setViewport } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';
import { TRIAGE_RED, TRIAGE_YELLOW } from '../testing/triage-fixtures';

const triageCalls = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls.filter(([input]) => callUrl(input).startsWith(`${BASE}/triage`));

async function openPanel(options: Parameters<typeof serve>[0] = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await user.click(await screen.findByTestId('cockpit-tab-triage')); // Tab „Triage-Details“ (T-32)
  const panel = await screen.findByTestId('triage-panel');
  return { fetchMock, user, panel };
}

beforeEach(() => {
  register(pluginApi);
  setViewport(false);
  localStorage.clear();
  vi.setSystemTime(new Date(ANCHOR));
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  resetRegistry();
  localStorage.clear();
  await i18n.changeLanguage('de');
});

describe('Cockpit: Triage-Befund (F-11)', () => {
  it('bleibt eingeklappt, lädt nichts vorab und hält die einzige h1 (S5 unverändert)', async () => {
    const { fetchMock, panel } = await openPanel();
    expect(within(panel).getByText('Triage-Befund')).toBeVisible();
    expect(panel).not.toHaveAttribute('open');
    expect(triageCalls(fetchMock)).toHaveLength(0);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    // Platz: eigener Bereich unter dem Raster, nicht in der Kopf-/Meldungsspalte
    const grid = screen.getByTestId('cockpit-grid');
    expect(grid.contains(panel)).toBe(false);
  });

  it('zeigt Rot mit Schutzboden: Stufe als Text + Symbol, Schild zuerst, Versionen, Platzhalter-Hinweis', async () => {
    const { fetchMock, user, panel } = await openPanel();
    await user.click(within(panel).getByText('Triage-Befund'));
    const finding = await within(panel).findByTestId('triage-finding');

    expect(triageCalls(fetchMock)).toHaveLength(1);
    expect(callUrl(triageCalls(fetchMock)[0]?.[0] as string)).toBe(`${BASE}/triage`);
    expect(within(finding).getByText('Stufe Rot')).toBeVisible();
    expect(within(finding).queryByTestId('triage-span')).toBeNull(); // eine einzige Stufe
    expect(within(finding).queryByTestId('triage-incomplete')).toBeNull();

    // Reihenfolge: Schutzboden (Schloss) zuerst, dann Pfad, dann Blatt
    const reasons = within(finding).getByTestId('triage-reasons');
    const items = within(reasons).getAllByRole('listitem');
    expect(items.map((item) => item.getAttribute('data-kind'))).toEqual(['shield', 'path', 'leaf']);
    expect(items[0]).toHaveTextContent('Schutzboden: Fieber ja: Mindeststufe Rot');
    expect(items[0]?.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(items[1]).toHaveTextContent('Beteiligt: diarrhea');

    expect(within(finding).getByTestId('triage-asked')).toHaveTextContent(
      'Gefragt: 5 von 14 Fragen',
    );
    expect(within(finding).getByTestId('triage-versions')).toHaveTextContent(
      'Regelwerk a1b2c3d4 · Baum tree-7f3a · chemo-folfox',
    );
    expect(within(finding).getByTestId('triage-placeholder')).toHaveTextContent(
      'Regelwerk: Platzhalter, klinisch nicht freigegeben.',
    );
  });

  it('zeigt Kontrafaktische getrennt; der Schild-Hinweis steht als eigener Schloss-Eintrag, nicht hinter „würde sinken, wenn …“', async () => {
    const { user, panel } = await openPanel();
    await user.click(within(panel).getByText('Triage-Befund'));
    const finding = await within(panel).findByTestId('triage-finding');
    const lower = within(finding).getByTestId('triage-lower');
    expect(lower).toHaveTextContent('Würde sinken, wenn …');
    expect(lower).toHaveTextContent('Durchfall (Schwere) auf ≤ 2 sinkt');
    expect(lower).not.toHaveTextContent('Boden FLOOR-FEVER'); // kein Teil des Bedingungssatzes
    const shield = within(finding).getByTestId('triage-shield-notes');
    expect(shield).toHaveTextContent('Schutzboden: Boden FLOOR-FEVER verhindert Senkung');
    expect(shield.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(within(finding).getByTestId('triage-raise')).toHaveTextContent(
      'Nächste Verschlechterung …wenn ein weiteres Symptom Stufe 3 erreicht',
    );
  });

  it('zeigt einen Schild-Hinweis auch dann, wenn es sonst keine Kontrafaktische gibt', async () => {
    const { user, panel } = await openPanel({
      triage: () =>
        jsonResponse({
          ...TRIAGE_RED,
          counterfactuals: [
            { direction: 'lower', kind: 'shield', text: 'Boden X verhindert Senkung' },
          ],
        }),
    });
    await user.click(within(panel).getByText('Triage-Befund'));
    const finding = await within(panel).findByTestId('triage-finding');
    expect(within(finding).getByTestId('triage-shield-notes')).toHaveTextContent(
      'Boden X verhindert Senkung',
    );
    expect(within(finding).queryByTestId('triage-lower')).toBeNull();
    expect(within(finding).queryByText('Keine Änderung anzuzeigen.')).toBeNull();
  });

  it('zeigt die Tipps an die Patientin mit Regel-ID, Symptom, Wert und angezeigt/unterdrückt', async () => {
    const { user, panel } = await openPanel();
    await user.click(within(panel).getByText('Triage-Befund'));
    const table = await within(panel).findByTestId('triage-tips-table');
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('ADV-DIARRHEA-01');
    expect(rows[0]).toHaveTextContent('angezeigt');
    expect(rows[1]).toHaveTextContent('ADV-FEVER-01');
    expect(rows[1]).toHaveTextContent('unterdrückt (akut)');
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual(['Regel', 'Symptom', 'Wert', 'Status']);
  });

  it('zeigt Gelb mit Pfad, Spanne und Unvollständig-Hinweis ohne Schild und ohne Tipps', async () => {
    const { user, panel } = await openPanel({ triage: () => jsonResponse(TRIAGE_YELLOW) });
    await user.click(within(panel).getByText('Triage-Befund'));
    const finding = await within(panel).findByTestId('triage-finding');
    expect(within(finding).getByText('Stufe Gelb')).toBeVisible();
    expect(within(finding).getByTestId('triage-span')).toHaveTextContent(
      'Mögliche Spanne: Grün bis Rot',
    );
    expect(within(finding).getByTestId('triage-incomplete')).toHaveTextContent('Unvollständig');
    const kinds = within(within(finding).getByTestId('triage-reasons'))
      .getAllByRole('listitem')
      .map((item) => item.getAttribute('data-kind'));
    expect(kinds).toEqual(['path', 'incomplete']);
    expect(within(finding).queryByText('Schutzboden:')).toBeNull();
    expect(
      within(finding).getByText('Zu dieser Antwort wurden keine Tipps angezeigt.'),
    ).toBeVisible();
    expect(within(finding).getByTestId('triage-lower')).toBeVisible();
    expect(within(finding).queryByTestId('triage-raise')).toBeNull();
  });

  it('zeigt bei 404 einen dezenten Hinweis statt eines Fehlers', async () => {
    const { user, panel } = await openPanel({
      triage: () => jsonResponse(ERROR_BODY('not_found'), 404),
    });
    await user.click(within(panel).getByText('Triage-Befund'));
    expect(await within(panel).findByTestId('triage-unavailable')).toHaveTextContent(
      'Die Triage ist noch nicht verfügbar.',
    );
    expect(within(panel).queryByRole('button', { name: 'Erneut versuchen' })).toBeNull();
  });

  it('zeigt bei einem Serverfehler eine Meldung mit „Erneut versuchen“', async () => {
    let attempt = 0;
    const { user, panel } = await openPanel({
      triage: () => {
        attempt += 1;
        return attempt === 1 ? jsonResponse(ERROR_BODY('boom'), 500) : jsonResponse(TRIAGE_RED);
      },
    });
    await user.click(within(panel).getByText('Triage-Befund'));
    const retry = await within(panel).findByRole('button', {
      name: /Erneut versuchen|Wiederholen|Noch einmal/,
    });
    await user.click(retry);
    expect(await within(panel).findByTestId('triage-finding')).toBeVisible();
  });

  it('klappt auf und zu (Summary ist ein 44-px-Ziel, die Tastatur bedient sie nativ) und bleibt ohne verbotene Wendungen', async () => {
    const { user, panel } = await openPanel();
    const summary = panel.querySelector('summary') as HTMLElement;
    expect(summary.className).toContain('min-h-11');
    await user.click(summary);
    const finding = await within(panel).findByTestId('triage-finding');
    expect(panel).toHaveAttribute('open');
    expect(findForbiddenClinician(finding.textContent)).toEqual([]);
    await user.click(summary);
    expect(panel).not.toHaveAttribute('open');
  });

  it('übersetzt den Befund (en) ohne Rohschlüssel', async () => {
    await i18n.changeLanguage('en');
    const { user, panel } = await openPanel();
    await user.click(within(panel).getByText('Triage finding'));
    const finding = await within(panel).findByTestId('triage-finding');
    expect(within(finding).getByText('Level red')).toBeVisible();
    expect(finding.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
  });
});
