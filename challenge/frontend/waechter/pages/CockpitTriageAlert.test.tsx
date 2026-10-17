import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import { ALERT_RED, OVERVIEW } from '../testing/cockpit-fixtures';
import { BASE, callUrl, serve, setViewport } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';
import { ALERT_TRIAGE, TRIAGE_RED } from '../testing/triage-fixtures';

const overviewWith = (alerts: unknown[]) =>
  jsonResponse({ ...OVERVIEW, open_alerts: alerts, traffic_light: 'red' });

async function openCockpit(options: Parameters<typeof serve>[0] = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  const cards = await screen.findAllByTestId('alert-card');
  return { fetchMock, user, cards };
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

describe('Meldung aus dem kompilierten Baum (explanation.kind triage, v2.8)', () => {
  it('bricht das Cockpit nicht (zod nimmt kind „triage“ an) und zeigt die Meldung', async () => {
    const { cards } = await openCockpit({ overview: () => overviewWith([ALERT_TRIAGE]) });
    expect(cards).toHaveLength(1);
    expect(within(cards[0] as HTMLElement).getByText('Triage: Stufe Rot')).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('zeigt unter „Warum?“ Stufe, Spanne, Begründungen mit Schutzboden zuerst und den Befund-Link', async () => {
    const { user, cards } = await openCockpit({ overview: () => overviewWith([ALERT_TRIAGE]) });
    await user.click(within(cards[0] as HTMLElement).getByRole('button', { name: 'Warum?' }));
    const explanationEl = await screen.findByTestId('explanation');
    const explanation = within(explanationEl);
    expect(explanation.getByText('Triage (kompilierter Baum)')).toBeVisible();
    const triage = within(explanation.getByTestId('explanation-triage'));
    expect(triage.getByText('Stufe Rot')).toBeVisible();
    expect(triage.getByTestId('explanation-triage-span')).toHaveTextContent(
      'Mögliche Spanne: Gelb bis Rot',
    );
    expect(triage.getByText(/Unvollständig/)).toBeVisible();
    const kinds = within(triage.getByTestId('triage-reasons'))
      .getAllByRole('listitem')
      .map((item) => item.getAttribute('data-kind'));
    // Schutzboden (Schloss) zuerst, auch wenn der Server ihn später liefert
    expect(kinds).toEqual(['shield', 'path']);
    expect(triage.getByText('Schutzboden:')).toBeVisible();
    expect(triage.getByTestId('triage-reasons')).toHaveTextContent('Beteiligt: fever');
    expect(findForbiddenClinician(explanationEl.textContent)).toEqual([]);
  });

  it('öffnet den Befund der zugehörigen Antwort erst per Klick und lädt ihn mit response_id', async () => {
    const { fetchMock, user, cards } = await openCockpit({
      overview: () => overviewWith([ALERT_TRIAGE]),
      triage: (responseId) => jsonResponse({ ...TRIAGE_RED, response_id: responseId ?? 'x' }),
    });
    await user.click(within(cards[0] as HTMLElement).getByRole('button', { name: 'Warum?' }));
    const open = await screen.findByText('Triage-Befund öffnen');
    const triageCalls = () =>
      fetchMock.mock.calls.filter(([input]) => callUrl(input).startsWith(`${BASE}/triage`));
    expect(triageCalls()).toHaveLength(0); // nichts vorab
    await user.click(open);
    expect(await screen.findByTestId('triage-finding')).toHaveTextContent(
      'Schutzboden: Fieber ja: Mindeststufe Rot',
    );
    expect(triageCalls()).toHaveLength(1);
    expect(callUrl(triageCalls()[0]?.[0] as RequestInfo)).toBe(`${BASE}/triage?response_id=resp-9`);
  });

  it('vergibt keine doppelten ids, wenn Befund im Cockpit und an der Meldung zugleich offen sind', async () => {
    const { user, cards } = await openCockpit({ overview: () => overviewWith([ALERT_TRIAGE]) });
    await user.click(within(cards[0] as HTMLElement).getByRole('button', { name: 'Warum?' }));
    await user.click(await screen.findByText('Triage-Befund öffnen'));
    // das Cockpit-Panel steht unter dem Raster, die Meldungs-Panels davor
    const panels = screen.getAllByTestId('triage-panel');
    await user.click((panels.at(-1) as HTMLElement).querySelector('summary') as HTMLElement);
    await screen.findAllByTestId('triage-finding');
    const ids = Array.from(document.querySelectorAll('[id]')).map((element) => element.id);
    expect(ids.length).toBeGreaterThan(5);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('zeigt die Triage-Erklärung auch an einer Bestandsmeldung (angehängt, Rauschbremse)', async () => {
    const attached = {
      ...ALERT_RED,
      explanation: { ...ALERT_RED.explanation, triage: ALERT_TRIAGE.explanation.triage },
    };
    const { user, cards } = await openCockpit({ overview: () => overviewWith([attached]) });
    await user.click(within(cards[0] as HTMLElement).getByRole('button', { name: 'Warum?' }));
    const explanation = within(await screen.findByTestId('explanation'));
    expect(explanation.getByText('Schwelle')).toBeVisible(); // Bestandsregel bleibt führend
    expect(explanation.getByTestId('explanation-triage')).toBeVisible();
  });

  it('kommt auch ohne explanation.triage aus (nullish) und zeigt dann keinen Triage-Block', async () => {
    const bare = {
      ...ALERT_TRIAGE,
      explanation: { ...ALERT_TRIAGE.explanation, triage: undefined },
    };
    const { user, cards } = await openCockpit({ overview: () => overviewWith([bare]) });
    await user.click(within(cards[0] as HTMLElement).getByRole('button', { name: 'Warum?' }));
    const explanation = within(await screen.findByTestId('explanation'));
    expect(explanation.getByText('Triage (kompilierter Baum)')).toBeVisible();
    expect(explanation.queryByTestId('explanation-triage')).toBeNull();
  });

  it('zeigt die Meldung auf der Detailseite (von Anfang an aufgeklappt) und übersetzt (en)', async () => {
    await i18n.changeLanguage('en');
    serve({ alert: () => jsonResponse(ALERT_TRIAGE) });
    renderApp('/clinic/alerts/al-tri');
    const explanation = within(await screen.findByTestId('explanation'));
    expect(explanation.getByText('Triage (compiled tree)')).toBeVisible();
    expect(explanation.getByText('Open triage finding')).toBeVisible();
    expect(explanation.getByText('Level red')).toBeVisible();
    expect(document.body.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
  });

  it('bricht die Arbeitsliste bei einer Triage-Meldung nicht (top_alert mit R-TRI-RED)', async () => {
    serve({
      worklist: () =>
        jsonResponse([
          {
            patient_id: 'pat-1',
            pseudonym: 'SYN-0001',
            display_name: 'Rita Rot',
            regimen_id: 'regimen-a',
            traffic_light: 'red',
            open_alerts: 1,
            top_alert: {
              alert_id: 'al-tri',
              rule_id: 'R-TRI-RED',
              level: 'red',
              headline: 'Triage: Stufe Rot',
              created_at: '2026-10-17T08:30:00+02:00',
            },
            synthetic: true,
          },
        ]),
    });
    renderApp('/clinic');
    expect(await screen.findByText('Triage: Stufe Rot')).toBeVisible();
  });
});
