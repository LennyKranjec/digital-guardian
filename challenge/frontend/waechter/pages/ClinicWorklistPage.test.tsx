import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import {
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { SEEN_STORAGE_KEY } from '../model/notifications';
import { metaBody, overviewForRow } from '../testing/cockpit-fixtures';
import { stripLang } from '../testing/cockpit-server';
import {
  ANCHOR,
  CLINICIAN,
  NOTIFICATIONS,
  PATIENT,
  WORKLIST,
  WORKLIST_NAMES,
} from '../testing/fixtures';

const ERROR_BODY = (code: string) => ({ code, message: code, field_errors: [] });

/** Gemockter Server für die Klinikseiten. */
function serve(options: {
  me?: unknown;
  meta?: Record<string, unknown>;
  worklist?: () => Response;
  notifications?: () => Response;
}) {
  return mockFetch((rawUrl) => {
    const url = stripLang(rawUrl);
    if (url.endsWith('/auth/me')) return jsonResponse(options.me ?? CLINICIAN);
    if (url.endsWith('/meta')) return jsonResponse(options.meta ?? metaBody());
    const overview = /\/waechter\/patients\/([^/]+)\/overview$/.exec(url);
    if (overview) {
      const row = WORKLIST.find((entry) => entry.patient_id === overview[1]);
      return row ? jsonResponse(overviewForRow(row)) : jsonResponse(ERROR_BODY('not_found'), 404);
    }
    if (url.endsWith('/waechter/patients')) return options.worklist?.() ?? jsonResponse(WORKLIST);
    if (url.includes('/waechter/notifications')) {
      return options.notifications?.() ?? jsonResponse([]);
    }
    return defaultApiResponse(url);
  });
}

/** jsdom kennt keine Medienabfragen: Breite ≥ 768 px (Tabelle) oder schmal (Karten) vorgeben. */
function setViewport(wide: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({
      matches: wide && query.includes('min-width: 768px'),
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

function rowNames(): (string | undefined)[] {
  return screen
    .getAllByTestId('worklist-row')
    .map((row) => WORKLIST_NAMES.find((name) => row.textContent.includes(name)));
}

function rowFor(name: string): HTMLElement {
  const row = screen
    .getAllByTestId('worklist-row')
    .find((candidate) => candidate.textContent.includes(name));
  if (!row) throw new Error(`Zeile für ${name} fehlt`);
  return row;
}

beforeEach(() => {
  register(pluginApi);
  setViewport(false);
  localStorage.clear();
  vi.setSystemTime(new Date(ANCHOR));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  resetRegistry();
  localStorage.clear();
});

describe('Arbeitsliste: Inhalt (Kartenansicht, 375 px)', () => {
  it('übernimmt die Serverreihenfolge unverändert', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    expect(rowNames()).toEqual(WORKLIST_NAMES);
    expect(WORKLIST_NAMES).toEqual(['Anna Grün', 'Rita Rot', 'Gerda Grau', 'Gustav Gelb']);
  });

  it('zeigt die Ampel als Icon und Text (nie nur Farbe)', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const expected: Record<string, [string, string]> = {
      'Anna Grün': ['green', 'Keine offene Meldung'],
      'Rita Rot': ['red', 'Sofort prüfen'],
      'Gerda Grau': ['grey', 'Daten fehlen (unbekannt)'],
      'Gustav Gelb': ['yellow', 'Prüfen'],
    };
    for (const [name, [level, text]] of Object.entries(expected)) {
      const light = rowFor(name).querySelector('[data-traffic-light]');
      expect(light, name).not.toBeNull();
      expect(light?.getAttribute('data-traffic-light')).toBe(level);
      expect(light?.textContent).toBe(text);
      expect(light?.querySelector('svg')).not.toBeNull();
    }
  });

  it('zeigt Name, Pseudonym, „synthetisch“, Regime, Zyklustag, Meldung und Anzahl', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const red = within(rowFor('Rita Rot'));
    expect(red.getByText('SYN-0001')).toBeInTheDocument();
    expect(red.getByText('synthetisch')).toBeInTheDocument();
    expect(red.getByText('Regime A')).toBeInTheDocument();
    expect(red.getByText('Zyklustag 8')).toBeInTheDocument();
    expect(red.getByText('Fieber gemeldet')).toBeInTheDocument();
    expect(red.getByText('Offene Meldungen: 2')).toBeInTheDocument();
    // ohne Regime-Bezeichnung und Zyklustag: Kennung des Regimes, keine Zyklusangabe
    const grey = within(rowFor('Gerda Grau'));
    expect(grey.getByText('regimen-b')).toBeInTheDocument();
    expect(grey.queryByText(/Zyklustag/)).not.toBeInTheDocument();
    // ohne Meldung
    expect(within(rowFor('Anna Grün')).getByText('Keine Meldung')).toBeInTheDocument();
  });

  it('zeigt letzte Eingabe und nächsten Termin relativ und absolut (Europe/Prague)', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const red = within(rowFor('Rita Rot'));
    expect(red.getByText('vor 3 Stunden')).toBeInTheDocument();
    expect(red.getByText(/17\.10\.2026.*06:00/)).toBeInTheDocument();
    expect(red.getByText('in 3 Tagen')).toBeInTheDocument();
    expect(red.getByText(/20\.10\.2026.*10:00/)).toBeInTheDocument();
    expect(within(rowFor('Anna Grün')).getByText('vor 30 Minuten')).toBeInTheDocument();
    expect(within(rowFor('Gustav Gelb')).getByText('gestern')).toBeInTheDocument();
  });

  it('zeigt ohne server_now nur absolute Zeiten (nie gegen die Browseruhr gerechnet)', async () => {
    serve({ meta: metaBody(false) });
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const red = within(rowFor('Rita Rot'));
    expect(red.getByText(/17\.10\.2026.*06:00/)).toBeInTheDocument();
    expect(red.queryByText('vor 3 Stunden')).not.toBeInTheDocument();
    expect(red.queryByText('in 3 Tagen')).not.toBeInTheDocument();
  });

  it('zeigt fehlende Eingabe und fehlenden Termin als Text', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const grey = within(rowFor('Gerda Grau'));
    expect(grey.getByText('Noch keine Eingabe')).toBeInTheDocument();
    expect(grey.getByText('Kein Termin geplant')).toBeInTheDocument();
  });

  it('zeigt die Zusatzfelder des Vertrags v1.3: quittiert/weiter bestehend, Auswertung ausstehend, Tage ohne Eingabe', async () => {
    const rows = WORKLIST.map((row) =>
      row.patient_id === 'pat-1'
        ? { ...row, persisting: true, evaluation_pending: true, days_without_response: 4 }
        : row,
    );
    serve({ worklist: () => jsonResponse(rows) });
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const red = within(rowFor('Rita Rot'));
    expect(red.getByText('Quittiert, Wert besteht weiter')).toBeInTheDocument();
    expect(red.getByText('Auswertung ausstehend')).toBeInTheDocument();
    expect(red.getByText('Tage ohne Eingabe: 4')).toBeInTheDocument();
    const green = within(rowFor('Anna Grün'));
    expect(green.queryByText('Auswertung ausstehend')).not.toBeInTheDocument();
    expect(green.queryByText(/Tage ohne Eingabe/)).not.toBeInTheDocument();
  });

  it('zeigt eine zukünftige „letzte Eingabe“ (Uhrabweichung) nur absolut', async () => {
    const future = WORKLIST.map((row) =>
      row.patient_id === 'pat-1' ? { ...row, last_response_at: '2026-10-17T12:00:00+02:00' } : row,
    );
    serve({ worklist: () => jsonResponse(future) });
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const red = within(rowFor('Rita Rot'));
    expect(red.getByText(/17\.10\.2026.*12:00/)).toBeInTheDocument();
    expect(red.queryByText(/in 3 Stunden/)).not.toBeInTheDocument();
  });

  it('hat genau eine h1 und eine benannte Liste', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Arbeitsliste');
    expect(screen.getByRole('list', { name: 'Patientinnen und Patienten' })).toBeInTheDocument();
  });
});

describe('Arbeitsliste: Navigation', () => {
  it('führt in der Kartenansicht per Klick auf die Karte zur Patientenseite', async () => {
    serve({});
    const user = userEvent.setup();
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const links = within(screen.getByTestId('worklist-cards')).getAllByRole('link');
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/clinic/patients/pat-4',
      '/clinic/patients/pat-1',
      '/clinic/patients/pat-3',
      '/clinic/patients/pat-2',
    ]);
    await user.click(within(rowFor('Rita Rot')).getByText('Fieber gemeldet'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Rita Rot' })).toBeVisible();
    expect(screen.getByText('SYN-0001')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('zeigt ab 768 px eine Tabelle mit Spaltenköpfen und Serverreihenfolge', async () => {
    setViewport(true);
    serve({});
    renderApp('/clinic');
    const table = await screen.findByTestId('worklist-table');
    expect(screen.queryByTestId('worklist-cards')).not.toBeInTheDocument();
    expect(
      within(table)
        .getAllByRole('columnheader')
        .map((header) => header.textContent),
    ).toEqual([
      'Ampel',
      'Patient:in',
      'Therapie',
      'Meldungen',
      'Letzte Eingabe',
      'Nächster Termin',
    ]);
    expect(rowNames()).toEqual(WORKLIST_NAMES);
    expect(within(table).getByRole('link', { name: 'Rita Rot' })).toHaveAttribute(
      'href',
      '/clinic/patients/pat-1',
    );
  });

  it('macht in der Tabelle die ganze Zeile klickbar', async () => {
    setViewport(true);
    serve({});
    const user = userEvent.setup();
    renderApp('/clinic');
    await screen.findByTestId('worklist-table');
    await user.click(within(rowFor('Gustav Gelb')).getByText('Übelkeit nimmt zu'));
    expect(await screen.findByRole('heading', { level: 1, name: 'Gustav Gelb' })).toBeVisible();
  });

  it('erreicht die Patientenseite in der Tabelle auch per Tastatur über den Namenslink', async () => {
    setViewport(true);
    serve({});
    const user = userEvent.setup();
    renderApp('/clinic');
    await screen.findByTestId('worklist-table');
    within(rowFor('Gerda Grau')).getByRole('link', { name: 'Gerda Grau' }).focus();
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { level: 1, name: 'Gerda Grau' })).toBeVisible();
  });

  it('bietet von der Patientenseite den Rückweg zur Arbeitsliste', async () => {
    serve({});
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByRole('heading', { level: 1, name: 'Rita Rot' })).toBeVisible();
    await user.click(screen.getByRole('link', { name: 'Zur Arbeitsliste' }));
    expect(await screen.findByTestId('worklist-cards')).toBeInTheDocument();
  });
});

describe('Arbeitsliste: Zustände und Rollen', () => {
  it('zeigt den Leerzustand', async () => {
    serve({ worklist: () => jsonResponse([]) });
    renderApp('/clinic');
    expect(await screen.findByText('Noch keine Einträge')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('zeigt Ladezustand, dann bei Fehler „Erneut versuchen“ und lädt neu', async () => {
    let calls = 0;
    serve({
      worklist: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(ERROR_BODY('internal'), 500) : jsonResponse(WORKLIST);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic');
    expect(await screen.findByText('Das hat nicht geklappt')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('worklist-cards')).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('zeigt bei 403 des Servers „Kein Zugriff“', async () => {
    serve({ worklist: () => jsonResponse(ERROR_BODY('forbidden'), 403) });
    renderApp('/clinic');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('lädt für die Patientenrolle weder Arbeitsliste noch Benachrichtigungen', async () => {
    const fetchMock = serve({ me: PATIENT });
    renderApp('/clinic');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => (typeof input === 'string' ? input : ''));
    expect(urls.some((url) => url.includes('/waechter/patients'))).toBe(false);
    expect(urls.some((url) => url.includes('/waechter/notifications'))).toBe(false);
  });
});

describe('Sofortbenachrichtigungen (Banner)', () => {
  it('zeigt nur rote, ungesehene Benachrichtigungen, neueste zuerst, mit Link zur Akte', async () => {
    serve({ notifications: () => jsonResponse(NOTIFICATIONS) });
    renderApp('/clinic');
    const items = await screen.findAllByTestId('notification-item');
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Rote Meldung zu SYN-0001'),
      expect.stringContaining('Rote Meldung zu SYN-0009'),
    ]);
    expect(screen.queryByText('Gelbe Meldung zu SYN-0002')).not.toBeInTheDocument();
    const first = within(items[0] as HTMLElement);
    expect(first.getByText('Sofort prüfen')).toBeInTheDocument();
    expect(first.getByRole('link', { name: 'Zur Patientenakte' })).toHaveAttribute(
      'href',
      '/clinic/patients/pat-1',
    );
    expect(first.getByText(/17\.10\.2026.*08:45/)).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('blendet eine Benachrichtigung nach „Gesehen“ aus und merkt sie lokal', async () => {
    serve({ notifications: () => jsonResponse(NOTIFICATIONS) });
    const user = userEvent.setup();
    const first = renderApp('/clinic');
    const items = await screen.findAllByTestId('notification-item');
    await user.click(within(items[0] as HTMLElement).getByRole('button', { name: 'Gesehen' }));
    expect(screen.getAllByTestId('notification-item')).toHaveLength(1);
    expect(screen.queryByText('Rote Meldung zu SYN-0001')).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(SEEN_STORAGE_KEY) ?? '[]')).toEqual(['n-new']);

    // nach Neuladen bleibt sie ausgeblendet
    first.unmount();
    renderApp('/clinic');
    const again = await screen.findAllByTestId('notification-item');
    expect(again).toHaveLength(1);
    expect(again[0]).toHaveTextContent('Rote Meldung zu SYN-0009');
  });

  it('zeigt keinen Banner, wenn alle roten Benachrichtigungen gesehen sind', async () => {
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify(['n-new', 'n-old']));
    serve({ notifications: () => jsonResponse(NOTIFICATIONS) });
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    expect(screen.queryByTestId('notification-banner')).not.toBeInTheDocument();
  });

  it('funktioniert auch bei blockiertem localStorage (nur im Arbeitsspeicher)', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blockiert');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blockiert');
    });
    serve({ notifications: () => jsonResponse(NOTIFICATIONS) });
    const user = userEvent.setup();
    renderApp('/clinic');
    const items = await screen.findAllByTestId('notification-item');
    expect(items).toHaveLength(2);
    await user.click(within(items[0] as HTMLElement).getByRole('button', { name: 'Gesehen' }));
    expect(screen.getAllByTestId('notification-item')).toHaveLength(1);
  });

  it('fragt alle 30 Sekunden erneut ab und zeigt neue rote Meldungen', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(ANCHOR));
    let calls = 0;
    serve({
      notifications: () => {
        calls += 1;
        return jsonResponse(calls === 1 ? [] : [NOTIFICATIONS[1]]);
      },
    });
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    expect(screen.queryByTestId('notification-banner')).not.toBeInTheDocument();
    expect(calls).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(await screen.findByText('Rote Meldung zu SYN-0001')).toBeVisible();
    expect(calls).toBe(2);
  });

  it('meldet einen Ladefehler sichtbar, lässt die Arbeitsliste stehen und kann wiederholen', async () => {
    let calls = 0;
    serve({
      notifications: () => {
        calls += 1;
        return calls === 1
          ? jsonResponse(ERROR_BODY('internal'), 500)
          : jsonResponse([NOTIFICATIONS[1]]);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Benachrichtigungen konnten nicht geladen werden.');
    expect(await screen.findByTestId('worklist-cards')).toBeInTheDocument();
    await user.click(within(alert).getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByText('Rote Meldung zu SYN-0001')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('erscheint auf der Patientenseite der Klinik eingeklappt (eine Zeile) und lässt sich aufklappen', async () => {
    serve({ notifications: () => jsonResponse(NOTIFICATIONS) });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByTestId('banner-count')).toHaveTextContent(
      'Neue Sofortbenachrichtigungen: 2',
    );
    expect(await screen.findByRole('heading', { level: 1, name: 'Rita Rot' })).toBeVisible();
    expect(screen.queryByTestId('notification-item')).not.toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: 'Anzeigen' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    expect(await screen.findAllByTestId('notification-item')).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Ausblenden' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    await user.click(screen.getByRole('button', { name: 'Ausblenden' }));
    expect(screen.queryByTestId('notification-item')).not.toBeInTheDocument();
  });

  it('zeigt das Banner auf der Arbeitsliste immer ausgeklappt (kein Einklappen-Knopf)', async () => {
    serve({ notifications: () => jsonResponse(NOTIFICATIONS) });
    renderApp('/clinic');
    expect(await screen.findAllByTestId('notification-item')).toHaveLength(2);
    expect(screen.queryByTestId('banner-count')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Anzeigen' })).not.toBeInTheDocument();
  });
});
