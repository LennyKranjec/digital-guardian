import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { ACKED_RED, ALERT_RED, OVERVIEW, OVERVIEW_QUIET } from '../testing/cockpit-fixtures';
import {
  ERROR_BODY,
  bodyOf,
  callUrl,
  serve,
  setViewport,
  type ServeOptions,
} from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

const ACK_URL = '/api/v1/waechter/alerts/al-1/acknowledge';

/** Übersicht vor und nach dem Quittieren (zustandsbehaftet wie der Server). */
function statefulOverview() {
  const state = { acknowledged: false, overviewCalls: 0 };
  const overview = () => {
    state.overviewCalls += 1;
    if (!state.acknowledged) return jsonResponse(OVERVIEW);
    return jsonResponse({
      ...OVERVIEW,
      traffic_light: 'yellow',
      open_alerts: OVERVIEW.open_alerts.filter((alert) => alert.alert_id !== 'al-1'),
      persisting: true,
      persisting_alerts: [ACKED_RED],
    });
  };
  return { state, overview };
}

async function openCockpit(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  return { fetchMock, user };
}

const redCard = () =>
  within(
    screen
      .getAllByTestId('alert-card')
      .find((card) => card.getAttribute('data-level') === 'red') as HTMLElement,
  );

const ackCalls = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls.filter(([url, init]) => callUrl(url) === ACK_URL && init?.method === 'POST');

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

describe('Quittieren: Dialog', () => {
  it('bietet an jeder offenen Meldung einen Quittieren-Knopf, nicht an quittierten', async () => {
    await openCockpit({
      overview: () =>
        jsonResponse({ ...OVERVIEW, persisting: true, persisting_alerts: [ACKED_RED] }),
    });
    const cards = screen.getAllByTestId('alert-card');
    const open = cards.filter((card) => card.getAttribute('data-status') === 'open');
    const acked = cards.filter((card) => card.getAttribute('data-status') === 'acknowledged');
    expect(open).toHaveLength(2);
    expect(acked).toHaveLength(1);
    for (const card of open) {
      expect(within(card).getByRole('button', { name: 'Quittieren' })).toBeInTheDocument();
    }
    expect(
      within(acked[0] as HTMLElement).queryByRole('button', { name: 'Quittieren' }),
    ).not.toBeInTheDocument();
  });

  it('öffnet den Dialog mit Meldung, vier neutralen Entscheidungen, Notiz und Zähler', async () => {
    const { user } = await openCockpit();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));

    const dialog = await screen.findByRole('dialog', { name: 'Meldung quittieren' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveFocus();
    const view = within(dialog);
    expect(view.getByTestId('ack-alert-headline')).toHaveTextContent('Fieber gemeldet');
    expect(view.getAllByRole('radio').map((radio) => radio.closest('label')?.textContent)).toEqual([
      'Patient:in kontaktieren',
      'Termin vereinbart',
      'Kein Handlungsbedarf',
      'Sonstiges',
    ]);
    expect(view.getByTestId('note-counter')).toHaveTextContent('0 / 500 Zeichen');
    const note = view.getByRole('textbox', { name: 'Notiz (optional)' });
    expect(note).toHaveAttribute('maxlength', '500');
    await user.type(note, 'Rückruf');
    expect(view.getByTestId('note-counter')).toHaveTextContent('7 / 500 Zeichen');
  });

  it('verlangt eine Entscheidung und sendet ohne sie nichts', async () => {
    const { fetchMock, user } = await openCockpit();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));
    expect(dialog.getByRole('alert')).toHaveTextContent('Bitte wählen Sie eine Entscheidung.');
    expect(ackCalls(fetchMock)).toHaveLength(0);
    await user.click(dialog.getByRole('radio', { name: 'Sonstiges' }));
    expect(dialog.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('quittiert (200): sendet Entscheidung und Notiz, schließt, meldet und lädt neu', async () => {
    const { state, overview } = statefulOverview();
    const { fetchMock, user } = await openCockpit({
      overview,
      ack: () => {
        state.acknowledged = true;
        return jsonResponse(ACKED_RED);
      },
    });
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('radio', { name: 'Patient:in kontaktieren' }));
    await user.type(
      dialog.getByRole('textbox', { name: 'Notiz (optional)' }),
      '  Patientin angerufen  ',
    );
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));

    expect(await screen.findByTestId('cockpit-notice')).toHaveTextContent(
      'Meldung quittiert: Fieber gemeldet – Patient:in kontaktieren',
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const [call] = ackCalls(fetchMock);
    expect(call?.[1]?.headers).toMatchObject({ 'X-Requested-With': 'fetch' });
    expect(bodyOf(call?.[1])).toEqual({
      decision: 'contact_patient',
      note: 'Patientin angerufen',
    });
    // Übersicht neu geladen: die Meldung ist nicht mehr offen, sondern quittiert und „besteht weiter“
    const persisting = within(await screen.findByTestId('persisting-alerts'));
    expect(persisting.getByText('Fieber gemeldet')).toBeInTheDocument();
    expect(persisting.getByText('Quittiert von doctor am', { exact: false })).toBeInTheDocument();
    expect(persisting.getByText('Entscheidung: Patient:in kontaktieren')).toBeInTheDocument();
    expect(persisting.getByText('Notiz: Patientin angerufen')).toBeInTheDocument();
    expect(persisting.getByText('Quittiert, Wert besteht weiter')).toBeInTheDocument();
    expect(state.overviewCalls).toBeGreaterThanOrEqual(2);
    expect(
      screen
        .getAllByTestId('alert-card')
        .filter((card) => card.getAttribute('data-status') === 'open'),
    ).toHaveLength(1);
  });

  it('lässt die Notiz weg, wenn sie leer ist', async () => {
    const { fetchMock, user } = await openCockpit();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('radio', { name: 'Kein Handlungsbedarf' }));
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));
    await screen.findByTestId('cockpit-notice');
    expect(bodyOf(ackCalls(fetchMock)[0]?.[1])).toEqual({
      decision: 'no_action_needed',
    });
  });

  it('erklärt 409 (bereits quittiert) und bietet „Neu laden“ statt erneutem Senden', async () => {
    const { state, overview } = statefulOverview();
    const { fetchMock, user } = await openCockpit({
      overview,
      ack: () => jsonResponse(ERROR_BODY('alert_not_open'), 409),
    });
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('radio', { name: 'Termin vereinbart' }));
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));

    expect(await dialog.findByRole('alert')).toHaveTextContent(
      'Diese Meldung wurde bereits von jemand anderem quittiert. Bitte laden Sie die Daten neu.',
    );
    expect(dialog.queryByRole('button', { name: 'Bestätigen' })).not.toBeInTheDocument();
    const callsBefore = state.overviewCalls;
    state.acknowledged = true; // der Server hat die Meldung inzwischen quittiert
    await user.click(dialog.getByRole('button', { name: 'Neu laden' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByTestId('persisting-alerts')).toBeInTheDocument();
    expect(state.overviewCalls).toBeGreaterThan(callsBefore);
    expect(ackCalls(fetchMock)).toHaveLength(1);
  });

  it.each([
    [404, 'not_found', 'Diese Meldung existiert nicht (mehr).'],
    [422, 'validation_error', 'Die Eingabe wurde nicht akzeptiert.'],
    [403, 'forbidden', 'Dafür fehlt die Berechtigung.'],
    [500, 'internal', 'Das Quittieren hat nicht geklappt.'],
  ])(
    'zeigt bei Status %i eine verständliche Meldung und lässt den Dialog offen',
    async (status, code, text) => {
      const { user } = await openCockpit({ ack: () => jsonResponse(ERROR_BODY(code), status) });
      await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
      const dialog = within(await screen.findByRole('dialog'));
      await user.click(dialog.getByRole('radio', { name: 'Sonstiges' }));
      await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));
      expect(await dialog.findByRole('alert')).toHaveTextContent(text);
      expect(dialog.getByRole('radio', { name: 'Sonstiges' })).toBeChecked();
    },
  );

  it('wiederholt nach Netzfehler mit „Erneut versuchen“', async () => {
    let calls = 0;
    const { fetchMock, user } = await openCockpit({
      ack: () => {
        calls += 1;
        if (calls === 1) throw new TypeError('Failed to fetch');
        return jsonResponse(ACKED_RED);
      },
    });
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('radio', { name: 'Sonstiges' }));
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('Keine Verbindung zum Server.');
    await user.click(dialog.getByRole('button', { name: 'Erneut versuchen' }));
    await screen.findByTestId('cockpit-notice');
    expect(ackCalls(fetchMock)).toHaveLength(2);
  });

  it('sperrt den Knopf während des Sendens (kein Doppelversand)', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve();
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (callUrl(input) === ACK_URL) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await screen.findByTestId('cockpit-header');
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('radio', { name: 'Sonstiges' }));
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));
    expect(await dialog.findByRole('button', { name: 'Wird gespeichert …' })).toBeDisabled();
    release?.();
    await screen.findByTestId('cockpit-notice');
    expect(ackCalls(fetchMock)).toHaveLength(1);
  });
});

describe('Quittieren: Tastatur und Fokus', () => {
  it('schließt mit Esc und gibt den Fokus an den Quittieren-Knopf zurück', async () => {
    const { user } = await openCockpit();
    const button = redCard().getByRole('button', { name: 'Quittieren' });
    await user.click(button);
    await screen.findByRole('dialog');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it('schließt mit „Abbrechen“ und per Klick auf den Hintergrund, ohne zu senden', async () => {
    const { fetchMock, user } = await openCockpit();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    await user.click(await screen.findByRole('button', { name: 'Abbrechen' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    await screen.findByRole('dialog');
    await user.click(screen.getByTestId('ack-backdrop'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(ackCalls(fetchMock)).toHaveLength(0);
  });

  it('hält den Fokus im Dialog (Fokusfalle in beide Richtungen)', async () => {
    const { user } = await openCockpit();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = await screen.findByRole('dialog');
    const view = within(dialog);
    expect(dialog).toHaveFocus();

    // Shift+Tab vom Dialog selbst springt auf das letzte Element (Bestätigen)
    await user.tab({ shift: true });
    expect(view.getByRole('button', { name: 'Bestätigen' })).toHaveFocus();
    // Tab vom letzten Element umläuft zum ersten (erste Entscheidung)
    await user.tab();
    expect(view.getAllByRole('radio')[0]).toHaveFocus();
    // Shift+Tab vom ersten Element zurück zum letzten
    await user.tab({ shift: true });
    expect(view.getByRole('button', { name: 'Bestätigen' })).toHaveFocus();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it('bedient die Entscheidungen per Pfeiltasten', async () => {
    const { user } = await openCockpit();
    await user.click(redCard().getByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    dialog.getAllByRole('radio')[0]?.focus();
    await user.keyboard('{ArrowDown}');
    expect(dialog.getByRole('radio', { name: 'Termin vereinbart' })).toBeChecked();
  });
});

describe('Cockpit-Aktionsleiste', () => {
  it('„Quittieren“ springt zur ersten offenen roten Meldung (Fokus auf deren Knopf)', async () => {
    const { user } = await openCockpit();
    const actions = within(screen.getByTestId('cockpit-actions'));
    await user.click(actions.getByRole('button', { name: 'Quittieren' }));
    expect(document.activeElement?.id).toBe('ack-al-1');
    expect(document.activeElement).toHaveTextContent('Quittieren');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('wählt ohne rote Meldung die erste offene', async () => {
    const yellowOnly = { ...OVERVIEW, open_alerts: [OVERVIEW.open_alerts[0]!] };
    const { user } = await openCockpit({ overview: () => jsonResponse(yellowOnly) });
    await user.click(
      within(screen.getByTestId('cockpit-actions')).getByRole('button', { name: 'Quittieren' }),
    );
    expect(document.activeElement?.id).toBe('ack-al-2');
  });

  it('sperrt „Quittieren“ ohne offene Meldung und erklärt es', async () => {
    await openCockpit({ overview: () => jsonResponse(OVERVIEW_QUIET) });
    const actions = within(screen.getByTestId('cockpit-actions'));
    expect(actions.getByRole('button', { name: 'Quittieren' })).toBeDisabled();
    expect(actions.getByText('Keine offene Meldung zum Quittieren.')).toBeInTheDocument();
  });

  it('verlinkt Aufnahme und Bericht und bietet den FHIR-Export an', async () => {
    await openCockpit();
    const actions = within(screen.getByTestId('cockpit-actions'));
    expect(actions.getByRole('link', { name: 'CTCAE-Aufnahme' })).toHaveAttribute(
      'href',
      '/clinic/patients/pat-1/assess',
    );
    expect(actions.getByRole('link', { name: 'Bericht' })).toHaveAttribute(
      'href',
      '/clinic/patients/pat-1/report',
    );
    expect(actions.getByRole('button', { name: 'FHIR-Bundle (JSON)' })).toBeEnabled();
  });
});

describe('Meldungsdetail /clinic/alerts/:id', () => {
  it('zeigt Meldung mit aufgeklappter Begründung, h1 und Links', async () => {
    serve();
    renderApp('/clinic/alerts/al-1');
    expect(await screen.findByRole('heading', { level: 1, name: 'Fieber gemeldet' })).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(await screen.findByTestId('explanation')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Zur Patientenakte' })).toHaveAttribute(
      'href',
      '/clinic/patients/pat-1',
    );
    expect(screen.getByRole('link', { name: 'Zur Arbeitsliste' })).toHaveAttribute(
      'href',
      '/clinic',
    );
  });

  it('quittiert auf der Detailseite und zeigt danach wer/wann/Entscheidung', async () => {
    let acknowledged = false;
    const fetchMock = serve({
      alert: (id) =>
        jsonResponse(
          acknowledged ? { ...ACKED_RED, alert_id: id } : { ...ALERT_RED, alert_id: id },
        ),
      ack: () => {
        acknowledged = true;
        return jsonResponse(ACKED_RED);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/alerts/al-1');
    await screen.findByRole('heading', { level: 1, name: 'Fieber gemeldet' });
    await user.click(await screen.findByRole('button', { name: 'Quittieren' }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.click(dialog.getByRole('radio', { name: 'Patient:in kontaktieren' }));
    await user.click(dialog.getByRole('button', { name: 'Bestätigen' }));

    expect(await screen.findByTestId('alert-notice')).toHaveTextContent('Meldung quittiert');
    const info = within(await screen.findByTestId('ack-info'));
    expect(info.getByText(/Quittiert von doctor am/)).toBeInTheDocument();
    expect(info.getByText('Entscheidung: Patient:in kontaktieren')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Quittieren' })).not.toBeInTheDocument();
    expect(ackCalls(fetchMock)).toHaveLength(1);
  });

  it('zeigt bei fremder oder unbekannter Meldung (404) den Nicht-gefunden-Zustand', async () => {
    serve({ alert: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    renderApp('/clinic/alerts/al-1');
    expect(await screen.findByText('Seite nicht gefunden')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.queryByTestId('alert-card')).not.toBeInTheDocument();
  });

  it('zeigt bei Serverfehler „Erneut versuchen“', async () => {
    let calls = 0;
    serve({
      alert: (id) => {
        calls += 1;
        return calls === 1
          ? jsonResponse(ERROR_BODY('internal'), 500)
          : jsonResponse({ ...ALERT_RED, alert_id: id });
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/alerts/al-1');
    await user.click(await screen.findByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('alert-card')).toBeInTheDocument();
  });

  it('öffnet Belege der Meldung in der Schublade (Patientin der Meldung)', async () => {
    const fetchMock = serve();
    const user = userEvent.setup();
    renderApp('/clinic/alerts/al-1');
    await user.click(await screen.findByRole('button', { name: 'Beleg resp-101 öffnen' }));
    expect(await screen.findByRole('dialog', { name: /Beleg: resp-101/ })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([url]) => callUrl(url) === '/api/v1/waechter/patients/pat-1/facts/resp-101',
      ),
    ).toBe(true);
  });
});
