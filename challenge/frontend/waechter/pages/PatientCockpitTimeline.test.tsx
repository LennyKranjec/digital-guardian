import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import { OVERVIEW, TIMELINE, metaBody } from '../testing/cockpit-fixtures';
import {
  BASE,
  ERROR_BODY,
  callUrl,
  serve,
  setViewport,
  timelineCalls,
  type ServeOptions,
} from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

async function openTimeline(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  await screen.findByTestId('timeline-body');
  return { fetchMock, user };
}

const charts = () => screen.getAllByTestId('timeline-chart');
const chartFor = (title: string) => {
  const chart = charts().find((entry) => within(entry).queryByRole('heading', { name: title }));
  if (!chart) throw new Error(`Kurve ${title} fehlt`);
  return within(chart);
};
const lane = () => within(screen.getByTestId('timeline-lane'));

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

describe('Verlauf: Aufbau', () => {
  it('zeigt Abschnitt, Legende, Ereigniskurve, je Symptom×Merkmal eine Kurve und die Ereignisliste', async () => {
    await openTimeline();
    const section = within(screen.getByTestId('timeline-section'));
    expect(section.getByRole('heading', { level: 2, name: 'Verlauf' })).toBeInTheDocument();
    expect(charts()).toHaveLength(3);
    expect(screen.getByTestId('timeline-lane')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-legend')).toBeInTheDocument();
    expect(screen.getByTestId('timeline-events')).toBeInTheDocument();
    expect(screen.getAllByTestId('timeline-axis')).toHaveLength(2);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('stellt Symptome mit offener Meldung zuerst (dann Serverreihenfolge)', async () => {
    await openTimeline();
    const titles = charts().map((chart) => within(chart).getByRole('heading').textContent);
    expect(titles).toEqual(['Übelkeit · Schwere', 'Fieber · Vorhandensein', 'Müdigkeit · Schwere']);
  });

  it('beschriftet jede Grafik als Bild (role="img") mit Anzahl der Werte, Lücken und Meldungen', async () => {
    await openTimeline();
    expect(
      chartFor('Fieber · Vorhandensein').getByRole('img', {
        name: 'Verlauf Fieber · Vorhandensein, Skala 0 bis 4. Werte: 4, übersprungen: 1, Meldungen: 1',
      }),
    ).toBeInTheDocument();
    expect(
      chartFor('Übelkeit · Schwere').getByRole('img', {
        name: 'Verlauf Übelkeit · Schwere, Skala 0 bis 4. Werte: 5, übersprungen: 0, Meldungen: 1',
      }),
    ).toBeInTheDocument();
    expect(
      lane().getByRole('img', {
        name: 'Ereignisleiste. Meldungen: 3, Termine: 2, Arztaufnahmen: 1',
      }),
    ).toBeInTheDocument();
  });

  it('zeigt eine Legende mit Text für alle Darstellungsarten', async () => {
    await openTimeline();
    const legend = within(screen.getByTestId('timeline-legend'));
    for (const text of [
      'Linie mit Punkten: Wert von 0 bis 4',
      'Kreuz: übersprungen (Lücke, nicht verbunden)',
      'Schraffur: Tag ohne Eingabe',
      'Raute: Meldung rot',
      'Dreieck: Meldung gelb',
      'Kreis: Meldung grau (Daten fehlen)',
      'Durchgezogene Linie: Termin (vergangen)',
      'Gestrichelte Linie: Termin (geplant)',
      'Gepunktete Linie: Arztaufnahme',
    ]) {
      expect(legend.getByText(text)).toBeInTheDocument();
    }
    expect(
      legend.getByText('Gestrichelte Linie: Schwelle laut Regelkonfiguration rules-v1'),
    ).toBeInTheDocument();
  });
});

describe('Verlauf: Kurven, Lücken, Marker, Schwellen', () => {
  it('verbindet nicht über eine Lücke: zwei getrennte Linienstücke und ein Kreuz', async () => {
    await openTimeline();
    const fever = chartFor('Fieber · Vorhandensein');
    const runs = fever.getAllByTestId('value-run');
    expect(runs).toHaveLength(2);
    expect(
      runs.map((run) => run.querySelector('polyline')?.getAttribute('points')?.split(' ').length),
    ).toEqual([2, 2]);
    expect(fever.getAllByTestId('gap-marker')).toHaveLength(1);
    expect(fever.getAllByTestId('value-point')).toHaveLength(4);
    // Übelkeit ohne Lücke: ein durchgehendes Stück mit 5 Punkten
    const nausea = chartFor('Übelkeit · Schwere');
    expect(nausea.getAllByTestId('value-run')).toHaveLength(1);
    expect(nausea.queryByTestId('gap-marker')).not.toBeInTheDocument();
    expect(
      nausea
        .getAllByTestId('value-run')[0]
        ?.querySelector('polyline')
        ?.getAttribute('points')
        ?.split(' '),
    ).toHaveLength(5);
  });

  it('beschriftet das Linienende direkt mit dem letzten Wert', async () => {
    await openTimeline();
    expect(chartFor('Übelkeit · Schwere').getByTestId('end-label')).toHaveTextContent('3');
    expect(chartFor('Müdigkeit · Schwere').getByTestId('end-label')).toHaveTextContent('2');
  });

  it('schraffiert Tage ohne Eingabe in jeder Grafik', async () => {
    await openTimeline();
    for (const chart of [...charts(), screen.getByTestId('timeline-lane')]) {
      const rects = within(chart).getAllByTestId('missing-day');
      expect(rects.map((rect) => rect.getAttribute('data-date'))).toEqual(['2026-10-14']);
      expect(Number(rects[0]?.getAttribute('width'))).toBeGreaterThan(0);
    }
  });

  it('zeichnet Meldungsmarker in Form je Stufe auf der passenden Kurve', async () => {
    await openTimeline();
    expect(
      chartFor('Fieber · Vorhandensein').getAllByText(
        (_, node) => node?.getAttribute('data-marker') === 'red',
      ),
    ).toHaveLength(1);
    expect(
      chartFor('Übelkeit · Schwere').getAllByText(
        (_, node) => node?.getAttribute('data-marker') === 'yellow',
      ),
    ).toHaveLength(1);
    // Müdigkeit hat keine Meldung
    const fatigue = chartFor('Müdigkeit · Schwere');
    expect(
      fatigue.queryAllByText((_, node) => Boolean(node?.getAttribute('data-marker'))),
    ).toHaveLength(0);
    // rot = Raute (4 Ecken), gelb = Dreieck (3 Ecken)
    const red = screen.getByTestId('timeline-section').querySelector('[data-marker="red"] polygon');
    const yellow = screen
      .getByTestId('timeline-section')
      .querySelector('[data-marker="yellow"] polygon');
    expect(red?.getAttribute('points')?.split(' ')).toHaveLength(4);
    expect(yellow?.getAttribute('points')?.split(' ')).toHaveLength(3);
  });

  it('zeigt in der Ereigniskurve alle Meldungen (auch ohne Kurve), Termine und Aufnahmen', async () => {
    await openTimeline();
    const lanes = screen.getByTestId('timeline-lane');
    const markers = Array.from(lanes.querySelectorAll('[data-marker]')).map((node) =>
      node.getAttribute('data-marker'),
    );
    expect(markers.sort()).toEqual([
      'assessment',
      'grey',
      'red',
      'visit-past',
      'visit-planned',
      'yellow',
    ]);
  });

  it('zeichnet Termine als senkrechte Linien (vergangen durchgezogen, geplant gestrichelt) und Aufnahmen gepunktet', async () => {
    await openTimeline();
    const nausea = screen
      .getByTestId('timeline-section')
      .querySelectorAll('[data-testid="timeline-chart"]')[0];
    const lines = Array.from(nausea?.querySelectorAll('[data-line]') ?? []);
    const byStyle = (style: string) =>
      lines.filter((line) => line.getAttribute('data-line') === style);
    expect(byStyle('visit-past')).toHaveLength(1);
    expect(byStyle('visit-planned')).toHaveLength(1);
    expect(byStyle('assessment')).toHaveLength(1);
    expect(byStyle('visit-past')[0]?.getAttribute('stroke-dasharray')).toBeNull();
    expect(byStyle('visit-planned')[0]?.getAttribute('stroke-dasharray')).toBe('5 4');
    expect(byStyle('assessment')[0]?.getAttribute('stroke-dasharray')).toBe('1 4');
  });

  it('zeichnet die Schwelle aus der Regelkonfiguration gestrichelt und beschriftet', async () => {
    await openTimeline();
    expect(chartFor('Übelkeit · Schwere').getByTestId('threshold')).toHaveTextContent('Schwelle 3');
    expect(chartFor('Fieber · Vorhandensein').getByTestId('threshold')).toHaveTextContent(
      'Schwelle 1',
    );
    // R-SEV-01 gilt für alle Symptome mit Merkmal „Schwere“; die deaktivierte Regel R-OFF-01 (Wert 2) erscheint nie
    const fatigue = chartFor('Müdigkeit · Schwere').getAllByTestId('threshold');
    expect(fatigue).toHaveLength(1);
    expect(fatigue[0]).toHaveTextContent('Schwelle 3');
    expect(screen.queryByText('Schwelle 2')).not.toBeInTheDocument();
    expect(
      chartFor('Übelkeit · Schwere')
        .getByTestId('threshold')
        .querySelector('line')
        ?.getAttribute('stroke-dasharray'),
    ).toBe('7 5');
  });

  it('zeigt den Verlauf auch ohne Regelkonfiguration (ohne Schwellenlinie)', async () => {
    await openTimeline({ config: () => jsonResponse(ERROR_BODY('internal'), 500) });
    expect(screen.queryAllByTestId('threshold')).toHaveLength(0);
    expect(screen.getAllByTestId('timeline-chart')).toHaveLength(3);
    expect(
      within(screen.getByTestId('timeline-legend')).getByText(
        'Gestrichelte Linie: Schwelle laut Regel',
      ),
    ).toBeInTheDocument();
  });
});

describe('Verlauf: Beleg per Klick und Tastatur', () => {
  it('öffnet bei Klick auf einen Messpunkt den Beleg', async () => {
    const { fetchMock, user } = await openTimeline();
    await user.click(
      chartFor('Übelkeit · Schwere').getByRole('button', { name: /Wert 3 am 16\.10\.2026/ }),
    );
    expect(await screen.findByRole('dialog', { name: /Beleg: obs-202/ })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => callUrl(url) === `${BASE}/facts/obs-202`)).toBe(
      true,
    );
  });

  it('öffnet auch eine Lücke (übersprungen) und einen Meldungsmarker', async () => {
    const { user } = await openTimeline();
    await user.click(
      chartFor('Fieber · Vorhandensein').getByRole('button', {
        name: /übersprungen am 14\.10\.2026/,
      }),
    );
    expect(await screen.findByRole('dialog', { name: /Beleg: obs-303/ })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(
      chartFor('Fieber · Vorhandensein').getByRole('button', {
        name: /Meldung Rot: Fieber gemeldet/,
      }),
    );
    expect(await screen.findByRole('dialog', { name: /Beleg: alert-al-1/ })).toBeInTheDocument();
  });

  it('öffnet Termine und Aufnahmen aus der Ereigniskurve', async () => {
    const { user } = await openTimeline();
    await user.click(lane().getByRole('button', { name: /Termin \(geplant\), 20\.10\.2026/ }));
    expect(await screen.findByRole('dialog', { name: /Beleg: visit-2/ })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await user.click(lane().getByRole('button', { name: /Arztaufnahme, 15\.10\.2026/ }));
    expect(await screen.findByRole('dialog', { name: /Beleg: assess-1/ })).toBeInTheDocument();
  });

  it('hat je Grafik einen Tabstopp; Pfeiltasten wechseln den Punkt, Enter öffnet den Beleg', async () => {
    const { user } = await openTimeline();
    const fever = chartFor('Fieber · Vorhandensein');
    const group = fever.getByRole('group', {
      name: 'Messpunkte und Marker Fieber · Vorhandensein',
    });
    const items = within(group).getAllByRole('button');
    expect(items.length).toBeGreaterThanOrEqual(6); // 5 Werte/Lücken + 1 Meldung
    expect(items.filter((item) => item.getAttribute('tabindex') === '0')).toHaveLength(1);
    expect(items.filter((item) => item.getAttribute('tabindex') === '-1')).toHaveLength(
      items.length - 1,
    );

    act(() => items[0]?.focus());
    expect(items[0]).toHaveFocus();
    expect(fever.getByTestId('chart-caption')).toHaveTextContent(
      /Fieber · Vorhandensein: Wert 0 am 12\.10\.2026/,
    );
    await user.keyboard('{ArrowRight}');
    expect(items[1]).toHaveFocus();
    expect(items[1]).toHaveAttribute('tabindex', '0');
    expect(items[0]).toHaveAttribute('tabindex', '-1');
    await user.keyboard('{End}');
    expect(items.at(-1)).toHaveFocus();
    await user.keyboard('{Home}');
    expect(items[0]).toHaveFocus();
    await user.keyboard('{ArrowLeft}');
    expect(items[0]).toHaveFocus(); // am Anfang bleibt der Fokus
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('dialog', { name: /Beleg: obs-301/ })).toBeInTheDocument();
  });

  it('löscht die Bildunterschrift, wenn der Fokus die Grafik verlässt', async () => {
    const { user } = await openTimeline();
    const nausea = chartFor('Übelkeit · Schwere');
    const first = nausea.getAllByRole('button')[0] as HTMLElement;
    act(() => first.focus());
    expect(nausea.getByTestId('chart-caption')).not.toBeEmptyDOMElement();
    await user.tab();
    expect(nausea.getByTestId('chart-caption')).toBeEmptyDOMElement();
  });
});

describe('Verlauf: Zeitraum-Umschalter', () => {
  it('fragt standardmäßig seit dem letzten Termin ab und lädt bei jedem Umschalten neu', async () => {
    const { fetchMock, user } = await openTimeline();
    expect(timelineCalls(fetchMock)).toEqual([
      `${BASE}/timeline?from=2026-10-10T08%3A00%3A00.000Z`,
    ]);
    expect(screen.getByRole('radio', { name: 'Seit letztem Termin' })).toBeChecked();

    await user.click(screen.getByRole('radio', { name: '14 Tage' }));
    await screen.findByTestId('timeline-body');
    expect(timelineCalls(fetchMock).at(-1)).toBe(
      `${BASE}/timeline?from=2026-10-03T07%3A00%3A00.000Z`,
    );

    await user.click(screen.getByRole('radio', { name: '28 Tage' }));
    await screen.findByTestId('timeline-body');
    expect(timelineCalls(fetchMock).at(-1)).toBe(
      `${BASE}/timeline?from=2026-09-19T07%3A00%3A00.000Z`,
    );

    await user.click(screen.getByRole('radio', { name: 'Alles' }));
    await screen.findByTestId('timeline-body');
    expect(timelineCalls(fetchMock).at(-1)).toBe(`${BASE}/timeline`);
    expect(timelineCalls(fetchMock)).toHaveLength(4);
    expect(screen.getByRole('radio', { name: 'Alles' })).toBeChecked();
  });

  it('ersetzt die Darstellung durch die Antwort zum gewählten Zeitraum', async () => {
    const shorter = { ...TIMELINE, series: TIMELINE.series.slice(0, 1), alerts: [] };
    const { user } = await openTimeline({
      timeline: (url) =>
        url.includes('from=2026-10-03') ? jsonResponse(shorter) : jsonResponse(TIMELINE),
    });
    expect(charts()).toHaveLength(3);
    await user.click(screen.getByRole('radio', { name: '14 Tage' }));
    await vi.waitFor(() => expect(screen.getAllByTestId('timeline-chart')).toHaveLength(1));
  });

  it('macht 14 und 28 Tage ohne Serverzeit nicht wählbar (nie Browseruhr)', async () => {
    await openTimeline({ meta: metaBody(false) });
    expect(screen.getByRole('radio', { name: '14 Tage' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: '28 Tage' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: 'Seit letztem Termin' })).toBeEnabled();
    expect(screen.getByRole('radio', { name: 'Alles' })).toBeEnabled();
    expect(screen.getByText('Für 14 und 28 Tage fehlt die Serverzeit.')).toBeInTheDocument();
  });

  it('startet ohne letzten Termin mit „Alles“ und macht „Seit letztem Termin“ nicht wählbar', async () => {
    const { fetchMock } = await openTimeline({
      overview: () => jsonResponse({ ...OVERVIEW, last_visit_at: null }),
    });
    expect(screen.getByRole('radio', { name: 'Seit letztem Termin' })).toBeDisabled();
    expect(screen.getByRole('radio', { name: 'Alles' })).toBeChecked();
    expect(timelineCalls(fetchMock)).toEqual([`${BASE}/timeline`]);
  });

  it('bedient die Optionen per Tastatur (Pfeiltasten und Leertaste)', async () => {
    const { fetchMock, user } = await openTimeline();
    screen.getByRole('radio', { name: 'Seit letztem Termin' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: '14 Tage' })).toBeChecked();
    await screen.findByTestId('timeline-body');
    expect(timelineCalls(fetchMock)).toHaveLength(2);
  });
});

describe('Verlauf: Ereignisliste als Alternative zur Grafik', () => {
  it('listet die Ereignisse zeitlich aufsteigend mit Datum, Ereignis und Details', async () => {
    await openTimeline();
    const list = within(screen.getByTestId('timeline-events'));
    expect(
      list.getByText('Älteste Ereignisse zuerst; dieselben Angaben wie in der Grafik.'),
    ).toBeInTheDocument();
    expect(list.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Datum',
      'Ereignis',
      'Details',
    ]);
    const rows = list.getAllByRole('row').slice(1);
    expect(rows.length).toBeGreaterThan(8);
    expect(rows[0]).toHaveTextContent(/10\.10\.2026.*10:00.*Termin \(vergangen\)/);
    expect(rows.at(-1)).toHaveTextContent(/20\.10\.2026.*Termin \(geplant\)/);
    const kinds = rows.map((row) => row.getAttribute('data-event'));
    expect(kinds.filter((kind) => kind === 'response')).toHaveLength(6);
  });

  it('nennt Werte als Text, auch übersprungene, und gruppiert Antworten eines Zeitpunkts', async () => {
    await openTimeline();
    const list = within(screen.getByTestId('timeline-events'));
    expect(list.getByText(/Fieber \(Vorhandensein\): übersprungen/)).toBeInTheDocument();
    const latest = list.getByText(
      /Müdigkeit \(Schwere\): 2 · Übelkeit \(Schwere\): 3 · Fieber \(Vorhandensein\): 1/,
    );
    expect(latest).toBeInTheDocument();
  });

  it('zeigt Meldungen, Quittierung mit Entscheidung, Arztaufnahme, Termine und fehlenden Tag', async () => {
    await openTimeline();
    const list = within(screen.getByTestId('timeline-events'));
    expect(list.getByText('Meldung (Rot)')).toBeInTheDocument();
    expect(list.getByText('Meldung (Gelb)')).toBeInTheDocument();
    expect(list.getByText('Meldung (Grau)')).toBeInTheDocument();
    const acknowledged = within(list.getByText('Quittiert').closest('tr') as HTMLElement);
    expect(
      acknowledged.getByText(/Patient:in kontaktieren · doctor · Patientin angerufen/),
    ).toBeInTheDocument();
    expect(list.getByText('Nausea – Grad 1')).toBeInTheDocument();
    expect(list.getByText('Termin (geplant)')).toBeInTheDocument();
    const missing = within(list.getByText('Keine Eingabe').closest('tr') as HTMLElement);
    expect(missing.getByText('Ganzer Tag ohne Eingabe')).toBeInTheDocument();
    expect(missing.getByText(/14\.10\.2026/)).toBeInTheDocument();
  });

  it('bietet Beleg-Chips für Termine, Aufnahmen und Meldungen', async () => {
    const { user } = await openTimeline();
    const list = within(screen.getByTestId('timeline-events'));
    await user.click(list.getByRole('button', { name: 'Beleg visit-1 öffnen' }));
    expect(await screen.findByRole('dialog', { name: /Beleg: visit-1/ })).toBeInTheDocument();
  });
});

describe('Verlauf: Zustände, 375 px, Sprache', () => {
  it('zeigt bei Fehler „Erneut versuchen“ im Abschnitt und lädt neu', async () => {
    let calls = 0;
    const { user } = await (async () => {
      const fetchMock = serve({
        timeline: () => {
          calls += 1;
          return calls === 1 ? jsonResponse(ERROR_BODY('internal'), 500) : jsonResponse(TIMELINE);
        },
      });
      const userSession = userEvent.setup();
      renderApp('/clinic/patients/pat-1');
      await screen.findByTestId('cockpit-header');
      return { fetchMock, user: userSession };
    })();
    const section = within(await screen.findByTestId('timeline-section'));
    expect(await section.findByText('Das hat nicht geklappt')).toBeInTheDocument();
    // Cockpit bleibt benutzbar
    expect(screen.getByTestId('cockpit-header')).toBeInTheDocument();
    await user.click(section.getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('timeline-body')).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('zeigt den Leerzustand, wenn der Zeitraum nichts enthält', async () => {
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
    expect(await screen.findByText('Noch kein Verlauf')).toBeInTheDocument();
    expect(screen.queryByTestId('timeline-body')).not.toBeInTheDocument();
  });

  it('zeigt Ladezustand, solange die Antwort aussteht', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve();
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (typeof input === 'string' && input.includes('/timeline')) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    renderApp('/clinic/patients/pat-1');
    const section = within(await screen.findByTestId('timeline-section'));
    expect(await section.findByRole('status')).toBeInTheDocument();
    release?.();
    expect(await screen.findByTestId('timeline-body')).toBeInTheDocument();
  });

  it('zeichnet bei 375 px Breite alle Grafiken und Bedienelemente innerhalb der Breite', async () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 343,
      height: 0,
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 343,
      bottom: 0,
      toJSON: () => ({}),
    });
    await openTimeline();
    for (const svg of screen.getAllByRole('img')) {
      expect(Number(svg.getAttribute('width'))).toBeLessThanOrEqual(343);
    }
    const items = screen.getAllByTestId('chart-item');
    expect(items.length).toBeGreaterThan(10);
    for (const item of items) {
      const left = parseFloat(item.style.left);
      const width = parseFloat(item.style.width);
      expect(left).toBeGreaterThanOrEqual(0);
      expect(left + width).toBeLessThanOrEqual(343);
      expect(width).toBeGreaterThanOrEqual(44);
      expect(parseFloat(item.style.height)).toBeGreaterThanOrEqual(44);
    }
  });

  it('enthält im Verlauf keine Diagnose, Therapieempfehlung oder Beruhigung', async () => {
    await openTimeline();
    const text = screen.getByTestId('timeline-section').textContent ?? '';
    expect(text.length).toBeGreaterThan(200);
    expect(findForbiddenClinician(text)).toEqual([]);
  });
});
