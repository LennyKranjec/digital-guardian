import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { bundleFileName } from '../components/ExportButton';
import { findForbiddenClinician } from '../i18n/forbidden';
import { CONFIG, OVERVIEW, metaBody } from '../testing/cockpit-fixtures';
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
import { PRINT_CSS } from './ReportPage';

function configWith(report: Record<string, unknown>) {
  return jsonResponse({ ...CONFIG, report: { ...CONFIG.report, ...report } });
}

async function openReport(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1/report');
  await screen.findByTestId('report-sheet');
  return { fetchMock, user };
}

const section = (id: string) => within(screen.getByTestId(`report-section-${id}`));

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

describe('Bericht: Aufbau', () => {
  it('hat genau eine h1, Kopf mit Patientin, Zeitraum, Erstellzeit und Konfigurationsversionen', async () => {
    await openReport();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole('heading', { level: 1, name: 'Bericht zum Arztgespräch' }),
    ).toBeVisible();
    const sheet = within(screen.getByTestId('report-sheet'));
    expect(sheet.getByText(/Rita Rot/)).toBeInTheDocument();
    expect(sheet.getByText(/SYN-0001/)).toBeInTheDocument();
    expect(screen.getByTestId('report-period')).toHaveTextContent(
      /10\.10\.2026.*10:00 – 17\.10\.2026.*09:00/,
    );
    expect(screen.getByTestId('report-meta')).toHaveTextContent(/Erstellt: 17\.10\.2026.*09:00/);
    expect(screen.getByTestId('report-meta')).toHaveTextContent(
      'Konfiguration: Regeln rules-v1, Bericht report-v1',
    );
  });

  it('zeigt alle aktivierten Abschnitte in fester Reihenfolge mit der Fußzeile', async () => {
    await openReport();
    const ids = Array.from(document.querySelectorAll('[data-testid^="report-section-"]')).map(
      (node) => node.getAttribute('data-testid')?.replace('report-section-', ''),
    );
    expect(ids).toEqual(
      [
        'therapy',
        'summary',
        'alerts',
        'since_last_visit',
        'timeline',
        'assessments',
        'missing_data',
        'audit',
      ].sort((a, b) => order(a) - order(b)),
    );
    expect(screen.getByTestId('report-footer')).toHaveTextContent(
      'Synthetische Daten · Entscheidungsunterstützung, keine Diagnose',
    );
  });

  it('zeigt nur die in report.sections aktivierten Abschnitte', async () => {
    await openReport({ config: () => configWith({ sections: ['alerts', 'audit'] }) });
    expect(screen.getByTestId('report-section-alerts')).toBeInTheDocument();
    expect(screen.getByTestId('report-section-audit')).toBeInTheDocument();
    for (const hidden of [
      'summary',
      'timeline',
      'since_last_visit',
      'therapy',
      'assessments',
      'missing_data',
    ]) {
      expect(screen.queryByTestId(`report-section-${hidden}`), hidden).not.toBeInTheDocument();
    }
  });

  it('ignoriert unbekannte Abschnittsnamen und sagt es, wenn kein Abschnitt aktiv ist', async () => {
    await openReport({ config: () => configWith({ sections: ['gibt-es-nicht'] }) });
    expect(screen.getByText('Keine Abschnitte')).toBeInTheDocument();
    expect(
      screen.getByText('Für diesen Bericht ist kein Abschnitt aktiviert (siehe Einstellungen).'),
    ).toBeInTheDocument();
    expect(document.querySelector('[data-testid^="report-section-"]')).toBeNull();
  });
});

function order(id: string): number {
  return [
    'summary',
    'alerts',
    'timeline',
    'since_last_visit',
    'therapy',
    'assessments',
    'missing_data',
    'audit',
  ].indexOf(id);
}

describe('Bericht: Inhalte der Abschnitte', () => {
  it('KI-Kurzfassung: Sätze mit Fußnotennummern, Belege als Fußnoten mit Datum, Entwurfshinweis', async () => {
    await openReport();
    const summary = section('summary');
    expect(summary.getByText('KI-Entwurf – Belege prüfen')).toBeInTheDocument();
    expect(
      summary.getByText(
        /Erzeugt von template-v1 \(Textbaustein ohne KI\) am .*08:00; verworfene Sätze: 2/,
      ),
    ).toBeInTheDocument();
    expect(summary.getByText(/Fieber wurde mit dem Wert 1 angegeben\./)).toBeInTheDocument();
    expect(summary.getAllByText('[1]').length).toBeGreaterThan(0);
    const notes = within(await summary.findByTestId('footnotes'));
    // erste Fußnote = resp-101 (Reihenfolge des ersten Auftretens), mit Beschriftung und Datum aus dem Beleg
    expect(
      await notes.findByText(/\[1\] Beleg resp-101 \(.*17\.10\.2026.*06:00\), resp-101/),
    ).toBeInTheDocument();
    expect(notes.getByText(/\[2\] Beleg obs-202/)).toBeInTheDocument();
    expect(summary.getByText(/Belege nicht vollständig geprüft/)).toBeInTheDocument();
    expect(summary.getByText(/Laborwerte/)).toBeInTheDocument();
    // Druckansicht ohne bedienbare Beleg-Chips in der Kurzfassung
    expect(summary.queryByRole('button')).not.toBeInTheDocument();
  });

  it('Fußnote ohne abrufbaren Beleg nennt die Kennung statt zu fehlen', async () => {
    await openReport({
      fact: (factId) =>
        factId === 'resp-101'
          ? jsonResponse(ERROR_BODY('not_found'), 404)
          : jsonResponse({
              fact_id: factId,
              kind: 'observation',
              at: '2026-10-16T08:00:00+02:00',
              label: `Beleg ${factId}`,
              data: {},
            }),
    });
    expect(await screen.findByText('[1] resp-101 (Beleg nicht abrufbar)')).toBeInTheDocument();
  });

  it('Meldungen: Tabelle mit Stufe (Text), Status offen/quittiert und wer/wann/Entscheidung', async () => {
    await openReport();
    const alerts = section('alerts');
    const rows = alerts.getAllByRole('row').slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent(/14\.10\.2026.*Grau.*Keine Eingabe seit 2 Tagen.*quittiert/);
    expect(within(rows[0] as HTMLElement).getByText(/Quittiert von doctor am/)).toBeInTheDocument();
    expect(
      within(rows[0] as HTMLElement).getByText('Entscheidung: Patient:in kontaktieren'),
    ).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent(/Gelb.*Übelkeit stärker als gewohnt.*offen/);
    expect(rows[2]).toHaveTextContent(/Rot.*Fieber gemeldet.*offen/);
  });

  it('Verlauf als Tabelle statt Grafik: Ereignisse ohne Beleg-Chips', async () => {
    await openReport();
    const timeline = section('timeline');
    expect(timeline.getAllByRole('row').length).toBeGreaterThan(8);
    expect(timeline.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('timeline-chart')).not.toBeInTheDocument();
    expect(timeline.getByText(/Fieber \(Vorhandensein\): übersprungen/)).toBeInTheDocument();
  });

  it('Seit dem letzten Termin, Therapie, Aufnahmen und fehlende Daten', async () => {
    await openReport();
    expect(screen.getByTestId('report-section-since_last_visit')).toHaveTextContent(
      'Seit dem letzten Termin',
    );
    const therapy = section('therapy');
    expect(therapy.getByText('Regime A')).toBeInTheDocument();
    expect(therapy.getByText('Wirkstoff X (L01XX01), Wirkstoff Y (L01YY02)')).toBeInTheDocument();
    expect(therapy.getByText('Zyklustag 8')).toBeInTheDocument();
    const assessments = section('assessments');
    expect(assessments.getByText(/Nausea – Grad 1 · möglich/)).toBeInTheDocument();
    expect(assessments.getByText('doctor')).toBeInTheDocument();
    expect(section('missing_data').getByTestId('missing-days')).toHaveTextContent(
      'Tage ohne Eingabe: 14.10.2026',
    );
  });

  it('Audit-Auszug: neueste zuerst, höchstens zehn Zeilen', async () => {
    const many = Array.from({ length: 14 }, (_, index) => ({
      at: `2026-10-17T0${index % 10}:00:00+02:00`,
      actor_role: 'clinician',
      action: `aktion_${index}`,
      target_type: 'patient',
      target_id: 'pat-1',
    }));
    await openReport({ audit: () => jsonResponse(many) });
    const audit = section('audit');
    const rows = await audit.findAllByRole('row');
    expect(rows).toHaveLength(11); // Kopf + 10
    expect(
      within(audit.getAllByRole('row')[1] as HTMLElement).getByText(/aktion_/),
    ).toBeInTheDocument();
  });

  it('Audit-Auszug mit 404 nennt „nicht verfügbar“, der Bericht entsteht trotzdem', async () => {
    await openReport({ audit: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    expect(await screen.findByTestId('audit-unavailable')).toHaveTextContent(
      'Der Audit-Auszug ist nicht verfügbar.',
    );
    expect(screen.getByTestId('report-sheet')).toBeInTheDocument();
  });

  it('enthält keine Diagnose, Therapieempfehlung oder Beruhigung', async () => {
    await openReport();
    await screen.findByTestId('footnotes');
    // Die vorgeschriebene Fußzeile nennt „keine Diagnose“ ausdrücklich und ist ausgenommen.
    const footer = screen.getByTestId('report-footer').textContent ?? '';
    const text = (screen.getByTestId('report-sheet').textContent ?? '').replace(footer, '');
    expect(text.length).toBeGreaterThan(500);
    expect(findForbiddenClinician(text)).toEqual([]);
  });
});

describe('Bericht: Zeitraum', () => {
  it('fragt „seit dem letzten Termin“ ab', async () => {
    const { fetchMock } = await openReport();
    expect(timelineCalls(fetchMock)).toEqual([
      `${BASE}/timeline?from=2026-10-10T08%3A00%3A00.000Z`,
    ]);
  });

  it('rechnet „14 Tage“ gegen die Serverzeit', async () => {
    const { fetchMock } = await openReport({ config: () => configWith({ since: 'days_14' }) });
    expect(timelineCalls(fetchMock)).toEqual([
      `${BASE}/timeline?from=2026-10-03T07%3A00%3A00.000Z`,
    ]);
  });

  it('fällt ohne Serverzeit auf den gesamten Verlauf zurück und weist das aus', async () => {
    const { fetchMock } = await openReport({
      meta: metaBody(false),
      config: () => configWith({ since: 'days_28' }),
    });
    expect(timelineCalls(fetchMock)).toEqual([`${BASE}/timeline`]);
    expect(screen.getByTestId('report-period')).toHaveTextContent('(gesamter Verlauf)');
    expect(screen.getByTestId('report-meta')).not.toHaveTextContent('Erstellt:');
  });

  it('fällt ohne letzten Termin auf den gesamten Verlauf zurück', async () => {
    const { fetchMock } = await openReport({
      overview: () => jsonResponse({ ...OVERVIEW, last_visit_at: null }),
    });
    expect(timelineCalls(fetchMock)).toEqual([`${BASE}/timeline`]);
  });
});

describe('Bericht: Drucken, Export, Zustände', () => {
  it('druckt über window.print und zeigt Druck- und Exportknopf nur am Bildschirm (no-print)', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => undefined);
    const { user } = await openReport();
    const toolbar = within(screen.getByTestId('report-toolbar'));
    expect(screen.getByTestId('report-toolbar')).toHaveClass('no-print');
    await user.click(toolbar.getByRole('button', { name: 'Drucken / als PDF speichern' }));
    expect(print).toHaveBeenCalledTimes(1);
    expect(toolbar.getByRole('button', { name: 'FHIR-Bundle (JSON)' })).toBeInTheDocument();
  });

  it('bringt Druck-CSS für A4 mit, blendet die Plattformhülle beim Drucken aus und wiederholt die Fußzeile', async () => {
    await openReport();
    const style = document.querySelector('.report style');
    expect(style?.textContent).toBe(PRINT_CSS);
    expect(PRINT_CSS).toMatch(/@page\s*\{\s*size:\s*A4/);
    expect(PRINT_CSS).toMatch(/@media print/);
    expect(PRINT_CSS).toMatch(/header,\s*nav[\s\S]*display:\s*none\s*!important/);
    expect(PRINT_CSS).toMatch(/\.no-print/);
    expect(PRINT_CSS).toMatch(/\.report-footer\s*\{\s*position:\s*fixed/);
    // keine Schrift unter 12 pt (= 16 px) im Druck
    for (const match of PRINT_CSS.matchAll(/font-size:\s*(\d+(?:\.\d+)?)(pt|px)/g)) {
      const px = match[2] === 'pt' ? Number(match[1]) * (4 / 3) : Number(match[1]);
      expect(px).toBeGreaterThanOrEqual(16);
    }
  });

  it('zeigt bei 404 den Nicht-gefunden-Zustand und bei Serverfehler „Erneut versuchen“', async () => {
    serve({ overview: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    renderApp('/clinic/patients/pat-1/report');
    expect(await screen.findByText('Seite nicht gefunden')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('lädt bei Fehler neu', async () => {
    let calls = 0;
    serve({
      config: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(ERROR_BODY('internal'), 500) : jsonResponse(CONFIG);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1/report');
    await user.click(await screen.findByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('report-sheet')).toBeInTheDocument();
  });
});

describe('FHIR-Export', () => {
  let downloads: string[];
  let revoke: Mock;

  beforeEach(() => {
    downloads = [];
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:test'),
    });
    revoke = vi.fn();
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
    // Spion wird von vi.restoreAllMocks() im äußeren afterEach zurückgesetzt
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });
  });

  async function openCockpit(options: ServeOptions = {}) {
    const fetchMock = serve(options);
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await screen.findByTestId('cockpit-actions');
    return { fetchMock, user };
  }

  it('lädt das Bundle als <pseudonym>-bundle.json herunter', async () => {
    const { fetchMock, user } = await openCockpit();
    await user.click(screen.getByRole('button', { name: 'FHIR-Bundle (JSON)' }));
    expect(await screen.findByText('Gespeichert als SYN-0001-bundle.json')).toBeInTheDocument();
    expect(downloads).toEqual(['SYN-0001-bundle.json']);
    expect(fetchMock.mock.calls.some(([url]) => callUrl(url) === `${BASE}/fhir`)).toBe(true);
    expect(revoke).toHaveBeenCalledWith('blob:test');
  });

  it('meldet 404 als „Export noch nicht verfügbar“', async () => {
    const { user } = await openCockpit({ fhir: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    await user.click(screen.getByRole('button', { name: 'FHIR-Bundle (JSON)' }));
    expect(await screen.findByText('Export noch nicht verfügbar.')).toBeInTheDocument();
    expect(downloads).toEqual([]);
  });

  it('meldet andere Fehler und Netzfehler als Fehlschlag und lässt es erneut zu', async () => {
    let calls = 0;
    const { user } = await openCockpit({
      fhir: () => {
        calls += 1;
        if (calls === 1) throw new TypeError('Failed to fetch');
        if (calls === 2) return jsonResponse(ERROR_BODY('internal'), 500);
        return new Response('{}', { status: 200 });
      },
    });
    const button = screen.getByRole('button', { name: 'FHIR-Bundle (JSON)' });
    await user.click(button);
    expect(
      await screen.findByText('Der Export hat nicht geklappt. Bitte versuchen Sie es erneut.'),
    ).toBeInTheDocument();
    await user.click(button);
    await vi.waitFor(() => expect(calls).toBe(2));
    await user.click(button);
    expect(await screen.findByText('Gespeichert als SYN-0001-bundle.json')).toBeInTheDocument();
  });

  it('sperrt den Knopf während des Exports', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve();
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (callUrl(input) === `${BASE}/fhir`) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await user.click(await screen.findByRole('button', { name: 'FHIR-Bundle (JSON)' }));
    expect(await screen.findByRole('button', { name: 'Export wird erstellt …' })).toBeDisabled();
    release?.();
    await screen.findByText('Gespeichert als SYN-0001-bundle.json');
  });

  it('macht aus dem Pseudonym einen sicheren Dateinamen', () => {
    expect(bundleFileName('SYN-0001')).toBe('SYN-0001-bundle.json');
    expect(bundleFileName('SYN 0001/../x')).toBe('SYN_0001____x-bundle.json');
    expect(bundleFileName('')).toBe('patient-bundle.json');
  });
});
