import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import {
  ALERT_YELLOW,
  NEW_SUMMARY,
  OVERVIEW,
  OVERVIEW_QUIET,
  factFor,
  metaBody,
} from '../testing/cockpit-fixtures';
import {
  BASE,
  ERROR_BODY,
  callUrl,
  serve,
  setViewport,
  type ServeOptions,
} from '../testing/cockpit-server';
import { ANCHOR, PATIENT } from '../testing/fixtures';

async function openCockpit(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  return { fetchMock, user };
}

function cards() {
  return screen.getAllByTestId('alert-card');
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

describe('Cockpit: Kopfzeile und Lage', () => {
  it('zeigt Name als einzige h1, Pseudonym, „synthetisch“, Alter, Therapie und Wirkstoffe', async () => {
    await openCockpit();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'Rita Rot' })).toBeVisible();
    const header = within(screen.getByTestId('cockpit-header'));
    expect(header.getByText('SYN-0001')).toBeInTheDocument();
    expect(header.getByText('synthetisch')).toBeInTheDocument();
    expect(header.getByText('62 Jahre')).toBeInTheDocument();
    expect(header.getByText(/Mammakarzinom/)).toBeInTheDocument();
    expect(header.getByText('Regime A')).toBeInTheDocument();
    expect(header.getByText('Zyklustag 8')).toBeInTheDocument();
    expect(header.getByText('Wirkstoff X (L01XX01)')).toBeInTheDocument();
    expect(header.getByText('Wirkstoff Y (L01YY02)')).toBeInTheDocument();
  });

  it('zeigt große Ampel mit Icon und Text', async () => {
    await openCockpit();
    const light = screen.getByTestId('cockpit-header').querySelector('[data-traffic-light="red"]');
    expect(light).not.toBeNull();
    expect(light?.textContent).toBe('Sofort prüfen');
    expect(light?.querySelector('svg')).not.toBeNull();
  });

  it('zeigt Termine und letzte Eingabe relativ (gegen server_now) und absolut in Prager Zeit', async () => {
    await openCockpit();
    const header = within(screen.getByTestId('cockpit-header'));
    expect(header.getByText('vor 3 Stunden')).toBeInTheDocument();
    expect(header.getByText(/17\.10\.2026.*06:00/)).toBeInTheDocument();
    expect(header.getByText('vor 7 Tagen')).toBeInTheDocument();
    expect(header.getByText(/10\.10\.2026.*10:00/)).toBeInTheDocument();
    expect(header.getByText('in 3 Tagen')).toBeInTheDocument();
    expect(header.getByText(/20\.10\.2026.*10:00/)).toBeInTheDocument();
  });

  it('zeigt ohne server_now nur absolute Zeiten (kein Rückgriff auf die Browseruhr)', async () => {
    await openCockpit({ meta: metaBody(false) });
    const header = within(screen.getByTestId('cockpit-header'));
    expect(header.getByText(/17\.10\.2026.*06:00/)).toBeInTheDocument();
    expect(header.queryByText(/vor \d+/)).not.toBeInTheDocument();
    expect(header.queryByText(/^in \d+/)).not.toBeInTheDocument();
  });

  it('bietet den Rückweg zur Arbeitsliste', async () => {
    await openCockpit();
    expect(screen.getByRole('link', { name: 'Zur Arbeitsliste' })).toHaveAttribute(
      'href',
      '/clinic',
    );
  });
});

describe('Cockpit: offene Meldungen und „Warum?“', () => {
  it('zeigt rote Meldungen zuerst, auch wenn der Server gelb zuerst liefert', async () => {
    await openCockpit();
    expect(cards().map((card) => card.getAttribute('data-level'))).toEqual(['red', 'yellow']);
    expect(within(cards()[0] as HTMLElement).getByText('Fieber gemeldet')).toBeInTheDocument();
    expect(within(cards()[0] as HTMLElement).getByText('Sofort prüfen')).toBeInTheDocument();
    expect(within(cards()[1] as HTMLElement).getByText('Prüfen')).toBeInTheDocument();
    expect(within(cards()[1] as HTMLElement).getByText(/16\.10\.2026.*09:00/)).toBeInTheDocument();
  });

  it('klappt die Erklärung erst auf Klick auf und wieder zu', async () => {
    const { user } = await openCockpit();
    const red = within(cards()[0] as HTMLElement);
    const why = red.getByRole('button', { name: 'Warum?' });
    expect(why).toHaveAttribute('aria-expanded', 'false');
    expect(red.queryByTestId('explanation')).not.toBeInTheDocument();

    await user.click(why);
    expect(why).toHaveAttribute('aria-expanded', 'true');
    const explanation = within(red.getByTestId('explanation'));
    expect(explanation.getByText('Schwelle')).toBeInTheDocument();
    expect(explanation.getByText(/Regel: R-URG-01/)).toBeInTheDocument();
    expect(explanation.getByText(/Version: rules-v1/)).toBeInTheDocument();
    expect(explanation.getByText('Mindestwert (Wert ≥)')).toBeInTheDocument();
    expect(explanation.getByText('Aktueller Wert')).toBeInTheDocument();
    expect(explanation.getByText('Zyklustag')).toBeInTheDocument();
    expect(
      explanation.getByText('Fieber wurde mit 1 angegeben; Schwelle: Wert ≥ 1.'),
    ).toBeInTheDocument();

    await user.click(why);
    expect(red.queryByTestId('explanation')).not.toBeInTheDocument();
  });

  it('zeigt bei Baseline-Abweichung Parameter, Baseline, Zeitraum und nicht verfügbare Werte', async () => {
    const { user } = await openCockpit();
    const yellow = within(cards()[1] as HTMLElement);
    await user.click(yellow.getByRole('button', { name: 'Warum?' }));
    const explanation = within(yellow.getByTestId('explanation'));
    expect(explanation.getByText('Abweichung von der Baseline')).toBeInTheDocument();
    expect(explanation.getByText('Baseline-Fenster (Tage)')).toBeInTheDocument();
    expect(explanation.getByText('Baseline (Median)')).toBeInTheDocument();
    expect(explanation.getByText('Baseline-Zeitraum')).toBeInTheDocument();
    expect(explanation.getByText(/09\.10\.2026.*09:00 – 16\.10\.2026.*09:00/)).toBeInTheDocument();
    // observed.slope_per_day = null ⇒ „nicht verfügbar“, nie 0
    expect(explanation.getByText('Steigung pro Tag').nextElementSibling).toHaveTextContent(
      'nicht verfügbar',
    );
  });

  it('zeigt unbekannte Parameternamen mit ihrem Schlüssel statt sie zu verbergen', async () => {
    const overview = {
      ...OVERVIEW,
      open_alerts: [
        {
          ...OVERVIEW.open_alerts[1]!,
          explanation: {
            ...OVERVIEW.open_alerts[1]!.explanation,
            params: { neuer_parameter: 4.5 },
            observed: {},
          },
        },
      ],
    };
    const { user } = await openCockpit({ overview: () => jsonResponse(overview) });
    await user.click(screen.getByRole('button', { name: 'Warum?' }));
    expect(screen.getByText('neuer_parameter')).toBeInTheDocument();
    expect(screen.getByText('4,5')).toBeInTheDocument();
  });

  it('zeigt quittierte, weiter bestehende Meldungen getrennt mit Hinweis (Vertrag v1.3)', async () => {
    const acknowledged = { ...ALERT_YELLOW, alert_id: 'al-7', status: 'acknowledged' as const };
    await openCockpit({
      overview: () =>
        jsonResponse({ ...OVERVIEW, persisting: true, persisting_alerts: [acknowledged] }),
    });
    // offene Karten tragen den Hinweis nicht
    for (const card of cards().slice(0, 2)) {
      expect(within(card).queryByText('Quittiert, Wert besteht weiter')).not.toBeInTheDocument();
    }
    const section = within(screen.getByTestId('persisting-alerts'));
    expect(section.getByText('Quittierte Meldungen, Wert besteht weiter')).toBeInTheDocument();
    expect(section.getByText('Übelkeit stärker als gewohnt')).toBeInTheDocument();
    expect(section.getByText('Quittiert, Wert besteht weiter')).toBeInTheDocument();
    // kein zusätzlicher Hinweis auf Abschnittsebene, wenn die Liste vorhanden ist
    expect(screen.getAllByText('Quittiert, Wert besteht weiter')).toHaveLength(1);
  });

  it('zeigt einen Hinweis, wenn persisting gesetzt ist, aber keine Meldungsliste mitkommt', async () => {
    await openCockpit({ overview: () => jsonResponse({ ...OVERVIEW, persisting: true }) });
    expect(
      within(screen.getByTestId('alerts-section')).getByText('Quittiert, Wert besteht weiter'),
    ).toBeInTheDocument();
  });

  it('zeigt „Auswertung ausstehend“, wenn Antworten noch nicht ausgewertet sind', async () => {
    await openCockpit({
      overview: () => jsonResponse({ ...OVERVIEW, evaluation_pending: true }),
    });
    expect(screen.getByTestId('evaluation-pending')).toHaveTextContent(
      'Auswertung ausstehend: nicht alle Antworten sind ausgewertet.',
    );
  });

  it('zeigt die Tage ohne Eingabe (Prager Kalendertage) bei der letzten Eingabe', async () => {
    await openCockpit({
      overview: () => jsonResponse({ ...OVERVIEW, days_without_response: 3 }),
    });
    expect(screen.getByTestId('days-without-response')).toHaveTextContent('Tage ohne Eingabe: 3');
  });

  it('sagt „Keine offene Meldung.“, wenn keine Meldung offen ist', async () => {
    await openCockpit({ overview: () => jsonResponse(OVERVIEW_QUIET) });
    expect(screen.queryByTestId('alert-card')).not.toBeInTheDocument();
    expect(screen.getByText('Keine offene Meldung.')).toBeInTheDocument();
  });
});

describe('Cockpit: Beleg-Schublade', () => {
  it('führt in höchstens 2 Klicks (Warum? → Beleg-Chip) zum Beleg mit Datum, Angaben und Quelle', async () => {
    const { fetchMock, user } = await openCockpit();
    const red = within(cards()[0] as HTMLElement);
    await user.click(red.getByRole('button', { name: 'Warum?' })); // Klick 1
    await user.click(red.getByRole('button', { name: 'Beleg resp-101 öffnen' })); // Klick 2

    const dialog = await screen.findByRole('dialog', { name: /Beleg: resp-101/ });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    const content = within(await within(dialog).findByTestId('fact-content'));
    expect(content.getByText('Beleg resp-101')).toBeInTheDocument();
    expect(content.getByText(/17\.10\.2026.*06:00/)).toBeInTheDocument();
    expect(content.getByText('Antwort der Patient:in (resp-101)')).toBeInTheDocument();
    expect(content.getByText('Wert')).toBeInTheDocument();
    expect(content.getByText('web')).toBeInTheDocument();
    expect(content.getByText('–')).toBeInTheDocument(); // note: null
    expect(fetchMock.mock.calls.some(([url]) => callUrl(url) === `${BASE}/facts/resp-101`)).toBe(
      true,
    );
  });

  it('schließt mit Esc und gibt den Fokus an den Chip zurück', async () => {
    const { user } = await openCockpit();
    const red = within(cards()[0] as HTMLElement);
    await user.click(red.getByRole('button', { name: 'Warum?' }));
    const chip = red.getByRole('button', { name: 'Beleg obs-201 öffnen' });
    await user.click(chip);
    await screen.findByRole('dialog');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(chip).toHaveFocus();
  });

  it('schließt mit dem Schließen-Knopf und per Klick auf den Hintergrund', async () => {
    const { user } = await openCockpit();
    await user.click(screen.getByRole('button', { name: 'Beleg resp-101 öffnen' }));
    await user.click(await screen.findByRole('button', { name: 'Schließen' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Beleg resp-101 öffnen' }));
    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('fact-backdrop'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('hält den Fokus in der Schublade (Fokusfalle, Tab und Shift+Tab)', async () => {
    const { user } = await openCockpit();
    await user.click(screen.getByRole('button', { name: 'Beleg resp-101 öffnen' }));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByTestId('fact-content');
    expect(dialog).toHaveFocus();

    await user.tab();
    const close = within(dialog).getByRole('button', { name: 'Schließen' });
    expect(close).toHaveFocus();
    await user.tab();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
  });

  it('springt mit Shift+Tab vom Dialog selbst auf das letzte Element in der Schublade', async () => {
    const { user } = await openCockpit();
    await user.click(screen.getByRole('button', { name: 'Beleg resp-101 öffnen' }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveFocus();
    await user.tab({ shift: true });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it('meldet einen fehlenden Beleg (404) verständlich', async () => {
    const { user } = await openCockpit({
      fact: () => jsonResponse(ERROR_BODY('fact_not_found'), 404),
    });
    await user.click(screen.getByRole('button', { name: 'Beleg resp-101 öffnen' }));
    expect(await screen.findByText('Dieser Beleg existiert nicht (mehr).')).toBeInTheDocument();
  });

  it('zeigt bei Serverfehler „Erneut versuchen“ und lädt den Beleg nach', async () => {
    let calls = 0;
    const { user } = await openCockpit({
      fact: (factId) => {
        calls += 1;
        return calls === 1
          ? jsonResponse(ERROR_BODY('internal'), 500)
          : jsonResponse(factFor(factId));
      },
    });
    await user.click(screen.getByRole('button', { name: 'Beleg resp-101 öffnen' }));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('Das hat nicht geklappt');
    await user.click(within(dialog).getByRole('button', { name: 'Erneut versuchen' }));
    expect(await within(dialog).findByTestId('fact-content')).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});

describe('Cockpit: KI-Kurzfassung', () => {
  it('zeigt Entwurfshinweis, Generator, Modus, Zeit und Zahl verworfener Sätze', async () => {
    await openCockpit();
    const panel = within(screen.getByTestId('summary-panel'));
    expect(panel.getByRole('heading', { level: 2, name: 'KI-Kurzfassung' })).toBeInTheDocument();
    expect(panel.getByText('KI-Entwurf – Belege prüfen')).toBeInTheDocument();
    expect(panel.getByText('template-v1')).toBeInTheDocument();
    expect(panel.getByText('Textbaustein ohne KI')).toBeInTheDocument();
    expect(panel.getByText(/17\.10\.2026.*08:00/)).toBeInTheDocument();
    expect(panel.getByTestId('dropped-sentences')).toHaveTextContent('2');
  });

  it('zeigt jeden Satz mit Beleg-Chips, kennzeichnet ungeprüfte Sätze und unbekannte Themen', async () => {
    await openCockpit();
    const sentences = screen.getAllByTestId('summary-sentence');
    expect(sentences).toHaveLength(3);
    expect(
      within(sentences[0] as HTMLElement).getByRole('button', { name: 'Beleg resp-101 öffnen' }),
    ).toBeInTheDocument();
    expect(within(sentences[1] as HTMLElement).getAllByRole('button')).toHaveLength(2);
    expect(
      within(sentences[0] as HTMLElement).queryByText('Belege nicht vollständig geprüft'),
    ).not.toBeInTheDocument();
    expect(
      within(sentences[2] as HTMLElement).getByText('Belege nicht vollständig geprüft'),
    ).toBeInTheDocument();
    const unknown = within(screen.getByTestId('unknown-topics'));
    expect(unknown.getByText('Unbekannt (keine Daten):')).toBeInTheDocument();
    expect(unknown.getByText('Laborwerte')).toBeInTheDocument();
  });

  it('führt mit einem Klick auf einen Beleg-Chip des Satzes zur Schublade', async () => {
    const { user } = await openCockpit();
    const sentences = screen.getAllByTestId('summary-sentence');
    await user.click(
      within(sentences[1] as HTMLElement).getByRole('button', { name: 'Beleg obs-202 öffnen' }),
    );
    expect(await screen.findByRole('dialog', { name: /Beleg: obs-202/ })).toBeInTheDocument();
  });

  it('bietet ohne Kurzfassung „Kurzfassung erzeugen“ (POST) und zeigt danach das Ergebnis', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve({
      overview: () => jsonResponse({ ...OVERVIEW_QUIET }),
      summaryPost: async () => {
        await gate;
        return jsonResponse(NEW_SUMMARY, 201);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await screen.findByTestId('cockpit-header');
    const panel = within(screen.getByTestId('summary-panel'));
    expect(panel.getByText('Noch keine Kurzfassung vorhanden.')).toBeInTheDocument();
    expect(panel.getByText('KI-Entwurf – Belege prüfen')).toBeInTheDocument();

    await user.click(panel.getByRole('button', { name: 'Kurzfassung erzeugen' }));
    expect(await panel.findByRole('button', { name: 'Wird erzeugt …' })).toBeDisabled();
    release?.();

    expect(await panel.findByText('azure-openai:test')).toBeInTheDocument();
    expect(panel.getByText('live (Sprachmodell)')).toBeInTheDocument();
    expect(panel.getByText('Neue Kurzfassung zu Fieber.')).toBeInTheDocument();
    expect(panel.getByRole('button', { name: 'Neu erzeugen' })).toBeEnabled();

    const post = fetchMock.mock.calls.find(
      ([url, init]) => callUrl(url) === `${BASE}/summary` && init?.method === 'POST',
    );
    expect(post).toBeDefined();
    expect(post?.[1]?.headers).toMatchObject({ 'X-Requested-With': 'fetch' });
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });

  it('meldet einen Fehler beim Erzeugen und lässt den Knopf wieder zu', async () => {
    const { user } = await openCockpit({
      overview: () => jsonResponse(OVERVIEW_QUIET),
      summaryPost: () => jsonResponse(ERROR_BODY('llm_failed'), 500),
    });
    const panel = within(screen.getByTestId('summary-panel'));
    await user.click(panel.getByRole('button', { name: 'Kurzfassung erzeugen' }));
    expect(await panel.findByRole('alert')).toHaveTextContent('konnte nicht erzeugt werden');
    expect(panel.getByRole('button', { name: 'Kurzfassung erzeugen' })).toBeEnabled();
  });
});

describe('Cockpit: Hinweise und Verlauf seit dem letzten Termin', () => {
  it('zeigt Beobachtungshinweise (Text und Quelle) als beschreibende Hinweise', async () => {
    await openCockpit();
    const notes = within(screen.getByTestId('watch-notes'));
    expect(notes.getByText('Fieber im Zyklus beobachten')).toBeInTheDocument();
    expect(notes.getByText(/Übelkeit nach der Gabe/)).toBeInTheDocument();
    expect(notes.queryByText(/SRC-1/)).not.toBeInTheDocument();
    expect(
      notes.getByText('Beschreibende Hinweise aus der Regime-Konfiguration.'),
    ).toBeInTheDocument();
  });

  it('zeigt die Tabelle ab 768 px mit Pfeil und Text für die Richtung', async () => {
    setViewport(true);
    await openCockpit();
    const table = within(await screen.findByTestId('since-table'));
    expect(table.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Symptom',
      'Erster → letzter Wert',
      'Maximum',
      'Verlauf',
      'Meldungen',
      'Fehlende Tage',
    ]);
    const rows = table.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    const nausea = within(rows[0] as HTMLElement);
    expect(nausea.getByText('Übelkeit')).toBeInTheDocument();
    expect(nausea.getByText('1 → 3')).toBeInTheDocument();
    expect(nausea.getByText(/steigt/)).toBeInTheDocument();
    expect(nausea.getByText('↑', { exact: false })).toHaveAttribute('aria-hidden', 'true');
    const fatigue = within(rows[2] as HTMLElement);
    expect(fatigue.getByText('fehlt → fehlt')).toBeInTheDocument();
    expect(fatigue.getByText(/unbekannt/)).toBeInTheDocument();
    expect(fatigue.getByText('3')).toBeInTheDocument();
  });

  it('zeigt schmal Karten statt Tabelle', async () => {
    await openCockpit();
    const list = within(await screen.findByTestId('since-cards'));
    expect(screen.queryByTestId('since-table')).not.toBeInTheDocument();
    expect(list.getAllByRole('listitem')).toHaveLength(3);
    expect(list.getByText(/gleichbleibend/)).toBeInTheDocument();
  });

  it('sagt „Keine Daten seit dem letzten Termin.“ bei leerer Tabelle', async () => {
    await openCockpit({ overview: () => jsonResponse(OVERVIEW_QUIET) });
    expect(screen.getByText('Keine Daten seit dem letzten Termin.')).toBeInTheDocument();
  });
});

describe('Cockpit: Zustände, Rollen und Sprache', () => {
  it('zeigt beim Laden die h1 „Patientenakte“ und einen Ladezustand', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve();
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (callUrl(input).endsWith('/overview')) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByRole('heading', { level: 1, name: 'Patientenakte' })).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    release?.();
    expect(await screen.findByRole('heading', { level: 1, name: 'Rita Rot' })).toBeVisible();
  });

  it('zeigt bei 404 (fremdes oder unbekanntes Objekt) den Nicht-gefunden-Zustand mit Rückweg', async () => {
    serve({ overview: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByText('Seite nicht gefunden')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Zur Arbeitsliste' })).toBeInTheDocument();
    expect(screen.queryByTestId('cockpit-header')).not.toBeInTheDocument();
  });

  it('zeigt bei 403 „Kein Zugriff“', async () => {
    serve({ overview: () => jsonResponse(ERROR_BODY('forbidden'), 403) });
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('zeigt bei Serverfehler „Erneut versuchen“ und lädt neu', async () => {
    let calls = 0;
    serve({
      overview: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(ERROR_BODY('internal'), 500) : jsonResponse(OVERVIEW);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByText('Das hat nicht geklappt')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('cockpit-header')).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('lädt für die Patientenrolle keine Daten der Klinik', async () => {
    const fetchMock = serve({ me: PATIENT });
    renderApp('/clinic/patients/pat-1');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => (typeof input === 'string' ? input : ''));
    expect(urls.some((url) => url.includes('/waechter/patients'))).toBe(false);
  });

  it('enthält in der sichtbaren Oberfläche keine Diagnose, Therapieempfehlung oder Beruhigung', async () => {
    const { user } = await openCockpit();
    for (const why of screen.getAllByRole('button', { name: 'Warum?' })) {
      await user.click(why);
    }
    const main = document.getElementById('main');
    expect(main).not.toBeNull();
    expect(findForbiddenClinician(main?.textContent ?? '')).toEqual([]);
  });
});
