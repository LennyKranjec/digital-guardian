import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { ALERT_YELLOW, OVERVIEW } from '../testing/cockpit-fixtures';
import { serve, setViewport } from '../testing/cockpit-server';
import { ANCHOR } from '../testing/fixtures';

const TRACKED = [
  { ctcae_term_id: 'CTCAE-NAUSEA', term_en: 'Nausea', label: 'Übelkeit' },
  { ctcae_term_id: 'CTCAE-FEVER', term_en: 'Fever', label: 'Fieber' },
];

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

async function openCockpit(overview: unknown) {
  serve({ overview: () => jsonResponse(overview) });
  const user = userEvent.setup();
  renderApp('/clinic/patients/pat-1');
  await screen.findByTestId('cockpit-header');
  return { user };
}

describe('T-25: beobachtete Symptome (CTCAE-Subraum) im Cockpit', () => {
  it('zeigt die Zeile einmal, einzeilig im Meldungsbereich (A3 INT-5: S5 1366×768)', async () => {
    await openCockpit({ ...OVERVIEW, tracked_symptoms: TRACKED });
    const alerts = within(screen.getByTestId('alerts-section'));
    const line = alerts.getByTestId('tracked-symptoms');
    expect(line).toHaveTextContent('Beobachtete Symptome: Übelkeit, Fieber');
    expect(line).toHaveClass('truncate');
    expect(line).toHaveAttribute('title', 'Beobachtete Symptome: Übelkeit, Fieber');
    expect(screen.queryByTestId('summary-tracked-symptoms')).toBeNull();
  });

  it('lässt die Zeile ohne Angaben weg (alter Server, keine Therapie)', async () => {
    await openCockpit({ ...OVERVIEW, tracked_symptoms: [] });
    expect(screen.queryByTestId('tracked-symptoms')).toBeNull();
    expect(screen.queryByTestId('summary-tracked-symptoms')).toBeNull();
  });

  it('funktioniert, wenn das Feld ganz fehlt (Vertrag vor v2.9)', async () => {
    await openCockpit(OVERVIEW);
    expect(screen.getByTestId('alerts-section')).toBeVisible();
    expect(screen.queryByTestId('tracked-symptoms')).toBeNull();
  });

  it.each([
    ['cs', 'Sledované příznaky: Übelkeit, Fieber'],
    ['en', 'Tracked symptoms: Übelkeit, Fieber'],
    ['de', 'Beobachtete Symptome: Übelkeit, Fieber'],
  ])('beschriftet die Zeile in %s', async (lang, expected) => {
    await i18n.changeLanguage(lang);
    await openCockpit({ ...OVERVIEW, tracked_symptoms: TRACKED });
    expect(screen.getByTestId('tracked-symptoms')).toHaveTextContent(expected);
  });
});

describe('T-25: Erklärung nennt die Begrenzung des Baseline-Fensters', () => {
  const limited = {
    ...ALERT_YELLOW,
    explanation: {
      ...ALERT_YELLOW.explanation,
      baseline_window: {
        from: '2026-10-14T09:00:00+02:00',
        to: '2026-10-16T09:00:00+02:00',
      },
      baseline_limit: {
        reason: 'regimen_change',
        regimen_id: 'FOLFOX',
        since: '2026-10-14T09:00:00+02:00',
      },
    },
  };

  it('zeigt Schema und Beginn, wenn der Therapiewechsel das Fenster gekürzt hat', async () => {
    const { user } = await openCockpit({
      ...OVERVIEW,
      open_alerts: [limited],
    });
    const card = within(screen.getAllByTestId('alert-card')[0] as HTMLElement);
    await user.click(card.getByRole('button', { name: 'Warum?' }));
    const note = card.getByTestId('baseline-limit');
    expect(note).toHaveTextContent('Therapiewechsel');
    expect(note).toHaveTextContent('FOLFOX');
    expect(note).toHaveTextContent('14.10.2026');
  });

  it('zeigt nichts, wenn das Fenster nicht begrenzt wurde', async () => {
    const { user } = await openCockpit({ ...OVERVIEW, open_alerts: [ALERT_YELLOW] });
    const card = within(screen.getAllByTestId('alert-card')[0] as HTMLElement);
    await user.click(card.getByRole('button', { name: 'Warum?' }));
    expect(card.queryByTestId('baseline-limit')).toBeNull();
  });
});
