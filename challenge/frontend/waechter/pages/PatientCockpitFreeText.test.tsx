import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import type { FreeText } from '../api/client';
import { findForbiddenClinician } from '../i18n/forbidden';
import { ERROR_BODY, serve, setViewport, type ServeOptions } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

const TEXT_NEW = 'Mám PRŮJEM a nemůžu dýchat';
const TEXT_OLD = 'Bolí mě hlava';

const NEW: FreeText = {
  free_text_id: 'ft-new',
  response_id: 'resp-2',
  patient_id: 'pat-1',
  text: TEXT_NEW,
  lang: 'cs',
  created_at: '2026-10-17T07:00:00+02:00',
  suggestions: [
    {
      symptom_key: 'diarrhea',
      label: 'Durchfall',
      attribute: null,
      proposed_value: 3,
      quote: 'PRŮJEM',
      start: 4,
      end: 10,
      in_questionnaire: true,
      confirmed: true,
      answers: [{ attribute: 'frequency', value: 2 }],
    },
    {
      symptom_key: 'shortness_of_breath',
      label: 'Atemnot',
      attribute: null,
      proposed_value: null,
      quote: 'dýchat',
      start: 20,
      end: 26,
      in_questionnaire: false,
      confirmed: false,
      answers: [],
    },
  ],
  mapper: 'template-v1',
  mode: 'template',
  rejected_suggestions: 0,
  unconfirmed: 1,
};

const OLD: FreeText = {
  free_text_id: 'ft-old',
  response_id: 'resp-1',
  patient_id: 'pat-1',
  text: TEXT_OLD,
  lang: 'cs',
  created_at: '2026-10-15T09:00:00+02:00',
  suggestions: [],
  mapper: 'openai:fake',
  mode: 'fallback',
  rejected_suggestions: 2,
  unconfirmed: 0,
};

function urlOf(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
}

/** Öffnet das Cockpit und wartet, bis die Freitexte angefragt und verarbeitet sind. */
async function openCockpit(options: ServeOptions = {}) {
  const fetchMock = serve(options);
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  await userEvent.setup().click(await screen.findByTestId('cockpit-tab-texts')); // Tab „Freitexte & Dokumente“ (T-32)
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => urlOf(url).includes('/free-texts'))).toBe(true),
  );
  await new Promise((resolve) => setTimeout(resolve, 30));
  return fetchMock;
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

describe('Cockpit: Abschnitt „Freitexte“ (T-22)', () => {
  it('bleibt ohne Freitexte vollständig verborgen', async () => {
    await openCockpit();
    expect(screen.queryByTestId('free-texts')).not.toBeInTheDocument();
  });

  it('listet neueste zuerst, mit Modus, Hinweis „nicht bewertet“ und „unbestätigt“-Kennzeichen', async () => {
    await openCockpit({ freeTexts: () => jsonResponse([NEW, OLD]) });
    const section = await screen.findByTestId('free-texts');
    expect(within(section).getByRole('heading', { name: 'Freitexte der Patientin' })).toBeVisible();
    expect(section).toHaveTextContent('nicht bewertet');
    const items = within(section).getAllByTestId('free-text-item');
    expect(items).toHaveLength(2);
    expect(within(items[0]!).getByTestId('free-text-body')).toHaveTextContent(TEXT_NEW);
    expect(within(items[1]!).getByTestId('free-text-body')).toHaveTextContent(TEXT_OLD);
    expect(within(items[0]!).getByTestId('free-text-mode')).toHaveTextContent('Wortliste');
    expect(within(items[0]!).getByTestId('free-text-mode')).toHaveAttribute(
      'data-mode',
      'template',
    );
    expect(within(items[0]!).getByTestId('free-text-unconfirmed')).toHaveTextContent(
      'Freitext unbestätigt (1)',
    );
    expect(within(items[1]!).queryByTestId('free-text-unconfirmed')).not.toBeInTheDocument();
    expect(within(items[1]!).getByTestId('free-text-mode')).toHaveTextContent(
      'Wortliste (Rückfall)',
    );
  });

  it('hebt die Zitate hervor und zeigt Vorschläge als Chips „→ Symptom“', async () => {
    await openCockpit({ freeTexts: () => jsonResponse([NEW, OLD]) });
    const [first, second] = await screen.findAllByTestId('free-text-item');
    const quotes = within(first!).getAllByTestId('free-text-quote');
    expect(quotes.map((q) => q.textContent)).toEqual(['PRŮJEM', 'dýchat']);
    expect(quotes[0]!.tagName).toBe('MARK');
    const chips = within(first!).getAllByTestId('free-text-chip');
    expect(chips).toHaveLength(2);
    // getrackt: Vorschlagswert nur als Hinweis „zählt nicht“, bestätigt durch die Antwort der Patientin
    expect(chips[0]).toHaveTextContent('→ Durchfall');
    expect(chips[0]).toHaveTextContent('Vorschlagswert (zählt nicht): 3');
    expect(chips[0]).toHaveTextContent('Patientin hat die Folgefrage beantwortet (frequency: 2)');
    expect(chips[0]).toHaveAttribute('data-confirmed', 'true');
    // außerhalb der getrackten Symptome: eigene Gruppe, unbestätigt, ohne Vorschlagswert
    expect(chips[1]).toHaveTextContent('→ Atemnot');
    expect(chips[1]).toHaveTextContent('Zuordnung unbestätigt');
    expect(within(chips[1]!).queryByTestId('free-text-proposed')).not.toBeInTheDocument();
    const groups = within(first!).getAllByTestId('free-text-group');
    expect(groups.map((g) => g.querySelector('p')?.textContent)).toEqual([
      'Vorgeschlagene Zuordnung (nicht bewertet):',
      'Außerhalb der getrackten Symptome',
    ]);
    expect(within(second!).queryAllByTestId('free-text-quote')).toHaveLength(0);
    expect(within(second!).getByText('Kein Zuordnungsvorschlag.')).toBeVisible();
  });

  it('zeigt Text der Patientin nur als Text (kein Markup, kein HTML aus dem Freitext)', async () => {
    const hostile: FreeText = {
      ...OLD,
      free_text_id: 'ft-x',
      text: '<img src=x onerror=alert(1)> <b>fett</b>',
      suggestions: [],
    };
    await openCockpit({ freeTexts: () => jsonResponse([hostile]) });
    const body = await screen.findByTestId('free-text-body');
    expect(body).toHaveTextContent('<img src=x onerror=alert(1)> <b>fett</b>');
    expect(body.querySelector('img, b')).toBeNull();
  });

  it('zeigt bei einem Ladefehler eine Meldung, aber nicht bei fehlender Berechtigung', async () => {
    await openCockpit({ freeTexts: () => jsonResponse(ERROR_BODY('boom'), 500) });
    expect(await screen.findByText('Freitexte konnten nicht geladen werden.')).toBeVisible();
  });

  it('blendet den Abschnitt bei 403 aus', async () => {
    await openCockpit({ freeTexts: () => jsonResponse(ERROR_BODY('forbidden'), 403) });
    expect(screen.queryByTestId('free-texts')).not.toBeInTheDocument();
  });

  it.each(['cs', 'en', 'de'] as const)(
    '%s: Texte des Abschnitts tragen keine verbotene Wendung für die Ärztin',
    async (lang) => {
      await i18n.changeLanguage(lang);
      const keys = [
        'title',
        'note',
        'proposed',
        'confirmed',
        'unconfirmed',
        'outside',
        'tracked',
        'wrote',
        'yes',
        'no',
        'suggested',
        'noSuggestion',
        'error',
        'modes.template',
        'modes.live',
        'modes.fallback',
      ];
      const texts = keys.map((key) =>
        i18n.t(`waechter.clinic.freeText.${key}`, {
          value: 1,
          quote: 'x',
          date: 'd',
          mode: 'm',
          confirmed: 'ja',
        }),
      );
      expect(texts.every((text) => text !== '' && !text.startsWith('waechter.'))).toBe(true);
      for (const text of [...texts, i18n.t('waechter.clinic.freeTextUnconfirmed', { count: 2 })])
        expect(findForbiddenClinician(text)).toEqual([]);
    },
  );
});
