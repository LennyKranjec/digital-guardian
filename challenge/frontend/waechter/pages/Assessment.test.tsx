import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import type { FreeText } from '../api/client';
import { mapFieldErrors } from '../model/assessment';
import { ASSESSMENT_SAVED, OVERVIEW, TEMPLATE } from '../testing/cockpit-fixtures';
import {
  BASE,
  ERROR_BODY,
  bodyOf,
  serve,
  setViewport,
  type ServeOptions,
} from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

async function openAssessment(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1/assess');
  await screen.findByTestId('assessment-form');
  return { fetchMock, user };
}

const card = (term: string) =>
  within(document.querySelector(`[data-term="${term}"]`) as HTMLElement);

const posts = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls
    .filter(([url, init]) => url === `${BASE}/assessments` && init?.method === 'POST')
    .map(([, init]) => bodyOf(init));

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

describe('Aufnahme: Vorlage', () => {
  it('zeigt h1, Patientin, Quelle mit Link und je Begriff eine Karte', async () => {
    await openAssessment();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'CTCAE-Aufnahme' })).toBeVisible();
    expect(await screen.findByTestId('assess-patient')).toHaveTextContent('Rita Rot');
    expect(screen.getAllByTestId('term-card')).toHaveLength(3);
    const source = within(screen.getByTestId('assessment-source'));
    expect(
      source.getByText(
        /Common Terminology Criteria for Adverse Events \(CTCAE\) v6\.0, NCI\/NIH\/DHHS/,
      ),
    ).toBeInTheDocument();
    expect(source.getByRole('link', { name: 'Zum Originalprodukt (NCI)' })).toHaveAttribute(
      'href',
      'https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events/ctcae-v6.pdf',
    );
  });

  it('nennt ohne Quelle in der Vorlage NCI und CTCAE-Version und verlinkt das Originalprodukt', async () => {
    await openAssessment({ template: () => jsonResponse({ ...TEMPLATE, source: undefined }) });
    const source = within(screen.getByTestId('assessment-source'));
    expect(source.getByText(/Quelle: NCI, CTCAE v6\.0\./)).toBeInTheDocument();
    expect(source.getByRole('link')).toHaveAttribute(
      'href',
      'https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events',
    );
  });

  it('beschriftet Begriff (en) mit lokalisiertem Label und MedDRA-Code', async () => {
    await openAssessment();
    const nausea = document.querySelector('[data-term="CTCAE-NAUSEA"]') as HTMLElement;
    expect(within(nausea).getByText('Nausea · Übelkeit')).toBeInTheDocument();
    expect(within(nausea).getByText('MedDRA-Code 10028813')).toBeInTheDocument();
    // Label gleich Begriff ⇒ nicht doppelt
    expect(
      within(document.querySelector('[data-term="CTCAE-FATIGUE"]') as HTMLElement).getByText(
        'Fatigue',
      ),
    ).toBeInTheDocument();
  });

  it('bietet nur Grad 0 und die in CTCAE definierten Grade mit Originaltext an', async () => {
    await openAssessment();
    const names = (term: string) =>
      card(term)
        .getAllByRole('radio')
        .map((radio) => radio.closest('label')?.textContent);
    expect(names('CTCAE-NAUSEA')).toEqual([
      'Nicht bewerten',
      'Grad 0 – nicht vorhanden',
      'Grad 1Loss of appetite without alteration in eating habits',
      'Grad 2Oral intake decreased without significant weight loss, dehydration or malnutrition',
      'Grad 3Inadequate oral caloric or fluid intake; tube feeding, TPN, or hospitalization indicated',
    ]);
    // Fieber: Grade 1–4 definiert, 5 nicht ⇒ kein Grad 5
    expect(card('CTCAE-FEVER').queryByRole('radio', { name: /^Grad 5/ })).not.toBeInTheDocument();
    expect(card('CTCAE-FEVER').getByRole('radio', { name: /^Grad 4/ })).toBeInTheDocument();
    // Fatigue: Grad 3 fehlt, Grad 4 hat leeren Text ⇒ beide nicht anbieten
    expect(names('CTCAE-FATIGUE')).toHaveLength(4);
    expect(card('CTCAE-FATIGUE').queryByRole('radio', { name: /^Grad 3/ })).not.toBeInTheDocument();
    expect(card('CTCAE-FATIGUE').queryByRole('radio', { name: /^Grad 4/ })).not.toBeInTheDocument();
    // Gradtexte sind als englischer Originaltext ausgezeichnet
    expect(card('CTCAE-FEVER').getByText(/38\.0 - 39\.0 degrees C/)).toHaveAttribute('lang', 'en');
  });

  it('wählt keinen Grad vor und schlägt aus den PRO-Werten keinen vor', async () => {
    await openAssessment();
    for (const term of TEMPLATE.terms) {
      expect(card(term.ctcae_term_id).getByRole('radio', { name: 'Nicht bewerten' })).toBeChecked();
      expect(
        card(term.ctcae_term_id)
          .getAllByRole('radio')
          .filter((radio) => (radio as HTMLInputElement).checked),
      ).toHaveLength(1);
    }
    // Attribution/Notiz erst nach einer Gradwahl
    expect(
      card('CTCAE-NAUSEA').queryByLabelText('Zusammenhang mit der Therapie'),
    ).not.toBeInTheDocument();
  });

  it('zeigt den PRO-Verlauf nur als Hinweis und den letzten Grad', async () => {
    await openAssessment();
    const nausea = within(card('CTCAE-NAUSEA').getByTestId('pro-hint'));
    expect(nausea.getByText('PRO-Verlauf (nur Hinweis)')).toBeInTheDocument();
    expect(nausea.getByText('Schwere (Maximum): 3')).toBeInTheDocument();
    expect(nausea.getByText('Schwere (zuletzt): 3')).toBeInTheDocument();
    expect(nausea.getByText('Letzte Aufnahme: Grad 1')).toBeInTheDocument();
    expect(nausea.getByText(/keine Gradvorgabe/)).toBeInTheDocument();
    const fever = within(card('CTCAE-FEVER').getByTestId('pro-hint'));
    expect(fever.getByText('Vorhandensein (Maximum): 1')).toBeInTheDocument();
    expect(fever.getByText('Vorhandensein (zuletzt): 1')).toBeInTheDocument();
    expect(fever.getByText('Noch keine Aufnahme zu diesem Begriff.')).toBeInTheDocument();
    expect(
      within(card('CTCAE-FATIGUE').getByTestId('pro-hint')).getByText(
        'Keine Angaben seit dem letzten Termin.',
      ),
    ).toBeInTheDocument();
  });

  it('verknüpft standardmäßig alle offenen Meldungen der Patientin', async () => {
    await openAssessment();
    const related = within(
      await screen.findByRole('group', { name: 'Mit offenen Meldungen verknüpfen' }),
    );
    const boxes = await related.findAllByRole('checkbox');
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box).toBeChecked();
    expect(related.getByRole('checkbox', { name: /Fieber gemeldet/ })).toBeInTheDocument();
  });

  it('sagt „Keine offene Meldung zum Verknüpfen.“ ohne offene Meldungen', async () => {
    await openAssessment({ overview: () => jsonResponse({ ...OVERVIEW, open_alerts: [] }) });
    expect(await screen.findByText('Keine offene Meldung zum Verknüpfen.')).toBeInTheDocument();
  });

  it('zeigt einen Leerzustand ohne Begriffe', async () => {
    await openAssessment({ template: () => jsonResponse({ ...TEMPLATE, terms: [] }) });
    expect(screen.getByText('Keine Begriffe')).toBeInTheDocument();
  });
});

describe('Aufnahme: Speichern', () => {
  it('verlangt mindestens einen bewerteten Begriff und sendet sonst nichts', async () => {
    const { fetchMock, user } = await openAssessment();
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Bitte bewerten Sie mindestens einen Begriff.',
    );
    expect(posts(fetchMock)).toHaveLength(0);
  });

  it('sendet nur bewertete Begriffe mit Grad, Zusammenhang, Notiz und verknüpften Meldungen, dann zurück ins Cockpit', async () => {
    const { fetchMock, user } = await openAssessment();
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 2/ }));
    await user.selectOptions(
      card('CTCAE-NAUSEA').getByLabelText('Zusammenhang mit der Therapie'),
      'probable',
    );
    await user.type(
      card('CTCAE-NAUSEA').getByRole('textbox', { name: 'Notiz (optional)' }),
      ' nach Gabe ',
    );
    await user.click(card('CTCAE-FEVER').getByRole('radio', { name: 'Grad 0 – nicht vorhanden' }));
    await screen.findAllByRole('checkbox');
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));

    // zurück im Cockpit mit Hinweis
    expect(await screen.findByRole('heading', { level: 1, name: 'Rita Rot' })).toBeVisible();
    expect(await screen.findByTestId('cockpit-notice')).toHaveTextContent(
      'CTCAE-Aufnahme gespeichert.',
    );
    const [body] = posts(fetchMock);
    expect(posts(fetchMock)).toHaveLength(1);
    expect(body?.client_submission_id).toMatch(UUID);
    expect(body?.items).toEqual([
      { ctcae_term_id: 'CTCAE-NAUSEA', grade: 2, attribution: 'probable', note: 'nach Gabe' },
      { ctcae_term_id: 'CTCAE-FEVER', grade: 0, attribution: 'unknown' },
    ]);
    expect(body?.related_alert_ids).toEqual(['al-2', 'al-1']);
    const call = fetchMock.mock.calls.find(
      ([url, init]) => url === `${BASE}/assessments` && init?.method === 'POST',
    );
    expect(call?.[1]?.headers).toMatchObject({ 'X-Requested-With': 'fetch' });
  });

  it('lässt abgewählte Meldungen aus der Verknüpfung heraus', async () => {
    const { fetchMock, user } = await openAssessment();
    await user.click(card('CTCAE-FEVER').getByRole('radio', { name: /^Grad 1/ }));
    const boxes = await screen.findAllByRole('checkbox');
    await user.click(screen.getByRole('checkbox', { name: /Übelkeit stärker als gewohnt/ }));
    expect(boxes.filter((box) => (box as HTMLInputElement).checked)).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));
    await screen.findByTestId('cockpit-header');
    expect(posts(fetchMock)[0]?.related_alert_ids).toEqual(['al-1']);
  });

  it('lässt related_alert_ids weg, wenn nichts verknüpft ist', async () => {
    const { fetchMock, user } = await openAssessment({
      overview: () => jsonResponse({ ...OVERVIEW, open_alerts: [] }),
    });
    await user.click(card('CTCAE-FEVER').getByRole('radio', { name: /^Grad 1/ }));
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));
    await screen.findByTestId('cockpit-header');
    expect(posts(fetchMock)[0]).not.toHaveProperty('related_alert_ids');
  });

  it('ordnet 422-Feldfehler dem richtigen Begriff zu (Position in der gesendeten Liste)', async () => {
    const { user } = await openAssessment({
      assessmentPost: () =>
        jsonResponse(
          {
            ...ERROR_BODY('validation_error'),
            field_errors: [
              {
                field: 'items[1].grade',
                code: 'grade_not_defined',
                message: 'Grade 4 is not defined',
              },
              {
                field: 'related_alert_ids',
                code: 'foreign_alert',
                message: 'Alert belongs to another patient',
              },
            ],
          },
          422,
        ),
    });
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 1/ }));
    await user.click(card('CTCAE-FEVER').getByRole('radio', { name: /^Grad 4/ }));
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));

    const fever = await card('CTCAE-FEVER').findByTestId('term-errors');
    expect(fever).toHaveTextContent('Hinweis des Servers: Grade 4 is not defined');
    expect(card('CTCAE-NAUSEA').queryByTestId('term-errors')).not.toBeInTheDocument();
    const general = screen
      .getAllByRole('alert')
      .find((alert) => alert.textContent?.includes('Alert belongs to another patient'));
    expect(general).toHaveTextContent('Die Aufnahme wurde nicht akzeptiert.');
    // Eingaben bleiben erhalten, kein Wechsel der Seite
    expect(card('CTCAE-FEVER').getByRole('radio', { name: /^Grad 4/ })).toBeChecked();
    expect(screen.queryByTestId('cockpit-header')).not.toBeInTheDocument();
  });

  it('wiederholt nach Netzfehler mit derselben client_submission_id, bei Änderung mit neuer', async () => {
    const { fetchMock, user } = await openAssessment({
      assessmentPost: (_body, attempt) => {
        if (attempt <= 2) throw new TypeError('Failed to fetch');
        return jsonResponse(ASSESSMENT_SAVED, 201);
      },
    });
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 2/ }));
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));
    expect(await screen.findByRole('button', { name: 'Erneut senden' })).toBeInTheDocument();
    expect(
      screen.getByText(/Keine Verbindung zum Server\. Ihre Eingaben bleiben erhalten/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Erneut senden' }));
    await screen.findByText(/Keine Verbindung zum Server/);
    let sent = posts(fetchMock);
    expect(sent).toHaveLength(2);
    expect(sent[1]?.client_submission_id).toBe(sent[0]?.client_submission_id);
    expect(sent[1]?.items).toEqual(sent[0]?.items);

    // Änderung ⇒ neue ID
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 3/ }));
    await user.click(screen.getByRole('button', { name: 'Erneut senden' }));
    await screen.findByTestId('cockpit-header');
    sent = posts(fetchMock);
    expect(sent).toHaveLength(3);
    expect(sent[2]?.client_submission_id).not.toBe(sent[0]?.client_submission_id);
  });

  it('sperrt den Knopf während des Sendens (kein Doppelversand)', async () => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const fetchMock = serve();
    const original = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) => {
      if (typeof input === 'string' && input === `${BASE}/assessments`) await gate;
      return original ? original(input, init) : new Response(null, { status: 500 });
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1/assess');
    await screen.findByTestId('assessment-form');
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 1/ }));
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));
    expect(await screen.findByRole('button', { name: 'Wird gespeichert …' })).toBeDisabled();
    release?.();
    await screen.findByTestId('cockpit-header');
    expect(posts(fetchMock)).toHaveLength(1);
  });

  it.each([
    [404, 'not_found', 'Diese Patient:in existiert nicht (mehr).'],
    [403, 'forbidden', 'Dafür fehlt die Berechtigung.'],
    [500, 'internal', 'Das Speichern hat nicht geklappt.'],
  ])('zeigt bei Status %i eine verständliche Meldung', async (status, code, text) => {
    const { user } = await openAssessment({
      assessmentPost: () => jsonResponse(ERROR_BODY(code), status),
    });
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 1/ }));
    await user.click(screen.getByRole('button', { name: 'Aufnahme speichern' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
  });
});

describe('Aufnahme: Zustände, Rollen, Sprache', () => {
  it('zeigt Ladezustand und bei 404 den Nicht-gefunden-Zustand mit Rückweg', async () => {
    serve({ template: () => jsonResponse(ERROR_BODY('not_found'), 404) });
    renderApp('/clinic/patients/pat-1/assess');
    expect(await screen.findByText('Seite nicht gefunden')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'Zur Patientenakte' })).toBeInTheDocument();
  });

  it('zeigt bei Serverfehler „Erneut versuchen“ und lädt neu', async () => {
    let calls = 0;
    serve({
      template: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(ERROR_BODY('internal'), 500) : jsonResponse(TEMPLATE);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1/assess');
    await user.click(await screen.findByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('assessment-form')).toBeInTheDocument();
  });

  it('bricht ab und kehrt ins Cockpit zurück, ohne zu speichern', async () => {
    const { fetchMock, user } = await openAssessment();
    await user.click(card('CTCAE-NAUSEA').getByRole('radio', { name: /^Grad 2/ }));
    await user.click(screen.getByRole('link', { name: 'Abbrechen' }));
    expect(await screen.findByTestId('cockpit-header')).toBeInTheDocument();
    expect(posts(fetchMock)).toHaveLength(0);
  });

  it('enthält in der Oberfläche keine Diagnose, Therapieempfehlung oder Beruhigung', async () => {
    await openAssessment();
    const main = document.getElementById('main');
    expect(findForbiddenClinician(main?.textContent ?? '')).toEqual([]);
  });
});

describe('mapFieldErrors', () => {
  const sent = [
    { ctcae_term_id: 'CTCAE-A', grade: 1 },
    { ctcae_term_id: 'CTCAE-B', grade: 2 },
  ];

  it('erkennt gängige Pfadschreibweisen (Klammer, Punkt, Schrägstrich, mit Präfix)', () => {
    for (const field of [
      'items[1].grade',
      'items.1.grade',
      'body.items.1.grade',
      'items/1/grade',
    ]) {
      const result = mapFieldErrors([{ field, code: 'x', message: 'm' }], sent);
      expect(result.byTerm.get('CTCAE-B'), field).toEqual(['m']);
      expect(result.general, field).toEqual([]);
    }
  });

  it('erkennt Pfade mit Begriffskennung und sammelt alles andere allgemein', () => {
    const result = mapFieldErrors(
      [
        { field: 'items[CTCAE-A].grade', code: 'x', message: 'a' },
        { field: 'items[7].grade', code: 'x', message: 'außerhalb' },
        { field: 'related_alert_ids', code: 'x', message: 'r' },
        { field: '', code: 'x', message: 'leer' },
      ],
      sent,
    );
    expect(result.byTerm.get('CTCAE-A')).toEqual(['a']);
    expect(result.general).toEqual(['außerhalb', 'r', 'leer']);
  });

  it('bündelt mehrere Fehler je Begriff', () => {
    const result = mapFieldErrors(
      [
        { field: 'items[0].grade', code: 'x', message: 'eins' },
        { field: 'items[0].note', code: 'x', message: 'zwei' },
      ],
      sent,
    );
    expect(result.byTerm.get('CTCAE-A')).toEqual(['eins', 'zwei']);
  });
});

describe('Aufnahme: Freitext-Zitate je Begriff (T-22)', () => {
  const FEVER: FreeText = {
    free_text_id: 'ft-1',
    response_id: 'resp-9',
    patient_id: 'pat-1',
    text: 'Mám horečku od rána',
    lang: 'cs',
    created_at: '2026-10-17T07:00:00+02:00',
    suggestions: [
      {
        symptom_key: 'fever',
        label: 'Fieber',
        attribute: null,
        proposed_value: null,
        quote: 'horečku',
        start: 4,
        end: 11,
        in_questionnaire: true,
        confirmed: true,
        answers: [{ attribute: 'presence', value: 1 }],
      },
    ],
    mapper: 'template-v1',
    mode: 'template',
    rejected_suggestions: 0,
    unconfirmed: 0,
  };

  it('zeigt das Zitat nur an dem Begriff, dessen Symptom zugeordnet ist, ohne Gradvorschlag', async () => {
    await openAssessment({ freeTexts: () => jsonResponse([FEVER]) });
    const mention = await within(
      document.querySelector('[data-term="CTCAE-FEVER"]') as HTMLElement,
    ).findByTestId('free-text-mentions');
    expect(mention).toHaveTextContent('Patientin schrieb: „horečku“');
    expect(mention).toHaveTextContent('bestätigt durch Antwort: ja');
    expect(
      within(document.querySelector('[data-term="CTCAE-NAUSEA"]') as HTMLElement).queryByTestId(
        'free-text-mentions',
      ),
    ).not.toBeInTheDocument();
  });
});
