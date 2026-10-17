import { cleanup, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import { CONFIG } from '../testing/cockpit-fixtures';
import { ERROR_BODY, serve, setViewport } from '../testing/cockpit-server';
import { ADMIN, ANCHOR, CLINICIAN } from '../testing/fixtures';
import { ADVICE_FILE, TRIAGE_RULE_CARD } from '../testing/triage-fixtures';

async function openSettings(options: Parameters<typeof serve>[0] = {}) {
  const fetchMock = serve({
    me: CLINICIAN,
    config: () => jsonResponse({ ...CONFIG, advice: ADVICE_FILE }),
    ...options,
  });
  renderApp('/clinic/settings');
  await screen.findByTestId('rules-section');
  return fetchMock;
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

describe('Einstellungen: Triage-Regelkarte (F-11, nur lesen)', () => {
  it('zeigt je Profil Banner, Blätter/Tiefe, Regeln rot zuerst, Böden mit Schloss und Platzhalter', async () => {
    await openSettings();
    const section = await screen.findByTestId('triage-rules-section');
    expect(
      within(section).getByRole('heading', { level: 2, name: 'Triage-Regelkarte' }),
    ).toBeVisible();
    expect(await within(section).findByTestId('triage-kb')).toHaveTextContent(
      'Wissensbasis 01234567',
    );

    const profiles = within(section).getAllByTestId('triage-profile');
    expect(profiles).toHaveLength(2);
    const first = within(profiles[0] as HTMLElement);
    expect(profiles[0]).toHaveAttribute('open'); // erstes Profil offen
    const banner = first.getByTestId('triage-verification');
    expect(banner).toHaveTextContent(
      'Umsetzungstreue geprüft (Baum = Regelwerk): vollständig, alle 12345 Punkte',
    );
    expect(banner).toHaveTextContent('Untertriage 0 · Obertriage 0 · Monotonie-Verletzungen 0');
    expect(banner).toHaveAttribute('data-clean', 'true');
    expect(banner).toHaveAttribute('data-scope', 'exhaustive');
    expect(banner).toHaveAttribute('data-passed', 'true');
    expect(banner).toHaveTextContent('✓');
    expect(banner).not.toHaveTextContent('Verifiziert');
    // „Platzhalter, klinisch nicht freigegeben“ direkt neben der Aussage zur Umsetzungstreue
    expect(within(banner).getByTestId('triage-banner-placeholder')).toHaveTextContent(
      'Regelwerk: Platzhalter, klinisch nicht freigegeben.',
    );
    expect(first.getByTestId('triage-trees')).toHaveTextContent(
      'Blätter/Tiefe: gelb 9/4, rot 5/3 · tree-7f3a',
    );

    // Regeln: rot zuerst, auch wenn der Server gelb vorn liefert
    const rules = within(first.getByTestId('triage-rules')).getAllByRole('listitem');
    expect(rules.map((rule) => rule.getAttribute('data-level'))).toEqual(['RED', 'YELLOW']);
    expect(rules[0]).toHaveTextContent('Rot: Durchfall Schwere ≥ 3');

    // Böden: gesperrte mit Schloss und Wort
    const floors = within(first.getByTestId('triage-floors')).getAllByRole('listitem');
    expect(floors[0]).toHaveAttribute('data-locked', 'true');
    expect(floors[0]).toHaveTextContent('gesperrt');
    expect(floors[0]?.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(floors[1]).toHaveAttribute('data-locked', 'false');
    expect(floors[1]?.querySelector('svg')).toBeNull();

    expect(first.getByTestId('triage-placeholders')).toHaveTextContent(
      'Schwellen: Platzhalter, nicht klinisch freigegeben',
    );
    expect(first.getByText('Böden: Platzhalter')).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(findForbiddenClinician(section.textContent)).toEqual([]);
  });

  it('kennzeichnet ein Profil mit Abweichungen im Banner (Text und Symbol, nie nur Farbe)', async () => {
    await openSettings();
    const section = await screen.findByTestId('triage-rules-section');
    const secondProfile = (
      await within(section).findAllByTestId('triage-profile')
    )[1] as HTMLElement;
    expect(secondProfile).not.toHaveAttribute('open'); // nur das erste Profil ist offen
    await userEvent.setup().click(secondProfile.querySelector('summary') as HTMLElement);
    const second = within(secondProfile);
    const banner = second.getByTestId('triage-verification');
    expect(banner).toHaveAttribute('data-clean', 'false');
    expect(banner).toHaveTextContent(
      'Umsetzungstreue mit Abweichungen: Stichprobe von 800 Punkten',
    );
    expect(banner).toHaveTextContent('Untertriage 1 · Obertriage 0 · Monotonie-Verletzungen 2');
    expect(banner).toHaveAttribute('data-scope', 'sampled');
    expect(banner).toHaveAttribute('data-passed', 'false');
    expect(banner).toHaveTextContent('!');
    expect(second.getByText('Keine Regeln.')).toBeVisible();
    expect(second.getByText('Keine Schutzböden.')).toBeVisible();
  });

  it('zeigt bei fehlender Route (404) einen ehrlichen Hinweis und die übrigen Einstellungen bleiben', async () => {
    await openSettings({ triageConfig: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    expect(await screen.findByTestId('triage-rules-unavailable')).toHaveTextContent(
      'Die Triage ist noch nicht verfügbar.',
    );
    expect(screen.getByTestId('rules-section')).toBeVisible();
  });

  it('zeigt die Regelkarte auch der Administration ohne Eingabefelder', async () => {
    await openSettings({ me: ADMIN });
    const section = await screen.findByTestId('triage-rules-section');
    await within(section).findAllByTestId('triage-profile');
    expect(within(section).queryByRole('textbox')).toBeNull();
    expect(within(section).queryByRole('checkbox')).toBeNull();
    expect(within(section).queryByRole('button', { name: /Speichern/ })).toBeNull();
  });

  it('übersetzt die Karte (en) ohne Rohschlüssel', async () => {
    await i18n.changeLanguage('en');
    await openSettings();
    const section = await screen.findByTestId('triage-rules-section');
    await within(section).findAllByTestId('triage-profile');
    expect(
      within(section).getByRole('heading', { level: 2, name: 'Triage rule card' }),
    ).toBeVisible();
    expect(section.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
    expect(TRIAGE_RULE_CARD.profiles.length).toBe(2);
  });
});

describe('Einstellungen: Tipp-Regeln (F-11, nur lesen)', () => {
  it('zeigt ID, Symptom, Bereich, Anzahl Tipps, Quelle und Status je Regel', async () => {
    await openSettings();
    const section = await screen.findByTestId('advice-rules');
    expect(within(section).getByRole('heading', { level: 2, name: 'Tipp-Regeln' })).toBeVisible();
    const table = within(section).getByTestId('advice-rules-table');
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((cell) => cell.textContent),
    ).toEqual(['ID', 'Symptom', 'Bereich', 'Tipps', 'Quelle', 'Status']);
    const rows = within(table).getAllByRole('row').slice(1);
    expect(rows).toHaveLength(2);
    // Bereich: max_value, sonst Standard 4; Quelle mit Titel, unbekannte Kennung bleibt sichtbar
    expect(rows[0]).toHaveTextContent('ADV-NAUSEA-01');
    expect(rows[0]).toHaveTextContent('2–3');
    expect(rows[0]).toHaveTextContent('Nausea and Vomiting, NCI');
    expect(rows[0]).toHaveTextContent('draft');
    expect(rows[1]).toHaveTextContent('4–4');
    expect(rows[1]).toHaveTextContent('Nausea and Vomiting, NCI; SRC-UNKNOWN');
    expect(findForbiddenClinician(section.textContent)).toEqual([]);
  });

  it('meldet fehlende Tipp-Regeln ehrlich statt eine leere Tabelle zu zeigen', async () => {
    await openSettings({ config: () => jsonResponse(CONFIG) });
    expect(await screen.findByTestId('advice-rules-empty')).toHaveTextContent(
      'Keine Tipp-Regeln anzuzeigen.',
    );
  });
});

describe('Einstellungen: Prüfumfang im Verifikationsbanner (F-11F)', () => {
  const card = (scope: string | undefined, under = 0) => ({
    ...TRIAGE_RULE_CARD,
    profiles: [
      {
        ...TRIAGE_RULE_CARD.profiles[0],
        verification: { points: 5000, under, over: 0, monotone_violations: 0, scope },
      },
    ],
  });

  it('nennt bei sampled_raw „Stichprobe von N Punkten“ und vergibt keinen Haken', async () => {
    await openSettings({ triageConfig: () => jsonResponse(card('sampled_raw')) });
    const banner = await screen.findByTestId('triage-verification');
    expect(banner).toHaveTextContent('Stichprobe von 5000 Punkten');
    expect(banner).toHaveAttribute('data-scope', 'sampled');
    expect(banner).toHaveAttribute('data-passed', 'false');
    expect(banner).not.toHaveTextContent('✓');
    expect(banner).not.toHaveTextContent('vollständig');
  });

  it.each(['exhaustive_raw', 'exhaustive_orbit'])(
    'nennt bei %s „vollständig, alle N Punkte“ mit Haken',
    async (scope) => {
      await openSettings({ triageConfig: () => jsonResponse(card(scope)) });
      const banner = await screen.findByTestId('triage-verification');
      expect(banner).toHaveTextContent('vollständig, alle 5000 Punkte');
      expect(banner).toHaveAttribute('data-passed', 'true');
      expect(banner).toHaveTextContent('✓');
    },
  );

  it('vergibt bei vollständiger Prüfung mit Abweichungen keinen Haken', async () => {
    await openSettings({ triageConfig: () => jsonResponse(card('exhaustive_raw', 2)) });
    const banner = await screen.findByTestId('triage-verification');
    expect(banner).toHaveTextContent(
      'Umsetzungstreue mit Abweichungen: vollständig, alle 5000 Punkte',
    );
    expect(banner).toHaveAttribute('data-passed', 'false');
    expect(banner).not.toHaveTextContent('✓');
  });

  it('erhebt ohne Angabe zum Umfang keinen Anspruch auf Vollständigkeit', async () => {
    await openSettings({ triageConfig: () => jsonResponse(card(undefined)) });
    const banner = await screen.findByTestId('triage-verification');
    expect(banner).toHaveTextContent('Umfang nicht angegeben (5000 Punkte)');
    expect(banner).toHaveAttribute('data-scope', 'unknown');
    expect(banner).not.toHaveTextContent('✓');
  });

  it('übersetzt Banner und Umfang (cs/en) ohne das Wort „verifiziert/ověřeno“', async () => {
    for (const [lang, text, forbidden] of [
      [
        'cs',
        /Věrnost implementace ověřena \(strom = pravidla\): úplně, všech 12345 bodů/,
        /Ověřeno/,
      ],
      [
        'en',
        /Implementation fidelity checked \(tree = rules\): complete, all 12345 points/,
        /Verified/,
      ],
    ] as const) {
      await i18n.changeLanguage(lang);
      await openSettings();
      const banner = (await screen.findAllByTestId('triage-verification'))[0] as HTMLElement;
      expect(banner.textContent).toMatch(text);
      expect(banner.textContent).not.toMatch(forbidden);
      cleanup();
    }
  });
});
