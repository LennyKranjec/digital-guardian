import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import type { FreeText, FreeTextSuggestion } from '../api/client';
import { setViewport, serve, type ServeOptions } from '../testing/cockpit-server';
import { ANCHOR, WORKLIST } from '../testing/fixtures';

function suggestion(overrides: Partial<FreeTextSuggestion>): FreeTextSuggestion {
  return {
    symptom_key: 'fever',
    label: 'Fieber',
    attribute: null,
    proposed_value: null,
    quote: 'horečku',
    start: 4,
    end: 11,
    in_questionnaire: true,
    confirmed: false,
    answers: [],
    ...overrides,
  };
}

const FEVER_TEXT: FreeText = {
  free_text_id: 'ft-fever',
  response_id: 'resp-9',
  patient_id: 'pat-1',
  text: 'Mám horečku od rána',
  lang: 'cs',
  created_at: '2026-10-17T07:00:00+02:00',
  suggestions: [suggestion({})],
  mapper: 'template-v1',
  mode: 'template',
  rejected_suggestions: 0,
  unconfirmed: 1,
};

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
}

async function openCockpit(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => urlOf(url).includes('/free-texts'))).toBe(true),
  );
  await new Promise((resolve) => setTimeout(resolve, 30));
}

beforeEach(() => {
  register(pluginApi);
  setViewport(false);
  vi.setSystemTime(new Date(ANCHOR));
});

afterEach(async () => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetRegistry();
  await i18n.changeLanguage('de');
});

describe('Meldungskarte: „Patientin schrieb: …“ (T-22)', () => {
  it('zeigt Zitat, Datum, Modus und „bestätigt: nein“ an der Meldung zum Symptom', async () => {
    await openCockpit({ freeTexts: () => jsonResponse([FEVER_TEXT]) });
    const mentions = await screen.findAllByTestId('free-text-mentions');
    const text = mentions.map((m) => m.textContent).join(' ');
    expect(text).toContain('Patientin schrieb: „horečku“');
    expect(text).toContain('Wortliste');
    expect(text).toContain('bestätigt durch Antwort: nein');
  });

  it('zeigt „bestätigt: ja“, sobald die Patientin die Folgefrage beantwortet hat', async () => {
    const confirmed: FreeText = {
      ...FEVER_TEXT,
      unconfirmed: 0,
      suggestions: [
        suggestion({ confirmed: true, answers: [{ attribute: 'presence', value: 1 }] }),
      ],
    };
    await openCockpit({ freeTexts: () => jsonResponse([confirmed]) });
    const mentions = await screen.findAllByTestId('free-text-mentions');
    expect(mentions[0]).toHaveTextContent('bestätigt durch Antwort: ja');
  });

  it('zeigt nichts zu Symptomen ohne Zitat und nichts ohne Freitexte', async () => {
    const other: FreeText = {
      ...FEVER_TEXT,
      suggestions: [suggestion({ symptom_key: 'headache', label: 'Kopfschmerz' })],
    };
    await openCockpit({ freeTexts: () => jsonResponse([other]) });
    expect(screen.queryByTestId('free-text-mentions')).not.toBeInTheDocument();
  });

  it('ändert nichts an der Meldung: kein Gradvorschlag in der Zitatzeile', async () => {
    await openCockpit({ freeTexts: () => jsonResponse([FEVER_TEXT]) });
    const mentions = await screen.findAllByTestId('free-text-mentions');
    for (const mention of mentions) expect(mention.textContent).not.toMatch(/Grad|Stufe|Ampel/);
  });
});

describe('Arbeitsliste: Freitext-Zuordnung unbestätigt (T-22)', () => {
  it('zeigt den Hinweis nur bei Zeilen mit offener Zuordnung, ohne Alarm', async () => {
    const rows = WORKLIST.map((row) =>
      row.patient_id === 'pat-1' ? { ...row, free_text_unconfirmed: 2 } : row,
    );
    serve({ worklist: () => jsonResponse(rows) });
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    const badges = screen.getAllByTestId('free-text-unconfirmed');
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveTextContent('Freitext unbestätigt (2)');
    const row = badges[0]?.closest('[data-testid="worklist-row"]') as HTMLElement;
    expect(within(row).getByText(/Rita Rot/)).toBeVisible();
    expect(badges[0]?.getAttribute('role')).not.toBe('alert');
  });

  it('zeigt keinen Hinweis, wenn das Feld fehlt oder 0 ist', async () => {
    serve({});
    renderApp('/clinic');
    await screen.findByTestId('worklist-cards');
    expect(screen.queryByTestId('free-text-unconfirmed')).not.toBeInTheDocument();
  });
});
