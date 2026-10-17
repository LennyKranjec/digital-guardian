import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import {
  META_FIXTURE,
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbidden } from '../i18n/forbidden';
import { PATIENT, QUESTIONNAIRE, RECEIPT } from '../testing/fixtures';

const ERROR_BODY = (code: string) => ({ code, message: code, field_errors: [] });

function metaWith(freeText: unknown) {
  return {
    ...META_FIXTURE,
    challenge_loaded: true,
    waechter: {
      server_now: '2026-10-17T09:00:00+02:00',
      timezone: 'Europe/Prague',
      content_versions: { items: 'items-v1', rules: 'rules-v1', report: 'report-v1' },
      ...(freeText === undefined ? {} : { free_text: freeText }),
    },
  };
}

const ENABLED = metaWith({ enabled: true, max_length: 500 });

type PostHandler = (body: Record<string, unknown>, attempt: number) => Response;
type AnswerHandler = (body: Record<string, unknown>) => Response;

const OPTIONS = [
  { value: 0, label: 'Nein' },
  { value: 1, label: 'Ja' },
];

const CARD = (symptom: string, label: string, critical = false) => ({
  free_text_id: 'ft-1',
  symptom_key: symptom,
  label,
  quote: `zitat ${symptom}`,
  critical,
  questions: [{ attribute: 'presence', text: `Hatten Sie ${label}?`, options: OPTIONS }],
});

const SAVED = (followups: ReturnType<typeof CARD>[] = []) => ({
  free_text_id: 'ft-1',
  response_id: RECEIPT.response_id,
  saved: true,
  followups,
});

/** Gemockter Server: angemeldet als Patientin, Fragebogen, Senden, Freitext je Handler. */
function serve(
  options: {
    meta?: unknown;
    post?: PostHandler;
    cards?: ReturnType<typeof CARD>[];
    answer?: AnswerHandler;
  } = {},
) {
  let attempt = 0;
  return mockFetch((url, init) => {
    if (url.endsWith('/auth/me')) return jsonResponse(PATIENT);
    if (url.endsWith('/meta')) return jsonResponse(options.meta ?? ENABLED);
    if (url.includes('/waechter/me/questionnaire')) return jsonResponse(QUESTIONNAIRE);
    if (url.endsWith('/waechter/me/responses') && init?.method === 'POST') {
      return jsonResponse(RECEIPT, 201);
    }
    if (url.endsWith('/waechter/me/free-text') && init?.method === 'POST') {
      attempt += 1;
      const body = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as Record<
        string,
        unknown
      >;
      return (options.post ?? (() => jsonResponse(SAVED(), 201)))(body, attempt);
    }
    if (url.includes('/waechter/me/free-text/followups')) {
      return jsonResponse(options.cards ?? []);
    }
    if (/\/waechter\/me\/free-text\/[^/]+\/answers$/.test(url) && init?.method === 'POST') {
      const body = JSON.parse(typeof init.body === 'string' ? init.body : '{}') as Record<
        string,
        unknown
      >;
      return (options.answer ?? (() => jsonResponse(RECEIPT, 201)))(body);
    }
    return defaultApiResponse(url);
  });
}

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
}

function freeTextPosts(fetchMock: ReturnType<typeof serve>): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(
      ([url, init]) => urlOf(url).endsWith('/waechter/me/free-text') && init?.method === 'POST',
    )
    .map(
      ([, init]) =>
        JSON.parse(typeof init?.body === 'string' ? init.body : '{}') as Record<string, unknown>,
    );
}

/** Füllt nichts aus und sendet den Fragebogen (alles unbeantwortet ist erlaubt). */
async function reachConfirmation() {
  const user = userEvent.setup();
  renderApp('/patient/full');
  await screen.findByTestId('checkin-form');
  await user.click(screen.getByRole('button', { name: 'Senden' }));
  await screen.findByTestId('checkin-confirmation');
  return user;
}

beforeEach(() => {
  register(pluginApi);
});

afterEach(async () => {
  vi.unstubAllGlobals();
  resetRegistry();
  await i18n.changeLanguage('de');
});

describe('Freitext der Patientin: Feld am Ende des Check-ins', () => {
  it('zeigt nach dem Senden das optionale Feld mit Zähler und Höchstlänge aus /meta', async () => {
    serve();
    await reachConfirmation();
    const section = await screen.findByTestId('free-text');
    expect(within(section).getByRole('heading', { name: 'Weitere Beschwerden' })).toBeVisible();
    const input = within(section).getByTestId('free-text-input');
    expect(input).toHaveAttribute('maxlength', '500');
    expect(input).toHaveAccessibleName(/Optional\. Schreiben Sie/);
    expect(within(section).getByTestId('free-text-counter')).toHaveTextContent('0 von 500 Zeichen');
    expect(within(section).getByTestId('free-text-send')).toBeDisabled(); // leer ⇒ nichts zu senden
  });

  it('zählt Zeichen, aktiviert Senden erst mit Text und sendet getrimmt zur Antwort', async () => {
    const fetchMock = serve();
    const user = await reachConfirmation();
    const input = await screen.findByTestId('free-text-input');
    await user.type(input, '  Mám průjem  ');
    expect(screen.getByTestId('free-text-counter')).toHaveTextContent('14 von 500 Zeichen');
    await user.click(screen.getByTestId('free-text-send'));

    expect(await screen.findByTestId('free-text-saved')).toHaveTextContent(
      'Danke. Ihre Ergänzung wurde gespeichert.',
    );
    expect(freeTextPosts(fetchMock)).toEqual([
      { response_id: RECEIPT.response_id, text: 'Mám průjem', lang: 'de' },
    ]);
    expect(screen.queryByTestId('free-text-input')).not.toBeInTheDocument();
    // keine Bewertung: keine Ampel, kein Alarm, keine Vorschläge für die Patientin
    expect(screen.getByTestId('free-text')).not.toHaveTextContent(/Vorschlag|Stufe|Ampel/);
  });

  it('wird nicht angezeigt, wenn /meta den Freitext abschaltet oder nichts darüber sagt', async () => {
    for (const meta of [metaWith({ enabled: false, max_length: 500 }), metaWith(undefined)]) {
      serve({ meta });
      await reachConfirmation();
      expect(screen.queryByTestId('free-text')).not.toBeInTheDocument();
      resetRegistry();
      register(pluginApi);
      document.body.innerHTML = '';
    }
  });

  it('zeigt nach dem Speichern Folgefragen mit Zitat und den Standardoptionen, kritische zuerst', async () => {
    const cards = [CARD('fever', 'Fieber', true), CARD('diarrhea', 'Durchfall')];
    serve({ post: () => jsonResponse(SAVED(cards), 201), cards });
    const user = await reachConfirmation();
    await user.type(await screen.findByTestId('free-text-input'), 'Fieber und Durchfall');
    await user.click(screen.getByTestId('free-text-send'));

    const list = await screen.findAllByTestId('followup-card');
    expect(list.map((card) => card.dataset.symptom)).toEqual(['fever', 'diarrhea']);
    const first = list[0] as HTMLElement;
    expect(within(first).getByTestId('followup-quote')).toHaveTextContent(
      'Sie schrieben: „zitat fever“',
    );
    expect(within(first).getByRole('radio', { name: 'Nein' })).not.toBeChecked();
    expect(within(first).getByRole('radio', { name: 'Ja' })).not.toBeChecked(); // nichts vorgewählt
    expect(within(first).getByTestId('followup-send')).toBeDisabled();
  });

  it('sendet die Antwort der Patientin je Karte; ein Akut-Hinweis erscheint sofort und die Karte bleibt als erledigt', async () => {
    const cards = [CARD('fever', 'Fieber', true)];
    let answered = false;
    const fetchMock = serve({
      post: () => jsonResponse(SAVED(cards), 201),
      cards,
      answer: () => {
        answered = true;
        return jsonResponse(
          {
            ...RECEIPT,
            escalation: {
              level: 'acute',
              text: 'Bei akuten Beschwerden kontaktieren Sie die Ambulanz oder rufen Sie 155 an.',
              ambulance_phone: null,
            },
          },
          201,
        );
      },
    });
    const user = await reachConfirmation();
    await user.type(await screen.findByTestId('free-text-input'), 'Fieber');
    await user.click(screen.getByTestId('free-text-send'));
    const card = await screen.findByTestId('followup-card');
    await user.click(within(card).getByRole('radio', { name: 'Ja' }));
    await user.click(within(card).getByTestId('followup-send'));

    const done = await screen.findByTestId('followup-done');
    expect(answered).toBe(true);
    expect(within(done).getByTestId('escalation-acute')).toHaveTextContent('rufen Sie 155 an');
    expect(done).toHaveTextContent('Ihre Antwort zu „Fieber“ wurde gespeichert');
    const call = fetchMock.mock.calls.find(([url]) => urlOf(url).endsWith('/answers'));
    expect(urlOf(call?.[0] ?? '')).toContain('/waechter/me/free-text/ft-1/answers');
    const body = JSON.parse(typeof call?.[1]?.body === 'string' ? call[1].body : '{}') as Record<
      string,
      unknown
    >;
    expect(body.answers).toEqual([{ symptom_key: 'fever', attribute: 'presence', value: 1 }]);
    expect(typeof body.client_submission_id).toBe('string');
  });

  it('erlaubt „Überspringen“ als Antwort (Wert null) und zeigt keine Folgefragen ohne Zuordnung', async () => {
    const cards = [CARD('diarrhea', 'Durchfall')];
    const fetchMock = serve({ post: () => jsonResponse(SAVED(cards), 201), cards });
    const user = await reachConfirmation();
    await user.type(await screen.findByTestId('free-text-input'), 'Durchfall');
    await user.click(screen.getByTestId('free-text-send'));
    const card = await screen.findByTestId('followup-card');
    await user.click(within(card).getByRole('radio', { name: 'Überspringen' }));
    await user.click(within(card).getByTestId('followup-send'));
    await screen.findByTestId('followup-done');
    const call = fetchMock.mock.calls.find(([url]) => urlOf(url).endsWith('/answers'));
    const body = JSON.parse(typeof call?.[1]?.body === 'string' ? call[1].body : '{}') as {
      answers: { value: unknown }[];
    };
    expect(body.answers[0]?.value).toBeNull();
  });

  it('zeigt ohne offene Karten keinen Folgefragen-Abschnitt', async () => {
    serve();
    const user = await reachConfirmation();
    await user.type(await screen.findByTestId('free-text-input'), 'nichts Besonderes');
    await user.click(screen.getByTestId('free-text-send'));
    await screen.findByTestId('free-text-saved');
    expect(screen.queryByTestId('followups')).not.toBeInTheDocument();
  });

  it('zeigt bei Netzfehler eine Meldung, behält den Text und erlaubt erneutes Senden', async () => {
    const fetchMock = serve({
      post: (_body, attempt) =>
        attempt === 1 ? jsonResponse(ERROR_BODY('boom'), 503) : jsonResponse(SAVED(), 201),
    });
    const user = await reachConfirmation();
    const input = await screen.findByTestId('free-text-input');
    await user.type(input, 'Text bleibt');
    await user.click(screen.getByTestId('free-text-send'));
    expect(await screen.findByTestId('free-text-error')).toHaveTextContent(
      'Speichern fehlgeschlagen',
    );
    expect(screen.getByTestId('free-text-input')).toHaveValue('Text bleibt');
    await user.click(screen.getByRole('button', { name: 'Erneut senden' }));
    await waitFor(() => expect(screen.getByTestId('free-text-saved')).toBeVisible());
    expect(freeTextPosts(fetchMock)).toHaveLength(2);
  });

  it('übersetzt 422 und 409 in verständliche Meldungen', async () => {
    serve({ post: () => jsonResponse(ERROR_BODY('validation_failed'), 422) });
    const user = await reachConfirmation();
    await user.type(await screen.findByTestId('free-text-input'), 'zu lang');
    await user.click(screen.getByTestId('free-text-send'));
    expect(await screen.findByTestId('free-text-error')).toHaveTextContent('nicht angenommen');
  });

  it.each(['cs', 'en', 'de'] as const)(
    '%s: Texte tragen keine verbotene Wendung (Beruhigung, Alarm, Zusage)',
    async (lang) => {
      await i18n.changeLanguage(lang);
      const texts = [
        'waechter.patient.freeText.title',
        'waechter.patient.freeText.hint',
        'waechter.patient.freeText.saved',
        'waechter.patient.freeText.errors.generic',
      ].map((key) => i18n.t(key, { max: 500 }));
      expect(texts.every((text) => text !== '' && !text.startsWith('waechter.'))).toBe(true);
      for (const text of texts) expect(findForbidden(text)).toEqual([]);
      expect(i18n.t('waechter.patient.freeText.hint', { max: 500 })).toContain('155');
    },
  );
});
