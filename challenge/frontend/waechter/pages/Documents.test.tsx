import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { DOCUMENT_MAX_BYTES, type ClinicDocument } from '../api/documents';
import { register } from '../../plugin';
import { ERROR_BODY, bodyOf, callUrl, serve, setViewport } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

const DOCS = '/api/v1/waechter/patients/pat-1/documents';

const CONDITION = {
  candidate_id: 'c1',
  resource_type: 'Condition' as const,
  code: 'C50.9',
  system: 'http://hl7.org/fhir/sid/icd-10',
  display: 'C50.9',
  value: null,
  unit: null,
  date: '2026-10-14',
  sukl_code: null,
  quote: 'Hlavní diagnóza: C50.9 – karcinom prsu (syntetický příklad).',
  state: 'draft' as const,
  decided_at: null,
};
const LAB = {
  ...CONDITION,
  candidate_id: 'c2',
  resource_type: 'Observation' as const,
  code: '718-7',
  system: 'http://loinc.org',
  display: 'Hemoglobin',
  value: '108',
  unit: 'g/l',
  quote: 'Hemoglobin;108;g/l;120-160',
};

function documentFixture(overrides: Partial<ClinicDocument> = {}): ClinicDocument {
  return {
    document_id: 'doc-1',
    patient_id: 'pat-1',
    filename: 'arztbrief_SYN-0001.md',
    sha256: 'a'.repeat(64),
    size_bytes: 1200,
    created_at: '2026-10-17T09:00:00+02:00',
    version: 1,
    extractor: { id: 'template-regex-v1', mode: 'template', fallback_reason: null },
    candidates: [CONDITION, LAB],
    rejected: [
      {
        resource_type: 'Condition',
        code: 'I10',
        quote: 'Vedlejší diagnóza: I10',
        reasons: ['code_not_allowed'],
      },
    ],
    counts: { draft: 2, confirmed: 0, discarded: 0, rejected: 1 },
    ...overrides,
  };
}

type Handler = (url: string, init: RequestInit | undefined) => Response | undefined;

/** Cockpit-Server der übrigen Seite plus die Dokument-Routen dieses Tests. */
function serveDocuments(handler: Handler) {
  const base = serve();
  const wrapped = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = callUrl(input);
    if (url.startsWith(DOCS)) {
      const answer = handler(url, init);
      if (answer) return Promise.resolve(answer);
    }
    return base(input, init);
  });
  vi.stubGlobal('fetch', wrapped);
  return wrapped;
}

const documentCalls = (fetchMock: ReturnType<typeof serveDocuments>) =>
  fetchMock.mock.calls.filter(([input]) => callUrl(input).startsWith(DOCS));

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

async function openPanel() {
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await user.click(await screen.findByTestId('cockpit-tab-texts')); // Tab „Freitexte & Dokumente“ (T-32)
  const panel = await screen.findByTestId('documents-panel');
  await user.click(panel.querySelector('summary') as HTMLElement);
  return { user, panel: within(panel), element: panel };
}

describe('Dokumente im Cockpit (T-21)', () => {
  it('ist eingeklappt und lädt die Liste erst beim Öffnen', async () => {
    const fetchMock = serveDocuments((_url, init) =>
      (init?.method ?? 'GET') === 'GET' ? jsonResponse([]) : undefined,
    );
    const user = userEvent.setup();
    renderApp('/clinic/patients/pat-1');
    await user.click(await screen.findByTestId('cockpit-tab-texts'));
    const panel = await screen.findByTestId('documents-panel');
    expect(panel).not.toHaveAttribute('open');
    expect(documentCalls(fetchMock)).toHaveLength(0);
    await user.click(panel.querySelector('summary') as HTMLElement);
    expect(await within(panel).findByTestId('documents-empty')).toBeVisible();
    expect(documentCalls(fetchMock)).toHaveLength(1);
  });

  it('zeigt Kandidaten mit Zitat, Extraktor und abgelehnten Vorschlägen', async () => {
    serveDocuments(() => jsonResponse([documentFixture()]));
    const { panel } = await openPanel();
    const cards = await panel.findAllByTestId('document-candidate');
    expect(cards).toHaveLength(2);
    expect(within(cards[0] as HTMLElement).getByText('C50.9')).toBeVisible();
    expect(within(cards[0] as HTMLElement).getByText(/karcinom prsu/)).toBeVisible();
    expect(within(cards[1] as HTMLElement).getByText('108 g/l · 2026-10-14')).toBeVisible();
    expect(panel.getByTestId('document-extractor')).toHaveTextContent(
      'Extraktion: template-regex-v1 (Regelwerk, ohne Sprachmodell)',
    );
    for (const state of panel.getAllByTestId('candidate-state')) {
      expect(state).toHaveTextContent('Entwurf, nicht bestätigt');
    }
    const rejected = panel.getByTestId('document-rejected');
    expect(rejected).toHaveTextContent('Nicht belegt, verworfen: 1');
    expect(rejected).toHaveTextContent('I10');
    expect(rejected).toHaveTextContent('Code nicht in der Allow-Liste');
  });

  it('weist auf den Rückfall hin, wenn das Sprachmodell nicht verfügbar war', async () => {
    serveDocuments(() =>
      jsonResponse([
        documentFixture({
          extractor: {
            id: 'template-regex-v1',
            mode: 'fallback',
            fallback_reason: 'llm_unavailable',
          },
        }),
      ]),
    );
    const { panel } = await openPanel();
    expect(await panel.findByTestId('document-extractor')).toHaveTextContent(
      'Rückfall auf Regelwerk, Sprachmodell nicht verfügbar',
    );
  });

  it('bestätigt eine Ressource per Klick und zeigt den neuen Stand', async () => {
    const confirmed = documentFixture({
      version: 2,
      candidates: [
        { ...CONDITION, state: 'confirmed', decided_at: '2026-10-17T09:05:00+02:00' },
        LAB,
      ],
      counts: { draft: 1, confirmed: 1, discarded: 0, rejected: 1 },
    });
    const fetchMock = serveDocuments((url, init) => {
      if (init?.method === 'POST') return jsonResponse(confirmed);
      return url === DOCS ? jsonResponse([documentFixture()]) : undefined;
    });
    const { user, panel } = await openPanel();
    await user.click(await panel.findByRole('button', { name: 'Bestätigen: C50.9' }));
    await waitFor(() =>
      expect(panel.getAllByTestId('candidate-state')[0]).toHaveTextContent(
        'Bestätigt, im Export enthalten',
      ),
    );
    const post = documentCalls(fetchMock).find(([, init]) => init?.method === 'POST');
    expect(callUrl(post?.[0] as string)).toBe(`${DOCS}/doc-1/candidates/c1`);
    expect(bodyOf(post?.[1])).toEqual({ decision: 'confirm' });
    // der bestätigte Eintrag hat keine Knöpfe mehr, der offene behält sie
    expect(panel.queryByRole('button', { name: 'Bestätigen: C50.9' })).toBeNull();
    expect(panel.getByRole('button', { name: 'Bestätigen: 718-7' })).toBeEnabled();
    expect(panel.getByText('1 offen · 1 bestätigt')).toBeVisible();
  });

  it('verwirft eine Ressource per Klick', async () => {
    const discarded = documentFixture({
      candidates: [{ ...CONDITION, state: 'discarded' }, LAB],
      counts: { draft: 1, confirmed: 0, discarded: 1, rejected: 1 },
    });
    const fetchMock = serveDocuments((url, init) => {
      if (init?.method === 'POST') return jsonResponse(discarded);
      return url === DOCS ? jsonResponse([documentFixture()]) : undefined;
    });
    const { user, panel } = await openPanel();
    await user.click(await panel.findByRole('button', { name: 'Verwerfen: C50.9' }));
    await waitFor(() =>
      expect(panel.getAllByTestId('candidate-state')[0]).toHaveTextContent(
        'Verworfen, nicht im Export',
      ),
    );
    const post = documentCalls(fetchMock).find(([, init]) => init?.method === 'POST');
    expect(bodyOf(post?.[1])).toEqual({ decision: 'discard' });
  });

  it('lädt die Liste neu, wenn eine parallele Entscheidung schneller war (409)', async () => {
    let lists = 0;
    serveDocuments((url, init) => {
      if (init?.method === 'POST') {
        return jsonResponse(ERROR_BODY('already_decided'), 409);
      }
      if (url !== DOCS) return undefined;
      lists += 1;
      return jsonResponse([
        lists === 1
          ? documentFixture()
          : documentFixture({ candidates: [{ ...CONDITION, state: 'confirmed' }, LAB] }),
      ]);
    });
    const { user, panel } = await openPanel();
    await user.click(await panel.findByRole('button', { name: 'Bestätigen: C50.9' }));
    await waitFor(() =>
      expect(panel.getAllByTestId('candidate-state')[0]).toHaveTextContent('Bestätigt'),
    );
    expect(panel.getByTestId('documents-status')).toHaveTextContent('bereits entschieden');
  });

  it('lädt eine Textdatei hoch und zeigt das Ergebnis', async () => {
    const created = documentFixture({ document_id: 'doc-2', filename: 'laborbefund.csv' });
    const fetchMock = serveDocuments((url, init) => {
      if (init?.method === 'POST') return jsonResponse(created, 201);
      return url === DOCS ? jsonResponse([]) : undefined;
    });
    const { user, panel } = await openPanel();
    await panel.findByTestId('documents-empty');
    const file = new File(['Hemoglobin;108;g/l;120-160\n'], 'laborbefund.csv', {
      type: 'text/csv',
    });
    await user.upload(panel.getByLabelText('Dokument hochladen'), file);
    expect(await panel.findByRole('heading', { name: 'laborbefund.csv' })).toBeVisible();
    const post = documentCalls(fetchMock).find(([, init]) => init?.method === 'POST');
    expect(callUrl(post?.[0] as string)).toBe(DOCS);
    expect(bodyOf(post?.[1])).toEqual({
      filename: 'laborbefund.csv',
      text: 'Hemoglobin;108;g/l;120-160\n',
    });
  });

  it.each([
    ['scan.pdf', 'x', 'PDF wird nicht unterstützt'],
    ['bild.png', 'x', 'nicht unterstützt (erlaubt: .txt, .md, .csv)'],
    ['gross.txt', 'x'.repeat(DOCUMENT_MAX_BYTES + 1), 'größer als 200 kB'],
  ])('lehnt %s schon im Browser ab (kein Request)', async (name, content, message) => {
    const fetchMock = serveDocuments((url, init) =>
      url === DOCS && (init?.method ?? 'GET') === 'GET' ? jsonResponse([]) : undefined,
    );
    const { panel } = await openPanel();
    await panel.findByTestId('documents-empty');
    // accept-Filter von user-event umgehen: Datei direkt als Änderungsereignis
    const input = panel.getByLabelText('Dokument hochladen');
    const user = userEvent.setup({ applyAccept: false });
    await user.upload(input, new File([content], name));
    expect(panel.getByTestId('documents-status')).toHaveTextContent(message);
    expect(documentCalls(fetchMock).filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  });

  it('übersetzt Serverfehler (nicht synthetisch, zu groß)', async () => {
    let status = 409;
    serveDocuments((url, init) => {
      if (init?.method === 'POST') {
        return jsonResponse(
          ERROR_BODY(status === 409 ? 'not_synthetic' : 'document_too_large'),
          status,
        );
      }
      return url === DOCS ? jsonResponse([]) : undefined;
    });
    const { user, panel } = await openPanel();
    await panel.findByTestId('documents-empty');
    const input = panel.getByLabelText('Dokument hochladen');
    await user.upload(input, new File(['a'], 'a.txt'));
    await waitFor(() =>
      expect(panel.getByTestId('documents-status')).toHaveTextContent(
        'nur synthetische Patientendaten',
      ),
    );
    status = 413;
    await user.upload(input, new File(['b'], 'b.txt'));
    await waitFor(() =>
      expect(panel.getByTestId('documents-status')).toHaveTextContent('größer als 200 kB'),
    );
  });

  it('zeigt einen Fehlerzustand, wenn die Liste nicht geladen werden kann', async () => {
    serveDocuments((url) =>
      url === DOCS ? jsonResponse(ERROR_BODY('forbidden'), 403) : undefined,
    );
    const { panel } = await openPanel();
    expect(await panel.findByRole('alert')).toHaveTextContent('Dafür fehlt die Berechtigung.');
  });

  it('hat Beschriftung, 16-px-Schrift und Touchziele ab 44 px (Klassen)', async () => {
    serveDocuments(() => jsonResponse([documentFixture()]));
    const { panel, element } = await openPanel();
    await panel.findAllByTestId('document-candidate');
    const input = panel.getByLabelText('Dokument hochladen');
    expect(input.className).toContain('min-h-11');
    expect(element.querySelector('summary')?.className).toContain('min-h-11');
    for (const button of panel.getAllByRole('button')) {
      expect(button.className).toContain('min-h-11');
    }
    expect(element.innerHTML).not.toMatch(/text-(xs|sm)\b/);
    expect(element.querySelectorAll('h1')).toHaveLength(0);
  });

  it.each([
    ['cs', 'Dokumenty', 'Nahrát dokument'],
    ['en', 'Documents', 'Upload document'],
    ['de', 'Dokumente', 'Dokument hochladen'],
  ])('ist in %s übersetzt', async (lang, title, upload) => {
    await i18n.changeLanguage(lang);
    serveDocuments(() => jsonResponse([]));
    const { panel } = await openPanel();
    expect(panel.getByText(title, { selector: 'summary' })).toBeVisible();
    expect(panel.getByLabelText(upload)).toBeVisible();
  });
});
