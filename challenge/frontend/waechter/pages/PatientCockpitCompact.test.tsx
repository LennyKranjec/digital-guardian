import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { OVERVIEW, TIMELINE } from '../testing/cockpit-fixtures';
import { serve, setViewport, timelineCalls, type ServeOptions } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

async function openCockpit(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  await screen.findByTestId('timeline-body');
  return { fetchMock, user };
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

/** Reihenfolge der Bereiche im DOM (S5: Lage, Meldungen, Kurzfassung, kompakter Verlauf, dann der Rest). */
function position(testId: string): number {
  const all = Array.from(document.querySelectorAll('[data-testid]'));
  const element = screen.getByTestId(testId);
  return all.indexOf(element);
}

describe('Cockpit: Aufbau für den ersten Bildschirm (S5)', () => {
  it('ordnet Kopf, offene Meldungen, Kurzfassung, kompakten Verlauf und erst dann den vollen Verlauf an', async () => {
    await openCockpit();
    const order = [
      'cockpit-header',
      'alerts-section',
      'summary-panel',
      'timeline-compact',
      'timeline-section',
    ].map(position);
    expect(order.every((index) => index >= 0)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('legt Kopf und Meldungen in die linke, die Kurzfassung in die rechte Rasterspalte ab 1200 px', async () => {
    await openCockpit();
    const grid = screen.getByTestId('cockpit-grid');
    expect(grid.className).toContain('min-[1200px]:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]');
    expect(grid.className).not.toMatch(/(^|\s)grid-cols-2/); // darunter einspaltig (375 px)
    const [left, right] = Array.from(grid.children);
    expect(within(left as HTMLElement).getByTestId('cockpit-header')).toBeInTheDocument();
    expect(within(left as HTMLElement).getByTestId('alerts-section')).toBeInTheDocument();
    expect(right).toBe(screen.getByTestId('cockpit-right'));
    // rechts: Kurzfassung, darunter die kompakte Verlaufsleiste (Reihenfolge bleibt auch einspaltig gleich)
    expect(within(right as HTMLElement).getByTestId('summary-panel')).toBeInTheDocument();
    expect(within(right as HTMLElement).getByTestId('timeline-compact')).toBeInTheDocument();
  });

  it('hat genau eine Toolbar-Zeile mit Rückweg und allen Aktionen, der Rückweg steht nicht doppelt', async () => {
    await openCockpit();
    const toolbar = within(screen.getByTestId('cockpit-toolbar'));
    expect(toolbar.getByRole('link', { name: 'Zur Arbeitsliste' })).toHaveAttribute(
      'href',
      '/clinic',
    );
    expect(toolbar.getByTestId('cockpit-actions')).toBeInTheDocument();
    expect(toolbar.getByRole('link', { name: /CTCAE-Aufnahme/ })).toBeInTheDocument();
    expect(toolbar.getByRole('link', { name: /Bericht/ })).toBeInTheDocument();
    // die Aktionsleiste beginnt weiter mit den Aktionen, nicht mit dem Rückweg
    expect(
      within(screen.getByTestId('cockpit-actions')).queryByRole('link', {
        name: 'Zur Arbeitsliste',
      }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Zur Arbeitsliste' })).toHaveLength(1);
  });

  it('zeigt höchstens zwei offene Meldungen sofort, weitere hinter „Weitere Meldungen“', async () => {
    const third = {
      ...OVERVIEW.open_alerts[0],
      alert_id: 'al-3',
      level: 'yellow' as const,
      headline: 'Dritte Meldung',
    };
    await openCockpit({
      overview: () => jsonResponse({ ...OVERVIEW, open_alerts: [...OVERVIEW.open_alerts, third] }),
    });
    const more = screen.getByTestId('more-alerts');
    expect(within(more).getByText('Weitere Meldungen (1)')).toBeInTheDocument();
    expect(within(more).getByText('Dritte Meldung')).toBeInTheDocument();
    expect(more).not.toHaveAttribute('open');
  });

  it('hält Grunderkrankung, Wirkstoffe und absolute Zeiten unter „Mehr Angaben“ bereit', async () => {
    await openCockpit();
    const more = within(screen.getByTestId('header-more'));
    expect(more.getByText('Mehr Angaben')).toBeInTheDocument();
    expect(more.getByText(/Mammakarzinom/)).toBeInTheDocument();
    expect(more.getByText('Wirkstoff X (L01XX01)')).toBeInTheDocument();
  });

  it('zeigt höchstens die ersten zwei Sätze der Kurzfassung sofort, den Rest hinter „Weitere Sätze“', async () => {
    const base = OVERVIEW.summary;
    if (!base) throw new Error('Fixture ohne Kurzfassung');
    const sentences = Array.from({ length: 6 }, (_, index) => ({
      text: `Satz ${index + 1}`,
      refs: [`obs-${index + 1}0${index}`],
      verified: true,
    }));
    await openCockpit({
      overview: () => jsonResponse({ ...OVERVIEW, summary: { ...base, sentences } }),
    });
    const more = screen.getByTestId('summary-more');
    expect(within(more).getByText('Weitere Sätze (4)')).toBeInTheDocument();
    expect(within(more).getAllByTestId('summary-sentence')).toHaveLength(4);
    expect(screen.getAllByTestId('summary-sentence')).toHaveLength(6); // alle bleiben im DOM
    expect(more).not.toHaveAttribute('open');
  });

  it('klappt quittierte, weiter bestehende Meldungen nur ein, solange offene Meldungen Platz brauchen', async () => {
    const acknowledged = { ...OVERVIEW.open_alerts[0], alert_id: 'al-7', status: 'acknowledged' };
    await openCockpit({
      overview: () =>
        jsonResponse({ ...OVERVIEW, persisting: true, persisting_alerts: [acknowledged] }),
    });
    const closed = screen.getByTestId('persisting-alerts');
    expect(closed).not.toHaveAttribute('open');
    expect(within(closed).getByText('Quittierte Meldungen, Wert besteht weiter')).toBeVisible();
    expect(within(closed).getByText('(1)')).toBeInTheDocument();
  });

  it('zeigt quittierte Meldungen sofort, wenn keine offene Meldung mehr da ist (Ampel nicht still grün)', async () => {
    const acknowledged = { ...OVERVIEW.open_alerts[0], alert_id: 'al-7', status: 'acknowledged' };
    await openCockpit({
      overview: () =>
        jsonResponse({
          ...OVERVIEW,
          open_alerts: [],
          persisting: true,
          persisting_alerts: [acknowledged],
        }),
    });
    expect(screen.getByTestId('persisting-alerts')).toHaveAttribute('open');
  });

  it('zeigt Belege kurz (Symbol + Ende der ID), der zugängliche Name nennt die volle ID', async () => {
    await openCockpit();
    const sentence = screen.getAllByTestId('summary-sentence')[0] as HTMLElement;
    const chip = within(sentence).getByRole('button', { name: 'Beleg resp-101 öffnen' });
    expect(chip).toHaveTextContent('101');
    expect(chip).not.toHaveTextContent('resp-101');
    expect(chip).toHaveAttribute('title', 'Beleg resp-101 öffnen');
  });
});

describe('Cockpit: kompakter Verlauf', () => {
  it('zeigt je Symptom mit offener Meldung eine Karte mit Sparkline und letztem Wert', async () => {
    await openCockpit();
    const bar = within(screen.getByTestId('timeline-compact'));
    expect(bar.getByRole('heading', { level: 2, name: 'Verlauf kompakt' })).toBeInTheDocument();
    const cards = bar.getAllByTestId('timeline-compact-card');
    // offene Meldungen: Fieber (rot) und Übelkeit (gelb); Müdigkeit ohne Meldung bleibt weg
    expect(cards.map((card) => card.textContent)).toEqual([
      expect.stringContaining('Übelkeit'),
      expect.stringContaining('Fieber'),
    ]);
    expect(cards.every((card) => card.getAttribute('data-open-alert') === 'true')).toBe(true);
    expect(cards[0]).toHaveTextContent('zuletzt 3 von 4');
    expect(cards[1]).toHaveTextContent('zuletzt 1 von 4');
    expect(bar.getAllByTestId('sparkline')).toHaveLength(2);
    expect(bar.queryByText('Müdigkeit')).not.toBeInTheDocument();
  });

  it('zeichnet die Linie nie über eine Lücke (Fieber hat einen übersprungenen Tag → zwei Linienstücke)', async () => {
    await openCockpit();
    const fever = screen
      .getAllByTestId('timeline-compact-card')
      .find((card) => card.textContent?.includes('Fieber')) as HTMLElement;
    expect(within(fever).getAllByTestId('spark-run')).toHaveLength(2);
    expect(within(fever).getAllByTestId('spark-alert')).toHaveLength(1);
  });

  it('nennt jede Karte als Schaltfläche mit Symptom, letztem Wert und Ziel', async () => {
    await openCockpit();
    expect(
      screen.getByRole('button', {
        name: 'Übelkeit · Schwere: zuletzt 3 von 4 – vollständigen Verlauf öffnen',
      }),
    ).toBeInTheDocument();
  });

  it('springt per Klick zum vollen Verlauf (Fokus auf dessen Überschrift)', async () => {
    const { user } = await openCockpit();
    const scroll = vi.fn();
    const full = document.getElementById('timeline-full') as HTMLElement;
    expect(full).toBe(screen.getByTestId('timeline-section'));
    full.scrollIntoView = scroll;
    await user.click(screen.getAllByTestId('timeline-compact-card')[0] as HTMLElement);
    expect(scroll).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('heading', { level: 2, name: 'Verlauf' })).toHaveFocus();
  });

  it('nutzt dieselbe Abfrage wie der volle Verlauf (kein zusätzlicher Endpunkt, keine zweite Anfrage)', async () => {
    const { fetchMock } = await openCockpit();
    expect(timelineCalls(fetchMock)).toHaveLength(1);
  });

  it('zeigt ohne offene Meldung die ersten drei Kurven', async () => {
    await openCockpit({
      overview: () => jsonResponse({ ...OVERVIEW, open_alerts: [] }),
      timeline: () =>
        jsonResponse({
          ...TIMELINE,
          alerts: TIMELINE.alerts.map((alert) => ({ ...alert, status: 'acknowledged' as const })),
        }),
    });
    const cards = screen.getAllByTestId('timeline-compact-card');
    expect(cards).toHaveLength(3);
    expect(cards.every((card) => card.getAttribute('data-open-alert') === 'false')).toBe(true);
  });

  it('bleibt ohne Verlaufsdaten unsichtbar (der volle Verlauf zeigt den Leerzustand)', async () => {
    serve({
      timeline: () =>
        jsonResponse({
          ...TIMELINE,
          series: [],
          alerts: [],
          visits: [],
          assessments: [],
          missing_days: [],
        }),
    });
    renderApp('/clinic/patients/pat-1');
    await screen.findByText('Noch kein Verlauf');
    expect(screen.queryByTestId('timeline-compact')).not.toBeInTheDocument();
  });
});
