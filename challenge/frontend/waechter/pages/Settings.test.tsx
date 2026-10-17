import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { CONFIG } from '../testing/cockpit-fixtures';
import {
  ERROR_BODY,
  bodyOf,
  callUrl,
  serve,
  setViewport,
  type ServeOptions,
} from '../testing/cockpit-server';
import { ADMIN, ANCHOR, CLINICIAN } from '../testing/fixtures';

const RULES_URL = '/api/v1/waechter/config/rules';
const REPORT_URL = '/api/v1/waechter/config/report';

async function openSettings(options: ServeOptions = {}) {
  const fetchMock = serve({ me: ADMIN, ...options });
  const user = userEvent.setup();
  renderApp('/clinic/settings');
  await screen.findByTestId('rules-section');
  return { fetchMock, user };
}

const putCalls = (fetchMock: ReturnType<typeof serve>, url: string) =>
  fetchMock.mock.calls.filter(([input, init]) => callUrl(input) === url && init?.method === 'PUT');

const rule = (id: string) => within(document.querySelector(`[data-rule="${id}"]`) as HTMLElement);

async function writeNote(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByRole('textbox', { name: 'Änderungsnotiz (Pflicht)' }), text);
}

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

describe('Einstellungen: Ansicht für Ärztinnen (nur lesen)', () => {
  it('zeigt Regeln mit ID, Art, Stufe, Status, Parametern, Begründung und Quelle – ohne Eingabefelder', async () => {
    await openSettings({ me: CLINICIAN });
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1, name: 'Einstellungen' })).toBeVisible();
    expect(screen.getByTestId('settings-role-note')).toHaveTextContent('(nur lesen)');

    const cards = screen.getAllByTestId('rule-card');
    expect(cards.map((card) => card.getAttribute('data-rule'))).toEqual([
      'R-SEV-01',
      'R-URG-01',
      'R-OFF-01',
      'R-DLT-01',
    ]);
    const severity = rule('R-SEV-01');
    expect(severity.getByText('Rot')).toBeInTheDocument();
    expect(severity.getByText('Schwelle')).toBeInTheDocument();
    expect(severity.getByTestId('rule-active')).toHaveTextContent('aktiv');
    expect(severity.getByText('Mindestwert (Wert ≥) (Skalenwert 0–4)')).toBeInTheDocument();
    expect(severity.getByText('3')).toBeInTheDocument();
    expect(severity.getByText('Eine Meldung entsteht ab diesem Wert.')).toBeInTheDocument();
    // Begründung in der Anfragesprache bzw. englischer Rückfall, Quelle
    expect(severity.getByText('Demo threshold, not clinically validated.')).toBeInTheDocument();
    expect(severity.getByText('Quelle: SRC-DEMO')).toBeInTheDocument();
    expect(rule('R-OFF-01').getByTestId('rule-active')).toHaveTextContent('inaktiv');

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: 'aktiv' })).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Neue Regelversion speichern' }),
    ).not.toBeInTheDocument();
    for (const box of within(screen.getByTestId('report-settings')).getAllByRole('checkbox')) {
      expect(box).toBeDisabled();
    }
    expect(within(screen.getByTestId('report-settings')).getByRole('combobox')).toBeDisabled();
  });

  it('zeigt Versionshistorie (wer/wann/Notiz/aktiv) und Fragebogen-Profile je Therapie', async () => {
    await openSettings({ me: CLINICIAN });
    const history = within(await screen.findByTestId('history-rules'));
    expect(await history.findByText('rules-v2')).toBeInTheDocument();
    expect(history.getByText('Admin (Demo)')).toBeInTheDocument();
    expect(history.getByText('Schwelle angepasst')).toBeInTheDocument();
    expect(history.getByText('aktiv')).toBeInTheDocument();
    expect(history.getByText('abgelöst')).toBeInTheDocument();
    expect(await screen.findByTestId('history-report')).toBeInTheDocument();

    const profiles = within(screen.getByTestId('regimen-profiles'));
    const cards = profiles.getAllByTestId('regimen-card');
    expect(cards).toHaveLength(2);
    expect(
      within(cards[0] as HTMLElement).getByText('FOLFOX (oxaliplatin, fluorouracil)'),
    ).toBeInTheDocument();
    expect(
      within(cards[0] as HTMLElement).getByText(
        /oxaliplatin \(L01XA03\), fluorouracil \(L01BC02\)/,
      ),
    ).toBeInTheDocument();
    expect(within(cards[0] as HTMLElement).getByText('14 Tage')).toBeInTheDocument();
    expect(
      within(cards[0] as HTMLElement).getByText(/Tingling or numbness, Nausea, Fever/),
    ).toBeInTheDocument();
    expect(within(cards[1] as HTMLElement).getByText(/Tiredness/)).toBeInTheDocument();
    expect(profiles.getByTestId('core-symptoms')).toHaveTextContent('Nausea, Fever, Tiredness');
    expect(profiles.getByText(/Die Fragen entstehen aus der Medikation/)).toBeInTheDocument();
  });

  it('meldet fehlende Historie (404) ehrlich statt leer', async () => {
    await openSettings({
      me: CLINICIAN,
      history: () => jsonResponse(ERROR_BODY('not_found'), 404),
    });
    expect(
      await within(screen.getByTestId('history-rules')).findByText(
        'Die Versionshistorie ist noch nicht verfügbar.',
      ),
    ).toBeInTheDocument();
  });

  it('zeigt Lade-, Fehler- und Zugriffszustände', async () => {
    serve({ me: CLINICIAN, config: () => jsonResponse(ERROR_BODY('forbidden'), 403) });
    renderApp('/clinic/settings');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('bietet bei Serverfehler „Erneut versuchen“', async () => {
    let calls = 0;
    serve({
      me: CLINICIAN,
      config: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(ERROR_BODY('internal'), 500) : jsonResponse(CONFIG);
      },
    });
    const user = userEvent.setup();
    renderApp('/clinic/settings');
    await user.click(await screen.findByRole('button', { name: 'Erneut versuchen' }));
    expect(await screen.findByTestId('rules-section')).toBeInTheDocument();
  });

  it('verlinkt die Einstellungen in der Navigation', async () => {
    serve({ me: CLINICIAN });
    renderApp('/clinic');
    const nav = await screen.findByRole('navigation', { name: 'Hauptnavigation' });
    expect(await within(nav).findByRole('link', { name: 'Einstellungen' })).toHaveAttribute(
      'href',
      '/clinic/settings',
    );
  });
});

describe('Einstellungen: Regeln ändern (Administration)', () => {
  it('zeigt Eingabefelder mit Einheit und Erklärung und eine Pflichtnotiz', async () => {
    await openSettings();
    expect(screen.getByTestId('settings-role-note')).toHaveTextContent(
      'Als Administration können Sie Regeln ändern',
    );
    const input = rule('R-SEV-01').getByRole('textbox', {
      name: 'Mindestwert (Wert ≥) (Skalenwert 0–4)',
    });
    expect(input).toHaveValue('3');
    expect(input).toHaveAccessibleDescription('Eine Meldung entsteht ab diesem Wert.');
    expect(rule('R-SEV-01').getByRole('checkbox', { name: 'aktiv' })).toBeChecked();
    expect(rule('R-OFF-01').getByRole('checkbox', { name: 'aktiv' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Neue Regelversion speichern' })).toBeDisabled(); // unverändert
    expect(screen.getByRole('textbox', { name: 'Änderungsnotiz (Pflicht)' })).toBeRequired();
    expect(screen.getByText('0 / 300 Zeichen')).toBeInTheDocument();
  });

  it('speichert eine neue Version bedingt über expected_version, mit Notiz, Begründung unverändert', async () => {
    const { fetchMock, user } = await openSettings();
    const input = rule('R-SEV-01').getByRole('textbox', { name: /Mindestwert/ });
    await user.clear(input);
    await user.type(input, '2,5');
    await user.click(rule('R-OFF-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, '  Schwelle gesenkt  ');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));

    expect(await screen.findByTestId('rules-saved')).toHaveTextContent(
      'Neue Regelversion rules-v2 ist aktiv.',
    );
    const [call] = putCalls(fetchMock, RULES_URL);
    expect(putCalls(fetchMock, RULES_URL)).toHaveLength(1);
    expect(call?.[1]?.headers).toMatchObject({ 'X-Requested-With': 'fetch' });
    const body = bodyOf(call?.[1]) as {
      expected_version: string;
      change_note: string;
      rules: {
        rules: {
          id: string;
          enabled: boolean;
          params: Record<string, number>;
          rationale?: unknown;
        }[];
        noise: unknown;
      };
    };
    expect(body.expected_version).toBe('rules-v1');
    expect(body.change_note).toBe('Schwelle gesenkt');
    expect(body.rules.rules.map((entry) => entry.id)).toEqual([
      'R-SEV-01',
      'R-URG-01',
      'R-OFF-01',
      'R-DLT-01',
    ]);
    expect(body.rules.rules[0]?.params).toEqual({ min_value: 2.5 });
    expect(body.rules.rules[0]?.rationale).toEqual({
      cs: 'Demonstrační práh, klinicky neověřeno.',
      en: 'Demo threshold, not clinically validated.',
    });
    expect(body.rules.rules[2]?.enabled).toBe(true);
    expect(body.rules.rules[1]?.enabled).toBe(true);
    expect(body.rules.noise).toEqual({
      notify_levels: ['red'],
      cooldown_hours: 24,
      digest_levels: ['yellow', 'grey'],
    });
    expect(body.rules).not.toHaveProperty('version');
  });

  it('ändert Sperrzeit und Sofortbenachrichtigungsstufen der Rauschbremse', async () => {
    const { fetchMock, user } = await openSettings();
    const noise = within(screen.getByTestId('noise'));
    const cooldown = noise.getByRole('textbox', { name: /Sperrzeit/ });
    await user.clear(cooldown);
    await user.type(cooldown, '12');
    await user.click(noise.getByRole('checkbox', { name: 'Gelb' }));
    await writeNote(user, 'Rauschbremse');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    await screen.findByTestId('rules-saved');
    const body = bodyOf(putCalls(fetchMock, RULES_URL)[0]?.[1]) as {
      rules: { noise: { cooldown_hours: number; notify_levels: string[] } };
    };
    expect(body.rules.noise.cooldown_hours).toBe(12);
    expect(body.rules.noise.notify_levels.sort()).toEqual(['red', 'yellow']);
  });

  it('verlangt eine Änderungsnotiz und sendet ohne sie nichts', async () => {
    const { fetchMock, user } = await openSettings();
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Bitte geben Sie eine Änderungsnotiz an.',
    );
    expect(putCalls(fetchMock, RULES_URL)).toHaveLength(0);
  });

  it('prüft Zahlen vor dem Senden und markiert das Feld', async () => {
    const { fetchMock, user } = await openSettings();
    const input = rule('R-SEV-01').getByRole('textbox', { name: /Mindestwert/ });
    await user.clear(input);
    await user.type(input, 'abc');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(
      rule('R-SEV-01').getByText('Bitte eine Zahl eingeben (Dezimalkomma erlaubt).'),
    ).toBeInTheDocument();
    await writeNote(user, 'x');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(
      screen.getByText('Bitte korrigieren Sie die markierten Zahlenfelder.'),
    ).toBeInTheDocument();
    expect(putCalls(fetchMock, RULES_URL)).toHaveLength(0);
  });

  it('verweigert das Deaktivieren der letzten roten Regel schon vor dem Senden', async () => {
    const { fetchMock, user } = await openSettings();
    await user.click(rule('R-SEV-01').getByRole('checkbox', { name: 'aktiv' }));
    await user.click(rule('R-URG-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'alle rot aus');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(
      await screen.findByText('Mindestens eine aktive Regel der Stufe Rot ist erforderlich.'),
    ).toBeInTheDocument();
    expect(putCalls(fetchMock, RULES_URL)).toHaveLength(0);
  });

  it('zeigt die Serverentscheidung no_red_rule (422) verständlich', async () => {
    const { user } = await openSettings({
      rulesPut: () => jsonResponse(ERROR_BODY('no_red_rule'), 422),
    });
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Mindestens eine aktive Regel der Stufe Rot ist erforderlich.',
    );
  });

  it('zeigt no_red_notification (422) an der Rauschbremse', async () => {
    const { user } = await openSettings({
      rulesPut: () =>
        jsonResponse(
          {
            ...ERROR_BODY('no_red_notification'),
            field_errors: [
              {
                field: 'rules.noise.notify_levels',
                code: 'no_red_notification',
                message: 'red is required',
              },
            ],
          },
          422,
        ),
    });
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    const error = await within(screen.getByTestId('noise')).findByTestId('noise-error');
    expect(error).toHaveTextContent('Rote Meldungen müssen sofort benachrichtigt werden');
    // nicht zusätzlich als allgemeine Meldung unten
    expect(screen.getAllByRole('alert')).toHaveLength(1);
  });

  it('prüft vorab, dass die rote Sofortbenachrichtigung angehakt bleibt', async () => {
    const { fetchMock, user } = await openSettings();
    await user.click(within(screen.getByTestId('noise')).getByRole('checkbox', { name: 'Rot' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(await screen.findByTestId('noise-error')).toBeInTheDocument();
    expect(putCalls(fetchMock, RULES_URL)).toHaveLength(0);
  });

  it('ordnet 422-Feldfehler (rules.rules[<i>].params.<name>, wie vom Server) der Regelzeile zu', async () => {
    const { user } = await openSettings({
      rulesPut: () =>
        jsonResponse(
          {
            ...ERROR_BODY('validation_failed'),
            field_errors: [
              {
                field: 'rules.rules[2].params.min_value',
                code: 'out_of_range',
                message: 'out of range',
              },
            ],
          },
          422,
        ),
    });
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(await rule('R-OFF-01').findByTestId('rule-errors')).toHaveTextContent('out of range');
  });

  it('ordnet 422-Feldfehler (rules.rules.<i>…) der Regelzeile zu', async () => {
    const { user } = await openSettings({
      rulesPut: () =>
        jsonResponse(
          {
            ...ERROR_BODY('validation_failed'),
            field_errors: [
              {
                field: 'rules.rules.3.params.min_delta',
                code: 'out_of_range',
                message: 'must be at most 4',
              },
              { field: 'change_note', code: 'too_long', message: 'note too long' },
            ],
          },
          422,
        ),
    });
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    const errors = await rule('R-DLT-01').findByTestId('rule-errors');
    expect(errors).toHaveTextContent('Hinweis des Servers: must be at most 4');
    expect(rule('R-SEV-01').queryByTestId('rule-errors')).not.toBeInTheDocument();
    expect(
      screen.getAllByRole('alert').some((alert) => alert.textContent?.includes('note too long')),
    ).toBe(true);
  });

  it('erklärt 409 version_conflict und bietet „Neu laden“ statt erneutem Speichern', async () => {
    let configCalls = 0;
    const { fetchMock, user } = await openSettings({
      config: () => {
        configCalls += 1;
        return jsonResponse(CONFIG);
      },
      rulesPut: () => jsonResponse(ERROR_BODY('version_conflict'), 409),
    });
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Die Konfiguration wurde inzwischen geändert.',
    );
    expect(
      screen.queryByRole('button', { name: 'Neue Regelversion speichern' }),
    ).not.toBeInTheDocument();
    const before = configCalls;
    await user.click(screen.getByRole('button', { name: 'Neu laden' }));
    await vi.waitFor(() => expect(configCalls).toBeGreaterThan(before));
    expect(putCalls(fetchMock, RULES_URL)).toHaveLength(1);
  });

  it.each([
    [403, 'forbidden', 'Nur die Administration darf die Konfiguration ändern.'],
    [500, 'internal', 'Das Speichern hat nicht geklappt.'],
  ])('zeigt bei Status %i eine verständliche Meldung', async (status, code, text) => {
    const { user } = await openSettings({ rulesPut: () => jsonResponse(ERROR_BODY(code), status) });
    await user.click(rule('R-DLT-01').getByRole('checkbox', { name: 'aktiv' }));
    await writeNote(user, 'Test');
    await user.click(screen.getByRole('button', { name: 'Neue Regelversion speichern' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(text);
  });
});

describe('Einstellungen: Bericht (Administration)', () => {
  it('speichert Abschnitte und Zeitraum als neue Berichtsversion', async () => {
    const { fetchMock, user } = await openSettings();
    const report = within(screen.getByTestId('report-settings'));
    expect(report.getAllByRole('checkbox')).toHaveLength(8);
    expect(report.getByRole('button', { name: 'Neue Berichtsversion speichern' })).toBeDisabled();
    await user.click(report.getByRole('checkbox', { name: 'Audit-Auszug' }));
    await user.selectOptions(report.getByRole('combobox', { name: 'Zeitraum' }), 'days_14');
    await user.click(report.getByRole('button', { name: 'Neue Berichtsversion speichern' }));

    expect(await report.findByTestId('report-saved')).toHaveTextContent(
      'Neue Berichtsversion report-v2 ist aktiv.',
    );
    const body = bodyOf(putCalls(fetchMock, REPORT_URL)[0]?.[1]) as {
      expected_version: string;
      report: { since: string; sections: string[] };
    };
    expect(body.expected_version).toBe('report-v1');
    expect(body.report.since).toBe('days_14');
    expect(body.report.sections).toEqual([
      'summary',
      'alerts',
      'timeline',
      'since_last_visit',
      'therapy',
      'assessments',
      'missing_data',
    ]);
  });

  it('meldet 409 beim Bericht verständlich', async () => {
    const { user } = await openSettings({
      reportPut: () => jsonResponse(ERROR_BODY('version_conflict'), 409),
    });
    const report = within(screen.getByTestId('report-settings'));
    await user.click(report.getByRole('checkbox', { name: 'Therapie' }));
    await user.click(report.getByRole('button', { name: 'Neue Berichtsversion speichern' }));
    expect(await report.findByRole('alert')).toHaveTextContent(
      'Die Konfiguration wurde inzwischen geändert.',
    );
  });
});
