import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pluginApi, resetRegistry } from '../../../../platform/frontend/src/registry';
import {
  defaultApiResponse,
  jsonResponse,
  mockFetch,
  renderApp,
} from '../../../../platform/frontend/src/test/render';
import { register } from '../../plugin';
import type { WorklistRow } from '../api/client';
import { parseEnrollment, serverFieldErrors } from '../model/enrollment';
import { CONFIG, metaBody, overviewForRow } from '../testing/cockpit-fixtures';
import { stripLang } from '../testing/cockpit-server';
import { ANCHOR, CLINICIAN, WORKLIST } from '../testing/fixtures';

const NEW_ROW: WorklistRow = {
  ...(WORKLIST[0] as WorklistRow),
  patient_id: 'p-new',
  pseudonym: 'SYN-0008',
};

/** Aufgerufene URLs (ohne Sprachparameter), um die Navigation ins Cockpit zu prüfen. */
let visited: string[] = [];

function serve(enroll: (body: unknown) => Response) {
  return mockFetch((rawUrl, init) => {
    visited.push(stripLang(rawUrl));
    const url = stripLang(rawUrl);
    if (url.endsWith('/auth/me')) return jsonResponse(CLINICIAN);
    if (url.endsWith('/meta')) return jsonResponse(metaBody());
    if (url.endsWith('/waechter/config')) return jsonResponse(CONFIG);
    if (url.endsWith('/waechter/patients') && init?.method === 'POST') {
      return enroll(JSON.parse(typeof init.body === 'string' ? init.body : '{}'));
    }
    if (url.endsWith('/waechter/patients')) return jsonResponse(WORKLIST);
    if (url.endsWith('/waechter/patients/p-new/overview')) {
      return jsonResponse(overviewForRow(NEW_ROW));
    }
    if (url.endsWith('/waechter/notifications')) return jsonResponse([]);
    return defaultApiResponse(url);
  });
}

beforeEach(() => {
  visited = [];
  register(pluginApi);
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

describe('T-34 Einschreibung: Formular', () => {
  it('ist aus der Arbeitsliste erreichbar', async () => {
    serve(() => jsonResponse({}, 500));
    renderApp('/clinic');
    const link = await screen.findByTestId('enroll-link');
    expect(link.getAttribute('href')).toBe('/clinic/patients/new');
  });

  it('rendert beschriftete Felder und die Regime aus /config', async () => {
    serve(() => jsonResponse({}, 500));
    renderApp('/clinic/patients/new');
    await screen.findByTestId('enroll-form');
    expect(screen.getByLabelText('ICD-10-Code (optional)')).toBeTruthy();
    expect(screen.getByLabelText('Beginn des Zyklus')).toHaveProperty('value', '2026-10-17');
    expect(screen.getByLabelText('Sprache der Patientin')).toBeTruthy();
    const regimen = screen.getByLabelText('Therapieregime');
    const options = Array.from(regimen.querySelectorAll('option')).map((o) => o.value);
    expect(options).toContain('FOLFOX');
  });

  it('sendet den Body und navigiert ins Cockpit der neuen Patientin', async () => {
    const bodies: unknown[] = [];
    serve((body) => {
      bodies.push(body);
      return jsonResponse({ patient_id: 'p-new', pseudonym: 'SYN-0008' }, 201);
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/new');
    await screen.findByTestId('enroll-form');
    await user.type(screen.getByLabelText('ICD-10-Code (optional)'), 'c50.9');
    await user.selectOptions(screen.getByLabelText('Therapieregime'), 'FOLFOX');
    await user.click(screen.getByTestId('enroll-submit'));
    await vi.waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      diagnosis_code: 'C50.9',
      regimen_id: 'FOLFOX',
      cycle_start: '2026-10-17',
    });
    expect(typeof (bodies[0] as { client_request_id: unknown }).client_request_id).toBe('string');
    await vi.waitFor(() =>
      expect(visited.some((url) => url.endsWith('/patients/p-new/overview'))).toBe(true),
    );
  });

  it('zeigt Feldfehler ohne Request, wenn kein Regime gewählt ist', async () => {
    const bodies: unknown[] = [];
    serve((body) => {
      bodies.push(body);
      return jsonResponse({}, 500);
    });
    const user = userEvent.setup();
    renderApp('/clinic/patients/new');
    await screen.findByTestId('enroll-form');
    await user.click(screen.getByTestId('enroll-submit'));
    expect(await screen.findByText('Bitte ein Regime wählen.')).toBeTruthy();
    expect(bodies).toHaveLength(0);
  });

  it('zeigt Serverfeldfehler (422) am Feld', async () => {
    serve(() =>
      jsonResponse(
        {
          code: 'validation_failed',
          message: 'x',
          field_errors: [{ field: 'cycle_start', code: 'too_far_in_future', message: 'x' }],
        },
        422,
      ),
    );
    const user = userEvent.setup();
    renderApp('/clinic/patients/new');
    await screen.findByTestId('enroll-form');
    await user.selectOptions(screen.getByLabelText('Therapieregime'), 'FOLFOX');
    await user.click(screen.getByTestId('enroll-submit'));
    expect(
      await screen.findByText('Der Zyklusbeginn darf höchstens 30 Tage in der Zukunft liegen.'),
    ).toBeTruthy();
  });
});

describe('T-34 Einschreibung: Modell', () => {
  it('prüft ICD-10-Format und leert optionalen Code zu null', () => {
    const base = { regimen_id: 'FOLFOX', cycle_start: '2026-10-17', language: 'cs' as const };
    expect(parseEnrollment({ ...base, diagnosis_code: 'x1' })).toEqual({
      ok: false,
      errors: { diagnosis_code: 'icd10' },
    });
    const ok = parseEnrollment({ ...base, diagnosis_code: ' ' });
    expect(ok.ok && ok.body.diagnosis_code).toBeNull();
    expect(parseEnrollment({ ...base, diagnosis_code: '', cycle_start: '17.10.2026' })).toEqual({
      ok: false,
      errors: { cycle_start: 'date' },
    });
  });

  it('bildet Servercodes auf Textschlüssel ab', () => {
    expect(
      serverFieldErrors([
        { field: 'diagnosis_code', code: 'unknown_diagnosis_group' },
        { field: 'other', code: 'x' },
      ]),
    ).toEqual({ diagnosis_code: 'unknownGroup' });
  });
});
