import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import {
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import type { SessionStep, SubmitReceipt } from '../api/client';
import { findForbidden } from '../i18n/forbidden';
import { SESSION_META_KEY, SESSION_STORAGE_KEY } from '../model/session';
import { metaBody } from '../testing/cockpit-fixtures';
import { PATIENT, QUESTIONNAIRE } from '../testing/fixtures';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ERROR_BODY = (code: string) => ({ code, message: code, field_errors: [] });

const OPTIONS = [
  { value: 0, label: 'Nie' },
  { value: 1, label: 'Selten' },
  { value: 2, label: 'Gelegentlich' },
  { value: 3, label: 'Häufig' },
];

const NAUSEA = {
  symptom_key: 'nausea',
  attribute: 'frequency' as const,
  label: 'Übelkeit',
  text: 'Wie oft war Ihnen übel?',
  options: OPTIONS,
  kind: 'gate' as const,
  safety: false,
};
const FEVER = {
  symptom_key: 'fever',
  attribute: 'presence' as const,
  label: 'Fieber',
  text: 'Hatten Sie Fieber?',
  options: [
    { value: 0, label: 'Nein' },
    { value: 1, label: 'Ja' },
  ],
  kind: 'gate' as const,
  safety: true,
};

const STEP_1: SessionStep = {
  session_id: 'sess-1',
  next: NAUSEA,
  progress: { asked: 0, max: 6 },
  stop: null,
  receipt: null,
  selection_reason: 'Fragen passend zu Ihrer Behandlung (FOLFOX) und Ihrer Diagnose.',
  due: { next_due_at: '2026-10-18T09:00:00+02:00', overdue: false, interval_days: 3 },
};
const STEP_2: SessionStep = { ...STEP_1, next: FEVER, progress: { asked: 1, max: 6 } };

function receipt(extra: Partial<SubmitReceipt> = {}): SubmitReceipt {
  return {
    response_id: 'resp-1',
    recorded_at: '2026-10-17T09:00:00+02:00',
    answered: 2,
    skipped: 0,
    message_key: 'patient.response.saved',
    advice: [],
    escalation: { level: 'general', text: 'Bei Beschwerden wenden Sie sich an die Ambulanz.' },
    ...extra,
  };
}

const ACUTE_RECEIPT = receipt({
  escalation: {
    level: 'acute',
    text: 'Bei akuten Beschwerden kontaktieren Sie die Ambulanz oder rufen Sie 155 an.',
    ambulance_phone: '[Telefon der Ambulanz]',
  },
  advice: [
    {
      rule_id: 'ADV-NAUSEA-01',
      symptom_key: 'nausea',
      label: 'Übelkeit',
      tips: ['Trinken Sie in kleinen Schlucken.', 'Essen Sie mehrere kleine Mahlzeiten.'],
      sources: [
        { id: 'spc-1', title: 'SPC (SÚKL)', url: 'https://www.sukl.cz/spc' },
        { id: 'x', title: 'Ohne Link', url: 'javascript:alert(1)' },
      ],
    },
  ],
});

const STOP_STEP = (r: SubmitReceipt): SessionStep => ({
  session_id: 'sess-1',
  next: null,
  progress: { asked: 2, max: 6 },
  stop: { reason: 'decided', incomplete: false },
  receipt: r,
  selection_reason: STEP_1.selection_reason,
  due: { next_due_at: '2026-10-20T09:00:00+02:00', overdue: false, interval_days: 3 },
});

type Handler = (body: Record<string, unknown>, attempt: number) => Response;

interface Mocks {
  start?: Handler;
  answer?: Handler;
  /** `POST /me/sessions/{id}/undo` (T-31); Standard: Rücksprung auf STEP_1 */
  undo?: Handler;
  /** `GET /me/sessions/{id}` (v2.5); Standard: 404 */
  session?: (id: string) => Response;
  /** `GET /meta` mit server_now (DR-009); verzögert/fehlend zum Testen der Fälligkeit; Standard: ohne server_now */
  meta?: () => Response | Promise<Response>;
}

/** Gemockter Server nach openapi v2.0: Sitzung starten/fortsetzen und je Karte eine Antwort. */
function serve(mocks: Mocks = {}, me: unknown = PATIENT) {
  const counts = { start: 0, answer: 0, get: 0, undo: 0 };
  return {
    counts,
    fetch: mockFetch((url, init) => {
      if (url.endsWith('/auth/me')) return jsonResponse(me);
      const body =
        typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : {};
      if (url.endsWith('/waechter/me/sessions') && init?.method === 'POST') {
        counts.start += 1;
        return (mocks.start ?? (() => jsonResponse(STEP_1, 201)))(body, counts.start);
      }
      if (/\/waechter\/me\/sessions\/[^/]+\/answers$/.test(url) && init?.method === 'POST') {
        counts.answer += 1;
        return (mocks.answer ?? (() => jsonResponse(STEP_2)))(body, counts.answer);
      }
      if (/\/waechter\/me\/sessions\/[^/]+\/undo$/.test(url) && init?.method === 'POST') {
        counts.undo += 1;
        return (mocks.undo ?? (() => jsonResponse(STEP_1)))(body, counts.undo);
      }
      const getMatch = /\/waechter\/me\/sessions\/([^/]+)$/.exec(url);
      if (getMatch && init?.method !== 'POST') {
        counts.get += 1;
        return (
          mocks.session?.(decodeURIComponent(getMatch[1] ?? '')) ??
          jsonResponse(ERROR_BODY('not_found'), 404)
        );
      }
      if (url.includes('/waechter/me/questionnaire')) return jsonResponse(QUESTIONNAIRE);
      if (url.endsWith('/meta') && mocks.meta) return mocks.meta();
      return defaultApiResponse(url);
    }),
  };
}

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
}

function callsTo(fetchMock: ReturnType<typeof serve>['fetch'], suffix: RegExp) {
  return fetchMock.mock.calls
    .filter(([url, init]) => suffix.test(urlOf(url)) && init?.method === 'POST')
    .map(([url, init]) => ({
      url: urlOf(url),
      body: JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as Record<
        string,
        unknown
      >,
    }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  register(pluginApi);
});

afterEach(async () => {
  vi.unstubAllGlobals();
  resetRegistry();
  window.sessionStorage.clear();
  await i18n.changeLanguage('de');
});

describe('Adaptiver Check-in: Start und Fortsetzung', () => {
  it('startet eine Sitzung mit UUID und Sprache und zeigt Karte, Auswahlgrund, Fälligkeit und Fortschritt', async () => {
    const { fetch } = serve();
    renderApp('/patient');

    const card = await screen.findByTestId('session-card');
    expect(within(card).getByRole('heading', { level: 2, name: 'Übelkeit' })).toBeVisible();
    expect(within(card).getByRole('radiogroup', { name: NAUSEA.text })).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByTestId('selection-reason')).toHaveTextContent('FOLFOX');
    expect(screen.getByTestId('session-due')).toHaveTextContent(/Nächster Check-in/);
    // Fortschritt: sichtbar nur „x / y“, gesprochen „Frage x (höchstens y)“; kein Prozentwert
    const progress = screen.getByTestId('session-progress');
    expect(progress).toHaveTextContent('0 / 6');
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-valuetext',
      'Frage 1 (höchstens 6)',
    );
    expect(progress.textContent).not.toMatch(/%/);

    const [start] = callsTo(fetch, /\/waechter\/me\/sessions$/);
    expect(start?.body.client_session_id).toMatch(UUID);
    expect(start?.body.lang).toBe('de');
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBe(start?.body.client_session_id);
  });

  it('zeigt unter der Karte den NCI-Markenhinweis und den Prototyp-Hinweis', async () => {
    serve();
    renderApp('/patient');
    const notice = await screen.findByTestId('pro-ctcae-notice');
    expect(notice).toHaveTextContent('nach der Struktur von PRO-CTCAE®');
    expect(notice).toHaveTextContent('Forschungsprototyp');
  });

  it('setzt nach Neuladen mit derselben client_session_id fort', async () => {
    const { fetch } = serve();
    const first = renderApp('/patient');
    await screen.findByTestId('session-card');
    first.unmount();
    renderApp('/patient');
    await screen.findByTestId('session-card');

    const ids = callsTo(fetch, /\/waechter\/me\/sessions$/).map((c) => c.body.client_session_id);
    expect(ids.length).toBeGreaterThanOrEqual(2);
    expect(new Set(ids).size).toBe(1);
  });

  it('funktioniert auch ohne nutzbaren sessionStorage (try/catch)', async () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('gesperrt');
    });
    const setSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('gesperrt');
    });
    try {
      serve();
      renderApp('/patient');
      expect(await screen.findByTestId('session-card')).toBeVisible();
    } finally {
      spy.mockRestore();
      setSpy.mockRestore();
    }
  });
});

describe('Adaptiver Check-in: Karte → Antwort → nächste Karte', () => {
  it('sendet genau die gewählte Antwort und zeigt die Folgefrage des Servers', async () => {
    const user = userEvent.setup();
    const { fetch } = serve();
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');

    const next = within(card).getByRole('button', { name: 'Weiter' });
    expect(next).toBeDisabled(); // ohne Wahl nichts zu senden
    await user.click(within(card).getByRole('radio', { name: 'Gelegentlich' }));
    expect(next).toBeEnabled();
    expect(callsTo(fetch, /\/answers$/)).toHaveLength(0); // Auswahl allein sendet nichts
    await user.click(next);

    expect(await screen.findByRole('radiogroup', { name: FEVER.text })).toBeVisible();
    const [answer] = callsTo(fetch, /\/answers$/);
    expect(answer?.url).toContain('/waechter/me/sessions/sess-1/answers');
    expect(answer?.body).toEqual({ symptom_key: 'nausea', attribute: 'frequency', value: 2 });
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-valuetext',
      'Frage 2 (höchstens 6)',
    );
    // neue Karte: keine Vorauswahl
    for (const radio of within(screen.getByTestId('session-card')).getAllByRole('radio')) {
      expect(radio).not.toBeChecked();
    }
    // Fokus auf der neuen Karte (Screenreader/Tastatur)
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 2, name: 'Fieber' })).toHaveFocus(),
    );
  });

  it('sendet beim Überspringen null', async () => {
    const user = userEvent.setup();
    const { fetch } = serve();
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Überspringen' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    await screen.findByRole('radiogroup', { name: FEVER.text });
    expect(callsTo(fetch, /\/answers$/)[0]?.body).toEqual({
      symptom_key: 'nausea',
      attribute: 'frequency',
      value: null,
    });
  });

  it('bedient die Kacheln als Radiogruppe per Tastatur (Pfeiltaste wählt, Leertaste/Enter sendet nichts allein)', async () => {
    const user = userEvent.setup();
    const { fetch } = serve();
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    const radios = within(card).getAllByRole('radio');
    expect(new Set(radios.map((radio) => radio.getAttribute('name'))).size).toBe(1);
    radios[0]?.focus();
    await user.keyboard('{ArrowDown}');
    expect(radios.some((radio) => (radio as HTMLInputElement).checked)).toBe(true);
    expect(callsTo(fetch, /\/answers$/)).toHaveLength(0);
    await user.tab();
    await user.tab(); // von der Gruppe zu „Weiter“
  });

  it('lädt bei 409 not_current_question die Sitzung mit derselben Kennung neu', async () => {
    const user = userEvent.setup();
    const { fetch, counts } = serve({
      answer: () => jsonResponse(ERROR_BODY('not_current_question'), 409),
      start: (_body, attempt) =>
        jsonResponse(attempt === 1 ? STEP_1 : STEP_2, attempt === 1 ? 201 : 200),
    });
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Selten' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));

    // die Karte, die der Server tatsächlich erwartet (Fieber), ersetzt die veraltete
    expect(await screen.findByRole('radiogroup', { name: FEVER.text })).toBeVisible();
    expect(counts.start).toBe(2);
    const ids = callsTo(fetch, /\/waechter\/me\/sessions$/).map((c) => c.body.client_session_id);
    expect(ids[0]).toBe(ids[1]);
  });

  it('holt bei 409 session_closed zuerst den Beleg (GET) und startet nie still eine neue Sitzung (v2.5)', async () => {
    const user = userEvent.setup();
    const { fetch, counts } = serve({
      answer: () => jsonResponse(ERROR_BODY('session_closed'), 409),
      session: (id) =>
        id === 'sess-1'
          ? jsonResponse(STOP_STEP(ACUTE_RECEIPT))
          : jsonResponse(ERROR_BODY('nf'), 404),
    });
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Nie' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    const confirmation = await screen.findByTestId('checkin-confirmation');
    expect(within(confirmation).getByTestId('escalation-acute')).toBeVisible();
    expect(counts.get).toBe(1);
    expect(callsTo(fetch, /\/waechter\/me\/sessions$/)).toHaveLength(1); // keine zweite Sitzung
  });

  it('behält bei einem Netzfehler die Auswahl, zeigt den Fehler in der Karte und sendet beim zweiten Versuch', async () => {
    const user = userEvent.setup();
    let failed = false;
    const { counts } = serve({
      answer: () => {
        if (!failed) {
          failed = true;
          throw new TypeError('offline');
        }
        return jsonResponse(STEP_2);
      },
    });
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Häufig' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));

    expect(await within(card).findByRole('alert')).toBeVisible();
    expect(within(card).getByRole('radio', { name: 'Häufig' })).toBeChecked();
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    expect(await screen.findByRole('radiogroup', { name: FEVER.text })).toBeVisible();
    expect(counts.answer).toBe(2);
  });
});

describe('Adaptiver Check-in: Stopp und Abschluss', () => {
  async function finish(r: SubmitReceipt) {
    const user = userEvent.setup();
    serve({ answer: () => jsonResponse(STOP_STEP(r)) });
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Gelegentlich' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    return screen.findByTestId('checkin-confirmation');
  }

  it('zeigt zuerst den Akut-Hinweis, dann die Tipps mit Quelle, zuletzt die neutrale Bestätigung – ohne Platzhalter', async () => {
    const confirmation = await finish(ACUTE_RECEIPT);

    const acute = within(confirmation).getByTestId('escalation-acute');
    const advice = within(confirmation).getByTestId('advice');
    const saved = within(confirmation).getByRole('heading', { name: 'Gespeichert' });
    // Reihenfolge im Dokument: Hinweis → Tipps → Bestätigung
    expect(acute.compareDocumentPosition(advice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(advice.compareDocumentPosition(saved) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(acute).toHaveTextContent('rufen Sie 155 an');

    // Platzhalter in eckigen Klammern nie sichtbar, kein tel:-Link ohne echte Nummer
    expect(confirmation.textContent).not.toMatch(/\[[^\]]*\]/);
    expect(within(confirmation).queryByRole('link', { name: /Ambulanz anrufen/ })).toBeNull();

    // Tipps je Symptom mit Quelle; nur http(s) wird verlinkt
    const block = within(advice).getByTestId('advice-block');
    expect(within(block).getByRole('heading', { level: 3, name: 'Übelkeit' })).toBeVisible();
    expect(within(block).getAllByRole('listitem')).toHaveLength(2);
    const link = within(block).getByRole('link', { name: 'SPC (SÚKL)' });
    expect(link).toHaveAttribute('href', 'https://www.sukl.cz/spc');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(within(block).queryByRole('link', { name: 'Ohne Link' })).toBeNull();
    expect(within(block).getByText(/Ohne Link/)).toBeVisible();

    // Abschluss ohne Ampel/Grad/Stufe/Beruhigung/Reaktionszusage
    expect(document.querySelector('[data-traffic-light], [data-level], [data-status]')).toBeNull();
    expect(confirmation.textContent).not.toContain('ADV-'); // rule_id gehört nicht zur Patientin
    expect(findForbidden(confirmation.textContent)).toEqual([]);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    // Kennungen bleiben bis zur nächsten Fälligkeit im Speicher – nur Kennungen, nie Beleg oder Antworten
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toMatch(UUID);
    const stored = window.sessionStorage.getItem(SESSION_META_KEY) ?? '';
    expect(JSON.parse(stored)).toEqual({
      sessionId: 'sess-1',
      closed: true,
      until: '2026-10-20T09:00:00+02:00',
    });
    expect(Object.keys(window.sessionStorage)).toEqual(expect.not.arrayContaining(['Übelkeit']));
    expect(JSON.stringify(window.sessionStorage)).not.toMatch(/155|Tipps|Übelkeit|Schlucken/);
    // keine weitere Frage, keine Fortschrittsleiste mehr
    expect(screen.queryByTestId('session-card')).toBeNull();
    expect(screen.queryByTestId('session-progress')).toBeNull();
    expect(screen.getByTestId('session-due')).toHaveTextContent(/Nächster Check-in/);
  });

  it('zeigt bei „akut“ ohne lesbaren Text den Klinikwortlaut aus dem Katalog und eine echte Telefonnummer als Link', async () => {
    const confirmation = await finish(
      receipt({
        escalation: { level: 'acute', text: '[Text folgt]', ambulance_phone: '+420 123 456 789' },
      }),
    );
    const acute = within(confirmation).getByTestId('escalation-acute');
    expect(acute).toHaveTextContent('wenden Sie sich an die Ambulanz oder rufen Sie die 155 an');
    expect(acute.textContent).not.toMatch(/\[/);
    expect(within(acute).getByRole('link', { name: /\+420 123 456 789/ })).toHaveAttribute(
      'href',
      'tel:+420123456789',
    );
  });

  it('zeigt bei „general“ den allgemeinen Hinweis ohne Hervorhebung und keine leeren Tippblöcke', async () => {
    const confirmation = await finish(
      receipt({ advice: [{ symptom_key: 'nausea', label: 'Übelkeit', tips: [], sources: [] }] }),
    );
    expect(within(confirmation).queryByTestId('escalation-acute')).toBeNull();
    expect(within(confirmation).getByTestId('escalation-general')).toHaveTextContent(
      'wenden Sie sich an die Ambulanz',
    );
    expect(within(confirmation).queryByTestId('advice')).toBeNull();
  });

  it('lässt „Akut“-Hinweis und Tipps nie zusammen im selben Block erscheinen und stellt den Hinweis an den Anfang des Abschlusses', async () => {
    const confirmation = await finish(ACUTE_RECEIPT);
    expect(confirmation.firstElementChild).toBe(
      within(confirmation).getByTestId('escalation-acute'),
    );
  });
});

describe('Adaptiver Check-in: Fehler und Rückfall', () => {
  it('fällt bei fehlender Sitzungs-API (404) auf den vollständigen Fragebogen zurück', async () => {
    serve({ start: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    renderApp('/patient');
    expect(await screen.findByTestId('checkin-form')).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('bietet den Vollfragebogen unter /patient/full ohne Sitzung an', async () => {
    const { counts } = serve();
    renderApp('/patient/full');
    expect(await screen.findByTestId('checkin-form')).toBeVisible();
    expect(counts.start).toBe(0);
  });

  it('zeigt bei Serverfehler eine Meldung mit „Erneut versuchen“ und Link zum Vollfragebogen', async () => {
    const user = userEvent.setup();
    const { counts } = serve({
      start: (_body, attempt) =>
        attempt === 1 ? jsonResponse(ERROR_BODY('boom'), 500) : jsonResponse(STEP_1, 201),
    });
    renderApp('/patient');
    const error = await screen.findByTestId('session-error');
    expect(
      within(error).getByRole('link', { name: 'Vollständigen Fragebogen öffnen' }),
    ).toHaveAttribute('href', '/patient/full');
    await user.click(within(error).getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('session-card')).toBeVisible();
    expect(counts.start).toBe(2);
  });

  it('zeigt bei 403 „Kein Zugriff“', async () => {
    serve({ start: () => jsonResponse(ERROR_BODY('forbidden'), 403) });
    renderApp('/patient');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('übersetzt die Karten in en und de ohne Rohschlüssel', async () => {
    for (const lang of ['en', 'de'] as const) {
      await i18n.changeLanguage(lang);
      serve();
      const view = renderApp('/patient');
      await screen.findByTestId('session-card');
      expect(document.body.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
      view.unmount();
      window.sessionStorage.clear();
    }
  });
});

describe('Adaptiver Check-in: Beleg nie verlieren (Vertrag v2.5, F-10F)', () => {
  async function finishSession(r: SubmitReceipt) {
    const user = userEvent.setup();
    const server = serve({
      answer: () => jsonResponse(STOP_STEP(r)),
      session: () => jsonResponse(STOP_STEP(r)),
    });
    const view = renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Gelegentlich' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    await screen.findByTestId('checkin-confirmation');
    return { server, view, user };
  }

  it('zeigt nach Neuladen der Abschlussseite zuerst den Beleg (GET) mit Akut-Hinweis oben – ohne neue Sitzung', async () => {
    const { server, view } = await finishSession(ACUTE_RECEIPT);
    const clientId = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    const startsBefore = server.counts.start;
    view.unmount();

    renderApp('/patient');
    const confirmation = await screen.findByTestId('checkin-confirmation');
    expect(confirmation.firstElementChild).toBe(
      within(confirmation).getByTestId('escalation-acute'),
    );
    expect(within(confirmation).getByTestId('advice')).toBeVisible();
    expect(server.counts.get).toBeGreaterThanOrEqual(1);
    expect(server.counts.start).toBe(startsBefore); // keine neue Sitzung, keine erste Frage
    expect(screen.queryByTestId('session-card')).toBeNull();
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBe(clientId);
    expect(confirmation.textContent).not.toMatch(/\[[^\]]*\]/);
  });

  it('zeigt auf der Abschlussseite „Neuer Check-in“; der Knopf startet mit neuer Kennung bei der ersten Frage', async () => {
    const { server, user } = await finishSession(ACUTE_RECEIPT);
    const oldId = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
    await user.click(screen.getByRole('button', { name: 'Neuer Check-in' }));
    expect(await screen.findByTestId('session-card')).toBeVisible();
    const ids = callsTo(server.fetch, /\/waechter\/me\/sessions$/).map(
      (c) => c.body.client_session_id,
    );
    expect(ids.at(-1)).toMatch(UUID);
    expect(ids.at(-1)).not.toBe(oldId);
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBe(ids.at(-1));
    expect(screen.queryByTestId('checkin-confirmation')).toBeNull();
  });

  it('zeigt den Beleg auch bei einer identischen Wiederholung der letzten Antwort (200 + receipt)', async () => {
    const user = userEvent.setup();
    let failed = false;
    serve({
      answer: () => {
        if (!failed) {
          failed = true;
          throw new TypeError('offline'); // Antwort des Servers geht verloren
        }
        return jsonResponse(STOP_STEP(ACUTE_RECEIPT)); // Server: idempotent, gleicher Beleg
      },
    });
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    await user.click(within(card).getByRole('radio', { name: 'Gelegentlich' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    expect(await within(card).findByRole('alert')).toBeVisible();
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    const confirmation = await screen.findByTestId('checkin-confirmation');
    expect(within(confirmation).getByTestId('escalation-acute')).toBeVisible();
  });

  it('vergisst eine unbekannte gespeicherte Sitzung (GET 404) und beginnt normal', async () => {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, 'alte-kennung');
    window.sessionStorage.setItem(
      SESSION_META_KEY,
      JSON.stringify({ sessionId: 'fremd', closed: true, until: null }),
    );
    const { fetch } = serve(); // GET ⇒ 404
    renderApp('/patient');
    expect(await screen.findByTestId('session-card')).toBeVisible();
    const [start] = callsTo(fetch, /\/waechter\/me\/sessions$/);
    expect(start?.body.client_session_id).toMatch(UUID);
    expect(start?.body.client_session_id).not.toBe('alte-kennung');
  });

  it('zeigt bei einem Netzfehler beim Beleg-Abruf eine Meldung mit „Erneut versuchen“ statt still neu zu starten', async () => {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, 'k1');
    window.sessionStorage.setItem(
      SESSION_META_KEY,
      JSON.stringify({ sessionId: 'sess-1', closed: true, until: null }),
    );
    const user = userEvent.setup();
    let attempt = 0;
    const { counts } = serve({
      session: () => {
        attempt += 1;
        if (attempt === 1) throw new TypeError('offline');
        return jsonResponse(STOP_STEP(ACUTE_RECEIPT));
      },
    });
    renderApp('/patient');
    const error = await screen.findByTestId('session-error');
    expect(counts.start).toBe(0); // nie still eine neue Sitzung
    await user.click(within(error).getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('escalation-acute')).toBeVisible();
    expect(counts.start).toBe(0);
  });

  it('übersetzt „Neuer Check-in“ (cs/en) ohne Rohschlüssel (Beleg über gespeicherte Kennung)', async () => {
    for (const [lang, name] of [
      ['cs', 'Nový dotazník'],
      ['en', 'New check-in'],
    ] as const) {
      window.sessionStorage.setItem(SESSION_STORAGE_KEY, 'k1');
      window.sessionStorage.setItem(
        SESSION_META_KEY,
        JSON.stringify({ sessionId: 'sess-1', closed: true, until: null }),
      );
      await i18n.changeLanguage(lang);
      serve({ session: () => jsonResponse(STOP_STEP(ACUTE_RECEIPT)) });
      const view = renderApp('/patient');
      await screen.findByTestId('checkin-confirmation');
      expect(screen.getByRole('button', { name })).toBeVisible();
      expect(document.body.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
      view.unmount();
    }
  });

  describe('Fälligkeit des wiederhergestellten Belegs (A3 F-10F F-01)', () => {
    const PAST_DUE = {
      ...STOP_STEP(ACUTE_RECEIPT),
      due: { next_due_at: '2026-10-16T09:00:00+02:00', overdue: false, interval_days: 3 },
    };
    const delayed = (ms: number) => async () => {
      await new Promise((resolve) => setTimeout(resolve, ms));
      return jsonResponse(metaBody());
    };
    const store = () => {
      window.sessionStorage.setItem(SESSION_STORAGE_KEY, 'alte-kennung');
      window.sessionStorage.setItem(
        SESSION_META_KEY,
        JSON.stringify({ sessionId: 'sess-1', closed: true, until: '2026-10-16T09:00:00+02:00' }),
      );
    };

    it('beginnt einen neuen Check-in, sobald die Serverzeit eintrifft und die Fälligkeit erreicht ist – auch bei langsamem /meta', async () => {
      store();
      const { fetch } = serve({ session: () => jsonResponse(PAST_DUE), meta: delayed(300) });
      renderApp('/patient');
      // zunächst der gespeicherte Beleg (Serverzeit noch unbekannt, nie automatisch verwerfen) …
      expect(await screen.findByTestId('escalation-acute')).toBeVisible();
      // … dann, mit server_now (2026-10-17T09:00 > Fälligkeit), ein neuer Check-in mit neuer Kennung
      expect(await screen.findByTestId('session-card', undefined, { timeout: 3000 })).toBeVisible();
      expect(screen.queryByTestId('checkin-confirmation')).toBeNull();
      const starts = callsTo(fetch, /\/waechter\/me\/sessions$/);
      expect(starts).toHaveLength(1);
      expect(starts[0]?.body.client_session_id).toMatch(UUID);
      expect(starts[0]?.body.client_session_id).not.toBe('alte-kennung');
    });

    it('verwirft den Beleg nie automatisch, solange keine Serverzeit eintrifft', async () => {
      store();
      const { counts } = serve({
        session: () => jsonResponse(PAST_DUE),
        meta: () => jsonResponse(ERROR_BODY('boom'), 500),
      });
      renderApp('/patient');
      expect(await screen.findByTestId('escalation-acute')).toBeVisible();
      await new Promise((resolve) => setTimeout(resolve, 500));
      expect(screen.getByTestId('escalation-acute')).toBeVisible();
      expect(screen.queryByTestId('session-card')).toBeNull();
      expect(counts.start).toBe(0);
    });

    it('behält den Beleg, solange die Fälligkeit in der Zukunft liegt (Serverzeit bekannt)', async () => {
      window.sessionStorage.setItem(SESSION_STORAGE_KEY, 'k1');
      window.sessionStorage.setItem(
        SESSION_META_KEY,
        JSON.stringify({ sessionId: 'sess-1', closed: true, until: '2026-10-20T09:00:00+02:00' }),
      );
      const { counts } = serve({
        session: () => jsonResponse(STOP_STEP(ACUTE_RECEIPT)), // Fälligkeit 2026-10-20
        meta: delayed(100),
      });
      renderApp('/patient');
      expect(await screen.findByTestId('escalation-acute')).toBeVisible();
      await new Promise((resolve) => setTimeout(resolve, 500));
      expect(screen.getByTestId('escalation-acute')).toBeVisible();
      expect(counts.start).toBe(0);
    });

    it('lässt einen eben beendeten Check-in nie von selbst verschwinden, auch wenn die Serverzeit erst danach eintrifft', async () => {
      const user = userEvent.setup();
      const { counts } = serve({
        answer: () => jsonResponse(PAST_DUE), // Fälligkeit (Mock) liegt vor server_now
        meta: delayed(300),
      });
      renderApp('/patient');
      const card = await screen.findByTestId('session-card');
      await user.click(within(card).getByRole('radio', { name: 'Gelegentlich' }));
      await user.click(within(card).getByRole('button', { name: 'Weiter' }));
      expect(await screen.findByTestId('checkin-confirmation')).toBeVisible();
      await new Promise((resolve) => setTimeout(resolve, 700));
      expect(screen.getByTestId('checkin-confirmation')).toBeVisible();
      expect(screen.queryByTestId('session-card')).toBeNull();
      expect(counts.start).toBe(1);
    });
  });
});

describe('Adaptiver Check-in: Fortschrittsbalken mit Bodlík', () => {
  it('zeigt einen Balken mit role=progressbar, aria-Werten aus progress.asked/max und Text „x / y“', async () => {
    const user = userEvent.setup();
    serve();
    renderApp('/patient');
    const card = await screen.findByTestId('session-card');
    let bar = screen.getByRole('progressbar', { name: 'Fortschritt' });
    expect(bar).toHaveAttribute('aria-valuenow', '0');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '6');
    expect(screen.getByTestId('progress-count')).toHaveTextContent('0 / 6');
    // Igel ist reine Zierde
    expect(screen.getByTestId('bodlik').closest('[aria-hidden="true"]')).not.toBeNull();

    await user.click(within(card).getByRole('radio', { name: 'Gelegentlich' }));
    await user.click(within(card).getByRole('button', { name: 'Weiter' }));
    await screen.findByRole('radiogroup', { name: FEVER.text });
    bar = screen.getByRole('progressbar', { name: 'Fortschritt' });
    expect(bar).toHaveAttribute('aria-valuenow', '1');
    expect(screen.getByTestId('progress-count')).toHaveTextContent('1 / 6');
    expect(screen.getByTestId('patient-theme')).toBeInTheDocument();
  });
});

describe('Adaptiver Check-in: Zurück-Pfeil (Undo, T-31)', () => {
  it('blendet den Zurück-Pfeil bei der ersten Frage aus', async () => {
    serve();
    renderApp('/patient');
    await screen.findByTestId('session-card');
    expect(screen.queryByRole('button', { name: 'Zurück' })).toBeNull();
  });

  it('sendet steps = progress.asked an …/undo und zeigt die vorige Frage wieder', async () => {
    const user = userEvent.setup();
    const { fetch, counts } = serve({ start: () => jsonResponse(STEP_2, 201) });
    renderApp('/patient');
    await screen.findByRole('radiogroup', { name: FEVER.text });

    const back = screen.getByRole('button', { name: 'Zurück' });
    expect(back).toBeVisible();
    await user.click(back);

    expect(await screen.findByRole('radiogroup', { name: NAUSEA.text })).toBeVisible();
    const [undo] = callsTo(fetch, /\/undo$/);
    expect(undo?.url).toContain('/waechter/me/sessions/sess-1/undo');
    expect(undo?.body).toEqual({ steps: 1 });
    expect(counts.undo).toBe(1);
    expect(screen.queryByRole('button', { name: 'Zurück' })).toBeNull();
  });

  it('lädt bei 409 session_closed den Stand der Sitzung neu (kein stiller Neustart)', async () => {
    const user = userEvent.setup();
    const { counts } = serve({
      start: () => jsonResponse(STEP_2, 201),
      undo: () => jsonResponse(ERROR_BODY('session_closed'), 409),
      session: () => jsonResponse(STEP_1),
    });
    renderApp('/patient');
    await screen.findByRole('radiogroup', { name: FEVER.text });
    await user.click(screen.getByRole('button', { name: 'Zurück' }));

    expect(await screen.findByRole('radiogroup', { name: NAUSEA.text })).toBeVisible();
    expect(counts.get).toBe(1);
    expect(counts.start).toBe(1);
  });

  it('beschriftet den Zurück-Pfeil in cs und en', async () => {
    serve({ start: () => jsonResponse(STEP_2, 201) });
    await i18n.changeLanguage('cs');
    renderApp('/patient');
    expect(await screen.findByRole('button', { name: 'Zpět' })).toBeVisible();
    await i18n.changeLanguage('en');
    expect(await screen.findByRole('button', { name: 'Back' })).toBeVisible();
  });
});
