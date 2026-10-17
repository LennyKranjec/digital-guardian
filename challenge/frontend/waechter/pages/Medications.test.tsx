import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import i18n from '../../../../platform/frontend/src/shared/i18n';
import { jsonResponse, renderApp } from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import { findForbiddenClinician } from '../i18n/forbidden';
import { ERROR_BODY, callUrl, serve, setViewport } from '../testing/cockpit-server';
import { ANCHOR, CLINICIAN, PATIENT } from '../testing/fixtures';
import { FOLINATE, OXALIPLATIN, SUKL_ONLY } from '../testing/medication-fixtures';

const searchCalls = (fetchMock: ReturnType<typeof serve>) =>
  fetchMock.mock.calls
    .map(([input]) => callUrl(input))
    .filter((url) => url.includes('/waechter/medications?q='));

function open(options: Parameters<typeof serve>[0] = {}, path = '/clinic/medications') {
  const fetchMock = serve(options);
  const user = userEvent.setup();
  renderApp(path);
  return { fetchMock, user };
}

const box = () =>
  screen.findByRole('searchbox', { name: 'Arzneimittel – Name, SÚKL-Code oder ATC' });

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

describe('Arzneimittelsuche (F-12)', () => {
  it('zeigt Seite mit genau einer h1, beschriftetem Suchfeld, Hinweis und Reichweiten-Notiz', async () => {
    open();
    expect(await screen.findByRole('heading', { level: 1, name: 'Arzneimittel' })).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const field = await box();
    expect(field).toHaveAccessibleDescription(/Mindestens 2 Zeichen/);
    expect(screen.getByTestId('medication-idle')).toBeVisible();
    expect(screen.getByTestId('medication-note')).toHaveTextContent(
      'kein vollständiges SÚKL-Register',
    );
    expect(screen.getByRole('button', { name: 'Suchen' })).toBeVisible();
  });

  it('sucht nach Namen mit Pause (kein Request pro Taste) und zeigt Treffer mit allen Angaben', async () => {
    const { fetchMock, user } = open();
    await user.type(await box(), 'oxali');
    const [card] = await screen.findAllByTestId('medication-card');
    // eine Anfrage für den fertigen Suchtext (Debounce), nicht je Buchstabe
    expect(searchCalls(fetchMock)).toEqual(['/api/v1/waechter/medications?q=oxali']);

    const hit = within(card as HTMLElement);
    expect(
      hit.getByRole('heading', { level: 2, name: 'Oxaliplatin Accord 5 mg/ml' }),
    ).toBeVisible();
    expect(hit.getByTestId('medication-inn')).toHaveTextContent('Wirkstoff: oxaliplatin');
    expect(hit.getByTestId('medication-sukl')).toHaveTextContent('0239968');
    expect(hit.getByTestId('medication-atc')).toHaveTextContent('L01XA03');
    expect(hit.getByTestId('medication-match')).toHaveTextContent('Gefunden über: Name');
    expect(hit.getByTestId('medication-patients')).toHaveTextContent('3');
    // Regime mit Fragebogen-Symptomen (lokalisierte Etiketten aus der Konfiguration, sonst der Schlüssel)
    expect(hit.getByTestId('medication-regimens')).toHaveTextContent(
      'FOLFOX (oxaliplatin, fluorouracil)',
    );
    expect(hit.getByTestId('medication-regimens')).toHaveTextContent('Fragebogen-Symptome: Nausea');
    expect(screen.getByTestId('medication-count')).toHaveTextContent('Treffer: 2');
    expect(findForbiddenClinician(screen.getByTestId('medication-results').textContent)).toEqual(
      [],
    );
  });

  it.each([
    ['0239968', 'sukl_code', 'SÚKL-Code'],
    ['L01XA', 'atc', 'ATC-Code'],
    ['leukovorin', 'synonym', 'Synonym'],
  ] as const)('sucht „%s“ und zeigt „gefunden über“ %s', async (text, match, label) => {
    const { fetchMock, user } = open({
      medications: () => jsonResponse([{ ...OXALIPLATIN, match }]),
    });
    await user.type(await box(), text);
    const found = await screen.findByTestId('medication-match');
    expect(found).toHaveAttribute('data-match', match);
    expect(found).toHaveTextContent(`Gefunden über: ${label}`);
    expect(searchCalls(fetchMock)).toEqual([`/api/v1/waechter/medications?q=${text}`]);
  });

  it('sucht mit Enter sofort und ändert die Adresse nicht auf den Teilstand', async () => {
    const { fetchMock, user } = open();
    await user.type(await box(), 'xeloda{Enter}');
    await screen.findAllByTestId('medication-card');
    expect(searchCalls(fetchMock)).toEqual(['/api/v1/waechter/medications?q=xeloda']);
  });

  it('sucht erst ab 2 Zeichen: bei einem Zeichen kein Request, der Hinweis bleibt', async () => {
    const { fetchMock, user } = open();
    await user.type(await box(), 'o');
    await new Promise((resolve) => setTimeout(resolve, 400)); // länger als die Pause
    expect(searchCalls(fetchMock)).toEqual([]);
    expect(screen.getByTestId('medication-idle')).toBeVisible();
  });

  it('startet die Suche aus der Adresse (?q=), z. B. vom Link im Cockpit-Kopf', async () => {
    const { fetchMock } = open({}, '/clinic/medications?q=oxaliplatin');
    expect((await screen.findAllByTestId('medication-card'))[0]).toBeVisible();
    expect(await box()).toHaveValue('oxaliplatin');
    expect(searchCalls(fetchMock)).toEqual(['/api/v1/waechter/medications?q=oxaliplatin']);
  });

  it('zeigt bei keinem Treffer den Leerzustand mit dem Suchtext', async () => {
    const { user } = open();
    await user.type(await box(), 'nix');
    expect(await screen.findByTestId('medication-empty')).toHaveTextContent(
      'Zu „nix“ wurde nichts gefunden.',
    );
    expect(screen.queryByTestId('medication-card')).toBeNull();
    expect(screen.getByTestId('medication-empty-sukl')).toHaveTextContent(
      'Kuratiert sind nur die Arzneimittel der Demo-Regime; die SÚKL-Datenbank wurde ebenfalls durchsucht.',
    );
  });

  it('T-33: kennzeichnet SÚKL-Treffer „Nur SÚKL-Datenbank, kein Therapieprofil“ hinter den kuratierten', async () => {
    const { user } = open({ medications: () => jsonResponse([OXALIPLATIN, SUKL_ONLY]) });
    await user.type(await box(), 'paralen');
    const cards = await screen.findAllByTestId('medication-card');
    expect(cards.map((card) => card.dataset.medication)).toEqual([
      'MED-OXALIPLATIN-ACCORD',
      'SUKL-0000123',
    ]);
    expect(within(cards[0]!).queryByTestId('medication-sukl-only')).toBeNull();
    const sukl = within(cards[1]!);
    expect(sukl.getByTestId('medication-sukl-only')).toHaveTextContent(
      'Nur SÚKL-Datenbank, kein Therapieprofil',
    );
    expect(sukl.getByTestId('medication-sukl-strength')).toHaveTextContent('500MG');
    expect(sukl.getByTestId('medication-sukl-holder')).toHaveTextContent('Testfirma');
    expect(sukl.queryByTestId('medication-patients')).toBeNull();
    expect(sukl.queryByRole('region', { name: 'Therapieschemata' })).toBeNull();
  });

  it.each([
    ['cs', 'Pouze databáze SÚKL, bez terapeutického profilu'],
    ['en', 'SÚKL database only, no therapy profile'],
  ])('T-33: SÚKL-Hinweis übersetzt (%s)', async (lang, text) => {
    await i18n.changeLanguage(lang);
    open({ medications: () => jsonResponse([SUKL_ONLY]) }, '/clinic/medications?q=paralen');
    expect(await screen.findByTestId('medication-sukl-only')).toHaveTextContent(text);
  });

  it('zeigt bei 422 einen verständlichen Hinweis zur Länge (nicht den Rohfehler)', async () => {
    const { user } = open({
      medications: () => jsonResponse(ERROR_BODY('validation_error'), 422),
    });
    await user.type(await box(), 'ab');
    const alert = await screen.findByTestId('medication-invalid');
    expect(alert).toHaveTextContent('Bitte 2 bis 60 Zeichen eingeben.');
    expect(alert).not.toHaveTextContent('validation_error');
  });

  it('zeigt bei einem Serverfehler eine Meldung mit „Erneut versuchen“', async () => {
    let attempt = 0;
    const { user } = open({
      medications: () => {
        attempt += 1;
        return attempt === 1 ? jsonResponse(ERROR_BODY('boom'), 500) : jsonResponse([OXALIPLATIN]);
      },
    });
    await user.type(await box(), 'ox{Enter}');
    const error = await screen.findByTestId('medication-error');
    await user.click(within(error).getByRole('button'));
    expect(await screen.findByTestId('medication-card')).toBeVisible();
  });

  it('zeigt bei 403 „Kein Zugriff“ (Patientin hat keinen Zugriff)', async () => {
    const { user } = open({
      medications: () => jsonResponse(ERROR_BODY('forbidden'), 403),
    });
    await user.type(await box(), 'ox{Enter}');
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('verlinkt die SPC nur mit http(s) im neuen Tab (rel noopener) und zeigt Status Entwurf', async () => {
    const { user } = open({ medications: () => jsonResponse([OXALIPLATIN, FOLINATE]) });
    await user.type(await box(), 'fol{Enter}');
    const cards = await screen.findAllByTestId('medication-card');
    const link = within(cards[0] as HTMLElement).getByRole('link', {
      name: /Oxaliplatin Accord – SPC \(SÚKL\)/,
    });
    expect(link).toHaveAttribute('href', 'https://prehledy.sukl.cz/spc-oxaliplatin');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(within(cards[0] as HTMLElement).getByTestId('medication-status')).toHaveTextContent(
      'geprüft',
    );

    const second = within(cards[1] as HTMLElement);
    expect(second.getByTestId('medication-status')).toHaveTextContent('Entwurf (nicht geprüft)');
    expect(second.getByTestId('medication-status')).toHaveAttribute('data-status', 'draft');
    expect(second.queryByRole('link', { name: /Ohne Link/ })).toBeNull(); // kein javascript:-Link
    expect(second.getByTestId('medication-spc')).toHaveTextContent('Ohne Link');
    expect(second.getByTestId('medication-sukl')).toHaveTextContent('–'); // ohne SÚKL-Code
    expect(second.getByTestId('medication-regimens')).toHaveTextContent('unknown_symptom'); // Schlüssel als Rückfall
  });

  it('verlinkt jeden Treffer auf die Detailansicht', async () => {
    const { user } = open();
    await user.type(await box(), 'ox{Enter}');
    const card = await screen.findAllByTestId('medication-card');
    expect(
      within(card[0] as HTMLElement).getByRole('link', { name: 'Oxaliplatin Accord 5 mg/ml' }),
    ).toHaveAttribute('href', '/clinic/medications/MED-OXALIPLATIN-ACCORD');
  });

  it('erreicht die Seite über die Navigation (Eintrag „Arzneimittel“, nur Klinikrollen) und den Link auf der Arbeitsliste', async () => {
    const { user } = open({}, '/clinic');
    const link = await screen.findByTestId('medications-link');
    expect(link).toHaveTextContent('Arzneimittel');
    expect(link).toHaveAttribute('href', '/clinic/medications');
    const nav = screen.getByRole('navigation', { name: 'Hauptnavigation' });
    expect(await within(nav).findByRole('link', { name: 'Arzneimittel' })).toHaveAttribute(
      'href',
      '/clinic/medications',
    );
    await user.click(link);
    expect(await screen.findByRole('heading', { level: 1, name: 'Arzneimittel' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Zur Arbeitsliste' })).toHaveAttribute(
      'href',
      '/clinic',
    );
  });

  it('verwehrt der Patientin die Seite (Navigationshilfe)', async () => {
    open({ me: PATIENT });
    expect(await screen.findByText('Kein Zugriff')).toBeInTheDocument();
  });

  it('übersetzt Seite und Treffer (en) ohne Rohschlüssel', async () => {
    await i18n.changeLanguage('en');
    const { user } = open();
    await user.type(
      await screen.findByRole('searchbox', { name: 'Medicine – name, SÚKL code or ATC' }),
      'ox{Enter}',
    );
    const card = await screen.findAllByTestId('medication-card');
    expect(within(card[0] as HTMLElement).getByTestId('medication-match')).toHaveTextContent(
      'Found by: name',
    );
    expect(document.body.textContent).not.toMatch(/\bwaechter\.[a-z]+\.[a-zA-Z.]+/);
  });
});

describe('Arzneimittel-Detailansicht (F-12)', () => {
  it('zeigt Name als h1, alle Angaben ohne „gefunden über“ und Zurück zur Suche', async () => {
    open({}, '/clinic/medications/MED-OXALIPLATIN-ACCORD');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Oxaliplatin Accord 5 mg/ml' }),
    ).toBeVisible();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const card = within(await screen.findByTestId('medication-card'));
    expect(card.getByTestId('medication-sukl')).toHaveTextContent('0239968');
    expect(card.queryByTestId('medication-match')).toBeNull();
    expect(card.queryByRole('link', { name: 'Oxaliplatin Accord 5 mg/ml' })).toBeNull(); // kein Selbstlink
    expect(screen.getByRole('link', { name: 'Zurück zur Suche' })).toHaveAttribute(
      'href',
      '/clinic/medications',
    );
    expect(screen.getByTestId('medication-note')).toBeVisible();
  });

  it('zeigt bei unbekannter Kennung „nicht gefunden“ mit Weg zurück', async () => {
    open({}, '/clinic/medications/MED-GIBTS-NICHT');
    await waitFor(() => expect(screen.queryByTestId('medication-card')).toBeNull());
    expect(await screen.findAllByRole('link', { name: 'Zurück zur Suche' })).not.toHaveLength(0);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
  });
});

describe('Cockpit-Kopf: Wirkstoffe als Links (F-12)', () => {
  it('verlinkt jeden Wirkstoff auf die Suche nach seinem Namen (S5: nur in „Weitere Angaben“)', async () => {
    const user = userEvent.setup();
    serve({ me: CLINICIAN });
    renderApp('/clinic/patients/pat-1');
    const header = within(await screen.findByTestId('cockpit-header'));
    await user.click(header.getByText('Mehr Angaben'));
    const link = header.getByRole('link', { name: 'Wirkstoff X (L01XX01)' });
    expect(link).toHaveAttribute('href', '/clinic/medications?q=Wirkstoff%20X');
    expect(link.className).toContain('min-h-11');
  });
});
