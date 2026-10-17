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
import type { ResponseSubmit } from '../api/client';
import { findForbidden } from '../i18n/forbidden';
import { PATIENT, QUESTIONNAIRE, RECEIPT } from '../testing/fixtures';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ERROR_BODY = (code: string) => ({ code, message: code, field_errors: [] });

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
}

function bodyOf(init: RequestInit | undefined): string {
  return typeof init?.body === 'string' ? init.body : '';
}

type PostHandler = (init: RequestInit | undefined, attempt: number) => Response;

/** Gemockter Server: angemeldet als `me`, Fragebogen und `POST /me/responses` je nach Handler. */
function serve(options: { me?: unknown; questionnaire?: () => Response; post?: PostHandler }) {
  let attempt = 0;
  return mockFetch((url, init) => {
    if (url.endsWith('/auth/me')) {
      return options.me === undefined
        ? jsonResponse(ERROR_BODY('unauthenticated'), 401)
        : jsonResponse(options.me);
    }
    if (url.includes('/waechter/me/questionnaire')) {
      return options.questionnaire?.() ?? jsonResponse(QUESTIONNAIRE);
    }
    if (url.endsWith('/waechter/me/responses') && init?.method === 'POST') {
      attempt += 1;
      return (options.post ?? (() => jsonResponse(RECEIPT, 201)))(init, attempt);
    }
    return defaultApiResponse(url);
  });
}

function posts(fetchMock: ReturnType<typeof serve>): ResponseSubmit[] {
  return fetchMock.mock.calls
    .filter(
      ([url, init]) => urlOf(url).endsWith('/waechter/me/responses') && init?.method === 'POST',
    )
    .map(([, init]) => JSON.parse(bodyOf(init)) as ResponseSubmit);
}

function group(question: string) {
  return within(screen.getByRole('radiogroup', { name: question }));
}

beforeEach(() => {
  register(pluginApi);
});

afterEach(async () => {
  vi.unstubAllGlobals();
  resetRegistry();
  await i18n.changeLanguage('de');
});

describe('Check-in: Darstellung', () => {
  it('lädt den Fragebogen in der UI-Sprache und zeigt Auswahlgrund, Zeitraum und Fortschritt', async () => {
    const fetchMock = serve({ me: PATIENT });
    renderApp('/patient/full');

    expect(await screen.findByTestId('checkin-form')).toBeInTheDocument();
    const questionnaireCalls = fetchMock.mock.calls.filter(([url]) =>
      urlOf(url).includes('/waechter/me/questionnaire'),
    );
    expect(questionnaireCalls[0]?.[0]).toBe('/api/v1/waechter/me/questionnaire?lang=de');
    expect(screen.getByTestId('selection-reason')).toHaveTextContent(
      QUESTIONNAIRE.selection_reason ?? '',
    );
    expect(screen.getByTestId('recall-period')).toHaveTextContent('In den letzten 7 Tagen');
    expect(screen.getByTestId('checkin-progress')).toHaveTextContent('0 von 3 beantwortet');
  });

  it('zeigt unter dem Fragebogen den Hinweis auf die eigene Formulierung und den Prototyp-Hinweis', async () => {
    serve({ me: PATIENT });
    renderApp('/patient/full');
    const notice = await screen.findByTestId('pro-ctcae-notice');
    expect(notice).toHaveTextContent(
      'Fragen in eigener Formulierung nach der Struktur von PRO-CTCAE®',
    );
    expect(notice).toHaveTextContent('Forschungsprototyp; nicht für diagnostische');
  });

  it('hat genau eine h1, je Item ein fieldset mit legend und je Frage eine benannte Radiogruppe', async () => {
    serve({ me: PATIENT });
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('group', { name: 'Übelkeit' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Fieber' })).toBeInTheDocument();
    const form = within(screen.getByTestId('checkin-form'));
    expect(form.getAllByRole('radiogroup')).toHaveLength(3);
    // 5 + 5 + 2 Optionen plus je Frage „Überspringen“ ⇒ 15 native Radios, alle per Name erreichbar
    expect(form.getAllByRole('radio')).toHaveLength(15);
    expect(form.getAllByRole('radio', { name: 'Überspringen' })).toHaveLength(3);
    expect(group('Hatten Sie Fieber?').getAllByRole('radio')).toHaveLength(3);
  });

  it('fragt mit der aktiven UI-Sprache (en) und zeigt englische Oberflächentexte', async () => {
    await i18n.changeLanguage('en');
    const fetchMock = serve({ me: PATIENT });
    renderApp('/patient/full');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Record your symptoms' }),
    ).toBeVisible();
    await screen.findByTestId('checkin-form');
    expect(fetchMock.mock.calls.some(([url]) => urlOf(url).endsWith('questionnaire?lang=en'))).toBe(
      true,
    );
    expect(screen.getByTestId('checkin-progress')).toHaveTextContent('0 of 3 answered');
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });

  it('zeigt den Leerzustand, wenn der Fragebogen keine Items hat', async () => {
    serve({ me: PATIENT, questionnaire: () => jsonResponse({ ...QUESTIONNAIRE, items: [] }) });
    renderApp('/patient/full');

    expect(await screen.findByText('Kein Fragebogen verfügbar')).toBeInTheDocument();
    expect(screen.queryByTestId('checkin-form')).not.toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('zeigt den Fehlerzustand beim Laden und lädt mit „Erneut versuchen“ neu', async () => {
    let calls = 0;
    serve({
      me: PATIENT,
      questionnaire: () => {
        calls += 1;
        return calls === 1
          ? jsonResponse(ERROR_BODY('internal'), 500)
          : jsonResponse(QUESTIONNAIRE);
      },
    });
    const user = userEvent.setup();
    renderApp('/patient/full');

    expect(await screen.findByText('Das hat nicht geklappt')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('checkin-form')).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('zeigt bei 403 den Zustand „Kein Zugriff“', async () => {
    serve({ me: PATIENT, questionnaire: () => jsonResponse(ERROR_BODY('forbidden'), 403) });
    renderApp('/patient/full');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });
});

describe('Check-in: Senden', () => {
  it('sendet Antworten, Überspringen als null und Unbeantwortetes als null; danach neutrale Bestätigung', async () => {
    const fetchMock = serve({ me: PATIENT });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');

    await user.click(
      group('Wie oft hatten Sie Übelkeit?').getByRole('radio', { name: 'Gelegentlich' }),
    );
    await user.click(
      group('Wie stark war die Übelkeit?').getByRole('radio', { name: 'Überspringen' }),
    );
    expect(screen.getByTestId('checkin-progress')).toHaveTextContent('1 von 3 beantwortet');
    expect(screen.getByTestId('checkin-progress')).toHaveTextContent('1 übersprungen');

    await user.click(screen.getByRole('button', { name: 'Senden' }));

    const confirmation = await screen.findByTestId('checkin-confirmation');
    const [body] = posts(fetchMock);
    expect(posts(fetchMock)).toHaveLength(1);
    expect(body?.client_submission_id).toMatch(UUID);
    expect(body?.questionnaire_id).toBe('items-v1:regimen-a');
    expect(body?.channel).toBe('web');
    expect(body?.entered_by).toBe('self');
    expect(body?.answers).toEqual([
      { symptom_key: 'nausea', attribute: 'frequency', value: 2 },
      { symptom_key: 'nausea', attribute: 'severity', value: null },
      { symptom_key: 'fever', attribute: 'presence', value: null },
    ]);
    const postInit = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')?.[1];
    expect(postInit?.headers).toMatchObject({ 'X-Requested-With': 'fetch' });

    // neutrale Bestätigung aus message_key, Eskalationstext nur als Platzhalter
    expect(confirmation).toHaveTextContent('Vielen Dank. Ihre Angaben wurden gespeichert.');
    expect(screen.getByTestId('escalation-placeholder')).toHaveTextContent(
      '[Text der Klinik folgt]',
    );
    expect(findForbidden(confirmation.textContent)).toEqual([]);
    // keine Bewertung: kein Ampel-/Grad-/Statuselement
    expect(document.querySelector('[data-status]')).toBeNull();
    expect(screen.queryByTestId('checkin-form')).not.toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });

  it('sendet die angezeigte Rückblick-Variante (recall) mit, wenn der Server sie liefert', async () => {
    const fetchMock = serve({
      me: PATIENT,
      questionnaire: () => jsonResponse({ ...QUESTIONNAIRE, recall: 'daily_24h' }),
    });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(screen.getByRole('button', { name: 'Senden' }));
    await screen.findByTestId('checkin-confirmation');
    expect(posts(fetchMock)[0]?.recall).toBe('daily_24h');
  });

  it('sendet kein recall, wenn der Fragebogen keine Variante nennt', async () => {
    const fetchMock = serve({ me: PATIENT });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(screen.getByRole('button', { name: 'Senden' }));
    await screen.findByTestId('checkin-confirmation');
    expect(posts(fetchMock)[0]).not.toHaveProperty('recall');
  });

  it('erlaubt das Senden ohne Antworten (alles null)', async () => {
    const fetchMock = serve({ me: PATIENT });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');

    await user.click(screen.getByRole('button', { name: 'Senden' }));
    await screen.findByTestId('checkin-confirmation');
    expect(posts(fetchMock)[0]?.answers.every((answer) => answer.value === null)).toBe(true);
  });

  it('nutzt für unbekannte message_key den neutralen Standardtext', async () => {
    serve({
      me: PATIENT,
      post: () => jsonResponse({ ...RECEIPT, message_key: 'unbekannt.schluessel' }, 201),
    });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByTestId('checkin-confirmation')).toHaveTextContent(
      'Ihre Angaben wurden gespeichert.',
    );
  });

  it('wiederholt nach Netzfehler mit DERSELBEN client_submission_id', async () => {
    const fetchMock = serve({
      me: PATIENT,
      post: (_init, attempt) => {
        if (attempt === 1) throw new TypeError('Failed to fetch');
        return jsonResponse(RECEIPT, 200);
      },
    });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(group('Hatten Sie Fieber?').getByRole('radio', { name: 'Nein' }));

    await user.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Keine Verbindung zum Server');
    expect(screen.getByTestId('checkin-form')).toBeInTheDocument();
    // Eingaben bleiben erhalten
    expect(group('Hatten Sie Fieber?').getByRole('radio', { name: 'Nein' })).toBeChecked();

    await user.click(screen.getByRole('button', { name: 'Erneut senden' }));
    expect(await screen.findByTestId('checkin-confirmation')).toBeInTheDocument();

    const sent = posts(fetchMock);
    expect(sent).toHaveLength(2);
    expect(sent[0]?.client_submission_id).toMatch(UUID);
    expect(sent[1]?.client_submission_id).toBe(sent[0]?.client_submission_id);
    expect(sent[1]?.answers).toEqual(sent[0]?.answers);
  });

  it('vergibt eine neue ID, wenn die Antworten nach einem Fehler geändert werden', async () => {
    const fetchMock = serve({
      me: PATIENT,
      post: (_init, attempt) => {
        if (attempt === 1) throw new TypeError('Failed to fetch');
        return jsonResponse(RECEIPT, 201);
      },
    });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');

    await user.click(screen.getByRole('button', { name: 'Senden' }));
    await screen.findByRole('alert');
    await user.click(group('Hatten Sie Fieber?').getByRole('radio', { name: 'Ja' }));
    await user.click(screen.getByRole('button', { name: 'Erneut senden' }));
    await screen.findByTestId('checkin-confirmation');

    const sent = posts(fetchMock);
    expect(sent).toHaveLength(2);
    expect(sent[1]?.client_submission_id).not.toBe(sent[0]?.client_submission_id);
  });

  it('zeigt bei 422 eine verständliche Meldung und behält die Eingaben', async () => {
    serve({ me: PATIENT, post: () => jsonResponse(ERROR_BODY('validation_error'), 422) });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(group('Hatten Sie Fieber?').getByRole('radio', { name: 'Ja' }));
    await user.click(screen.getByRole('button', { name: 'Senden' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Einige Angaben wurden nicht akzeptiert.',
    );
    expect(group('Hatten Sie Fieber?').getByRole('radio', { name: 'Ja' })).toBeChecked();
    expect(screen.queryByTestId('checkin-confirmation')).not.toBeInTheDocument();
  });

  it('zeigt bei 409 (idempotency_conflict) eine verständliche Meldung', async () => {
    serve({ me: PATIENT, post: () => jsonResponse(ERROR_BODY('idempotency_conflict'), 409) });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'bereits mit anderen Angaben gespeichert',
    );
  });

  it('zeigt bei 500 die allgemeine Sendemeldung', async () => {
    serve({ me: PATIENT, post: () => jsonResponse(ERROR_BODY('internal'), 500) });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');
    await user.click(screen.getByRole('button', { name: 'Senden' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Das Senden hat nicht geklappt');
  });

  it('sperrt den Sendeknopf, solange ein Versand läuft (kein Doppelversand)', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve({ me: PATIENT });
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (urlOf(input).endsWith('/waechter/me/responses')) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    const user = userEvent.setup();
    renderApp('/patient/full');
    await screen.findByTestId('checkin-form');

    await user.click(screen.getByRole('button', { name: 'Senden' }));
    const busy = await screen.findByRole('button', { name: 'Wird gesendet …' });
    expect(busy).toBeDisabled();
    release?.();
    await waitFor(() => expect(screen.getByTestId('checkin-confirmation')).toBeInTheDocument());
    expect(posts(fetchMock)).toHaveLength(1);
  });
});
