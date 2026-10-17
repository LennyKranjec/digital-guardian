import {
  defaultApiResponse,
  jsonResponse,
  mockFetch,
} from '../../../../platform/frontend/src/test/render';
import {
  ACKED_RED,
  ALERT_RED,
  ASSESSMENT_SAVED,
  AUDIT_ROWS,
  CONFIG,
  CONFIG_STATE,
  FHIR_BUNDLE,
  HISTORY_REPORT,
  HISTORY_RULES,
  NEW_SUMMARY,
  OVERVIEW,
  TEMPLATE,
  TIMELINE,
  factFor,
  metaBody,
} from './cockpit-fixtures';
import { CLINICIAN, WORKLIST } from './fixtures';
import { MEDICATIONS } from './medication-fixtures';
import { TRIAGE_RED, TRIAGE_RULE_CARD } from './triage-fixtures';

/** Entfernt `lang=xx` aus einer URL (das Backend lokalisiert danach; die Tests ordnen nach dem Pfad zu). */
export function stripLang(url: string): string {
  return url.replace(/([?&])lang=[a-z]{2}(&|$)/, (_match, lead: string, tail: string) =>
    tail === '&' ? lead : '',
  );
}

/** URL einer aufgezeichneten Anfrage ohne `lang`. */
export function callUrl(input: RequestInfo | URL): string {
  return stripLang(
    typeof input === 'string' ? input : input instanceof URL ? input.href : input.url,
  );
}

/** Wert des Parameters `lang` einer aufgezeichneten Anfrage (oder `null`). */
export function langOf(input: RequestInfo | URL): string | null {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  return /[?&]lang=([a-z]{2})/.exec(raw)?.[1] ?? null;
}

/** Gemockter Server für Cockpit und Verlauf der Patientin `pat-1`. */
export const BASE = '/api/v1/waechter/patients/pat-1';

export interface ServeOptions {
  me?: unknown;
  meta?: Record<string, unknown>;
  overview?: () => Response;
  fact?: (factId: string) => Response;
  summaryPost?: () => Response | Promise<Response>;
  /** Antwort auf `GET …/timeline?…`; erhält die vollständige URL */
  timeline?: (url: string) => Response;
  config?: () => Response;
  worklist?: () => Response;
  /** `GET …/config/history?kind=…`; Standard: Verlauf der Fixtures */
  history?: (kind: string) => Response;
  /** `PUT …/config/rules` und `…/config/report` (Körper als Objekt) */
  rulesPut?: (body: Record<string, unknown>) => Response;
  reportPut?: (body: Record<string, unknown>) => Response;
  /** `GET …/patients/pat-1/free-texts` (v2.9); Standard: keine Freitexte (Abschnitt bleibt verborgen) */
  freeTexts?: () => Response;
  /** `GET …/patients/pat-1/audit` */
  audit?: () => Response;
  /** `GET …/patients/pat-1/fhir` */
  fhir?: () => Response;
  /** `GET …/patients/pat-1/fhir?type=transaction` (v2.6); Standard: 200 mit Bundle */
  fhirTransaction?: () => Response;
  /** `POST …/patients/pat-1/fhir/push` (v2.6, nur admin); Standard: 200 sent */
  fhirPush?: () => Response;
  /** `POST …/alerts/{id}/acknowledge`; Standard: 200 mit quittierter Meldung */
  ack?: (alertId: string, body: Record<string, unknown>) => Response;
  /** `GET …/alerts/{id}` */
  alert?: (alertId: string) => Response;
  template?: () => Response;
  /** `GET …/patients/pat-1/triage?response_id=…` (v2.0); Standard: Rot mit Schild */
  triage?: (responseId: string | null) => Response;
  /** `GET …/medications?q=…` (v2.3); erhält den Suchtext; Standard: Treffer der Fixtures (leer bei „nix“) */
  medications?: (q: string) => Response;
  /** `GET …/medications/{id}`; Standard: Eintrag der Fixtures oder 404 */
  medication?: (id: string) => Response;
  /** `GET …/config/triage` (v2.0); Standard: Regelkarte der Fixtures */
  triageConfig?: () => Response;
  /** `POST …/assessments`; `attempt` zählt ab 1 (zum Auslösen von Fehlern bei der ersten Anfrage) */
  assessmentPost?: (body: Record<string, unknown>, attempt: number) => Response;
}

/** JSON-Körper einer gemockten Anfrage. */
export function bodyOf(init: RequestInit | undefined): Record<string, unknown> {
  return typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : {};
}

export function serve(options: ServeOptions = {}) {
  let assessmentAttempts = 0;
  return mockFetch((rawUrl, init) => {
    const url = stripLang(rawUrl);
    const ackMatch = /\/waechter\/alerts\/([^/]+)\/acknowledge$/.exec(url);
    if (ackMatch && init?.method === 'POST') {
      const id = decodeURIComponent(ackMatch[1] ?? '');
      return options.ack?.(id, bodyOf(init)) ?? jsonResponse({ ...ACKED_RED, alert_id: id });
    }
    const alertMatch = /\/waechter\/alerts\/([^/]+)$/.exec(url);
    if (alertMatch) {
      const id = decodeURIComponent(alertMatch[1] ?? '');
      return options.alert?.(id) ?? jsonResponse({ ...ALERT_RED, alert_id: id });
    }
    if (url === `${BASE}/assessment-template`) {
      return options.template?.() ?? jsonResponse(TEMPLATE);
    }
    if (url === `${BASE}/assessments` && init?.method === 'POST') {
      assessmentAttempts += 1;
      return (
        options.assessmentPost?.(bodyOf(init), assessmentAttempts) ??
        jsonResponse(ASSESSMENT_SAVED, 201)
      );
    }
    if (url === `${BASE}/triage` || url.startsWith(`${BASE}/triage?`)) {
      const responseId = /[?&]response_id=([^&]+)/.exec(url)?.[1] ?? null;
      return (
        options.triage?.(responseId ? decodeURIComponent(responseId) : null) ??
        jsonResponse(TRIAGE_RED)
      );
    }
    const medicationMatch = /\/waechter\/medications(?:\/([^/?]+))?(?:\?q=([^&]*))?$/.exec(url);
    if (medicationMatch) {
      const id = medicationMatch[1] ? decodeURIComponent(medicationMatch[1]) : null;
      if (id) {
        return (
          options.medication?.(id) ??
          (MEDICATIONS.find((entry) => entry.medication_id === id)
            ? jsonResponse(MEDICATIONS.find((entry) => entry.medication_id === id))
            : jsonResponse(ERROR_BODY('not_found'), 404))
        );
      }
      const q = decodeURIComponent((medicationMatch[2] ?? '').replace(/\+/g, ' '));
      return options.medications?.(q) ?? jsonResponse(MEDICATIONS.filter(() => q !== 'nix'));
    }
    if (url.endsWith('/waechter/config/triage')) {
      return options.triageConfig?.() ?? jsonResponse(TRIAGE_RULE_CARD);
    }
    if (url.endsWith('/auth/me')) return jsonResponse(options.me ?? CLINICIAN);
    if (url.endsWith('/meta')) return jsonResponse(options.meta ?? metaBody());
    if (url.endsWith('/waechter/notifications')) return jsonResponse([]);
    if (url.endsWith('/waechter/patients')) return options.worklist?.() ?? jsonResponse(WORKLIST);
    const historyMatch = /\/waechter\/config\/history\?kind=(rules|report)/.exec(url);
    if (historyMatch) {
      const kind = historyMatch[1] ?? 'rules';
      return (
        options.history?.(kind) ?? jsonResponse(kind === 'rules' ? HISTORY_RULES : HISTORY_REPORT)
      );
    }
    if (url.endsWith('/waechter/config/rules') && init?.method === 'PUT') {
      return options.rulesPut?.(bodyOf(init)) ?? jsonResponse(CONFIG_STATE);
    }
    if (url.endsWith('/waechter/config/report') && init?.method === 'PUT') {
      return (
        options.reportPut?.(bodyOf(init)) ?? jsonResponse({ ...CONFIG_STATE, version: 'report-v2' })
      );
    }
    if (url === `${BASE}/free-texts`) return options.freeTexts?.() ?? jsonResponse([]);
    if (url === `${BASE}/audit`) return options.audit?.() ?? jsonResponse(AUDIT_ROWS);
    if (url === `${BASE}/fhir?type=transaction`) {
      return (
        options.fhirTransaction?.() ??
        new Response(JSON.stringify({ resourceType: 'Bundle', type: 'transaction', entry: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/fhir+json' },
        })
      );
    }
    if (url === `${BASE}/fhir/push` && init?.method === 'POST') {
      return (
        options.fhirPush?.() ??
        jsonResponse({
          status: 'sent',
          http_status: 200,
          entries: 12,
          created: 9,
          updated: 3,
          errors: [],
        })
      );
    }
    if (url === `${BASE}/fhir`) {
      return (
        options.fhir?.() ??
        new Response(JSON.stringify(FHIR_BUNDLE), {
          status: 200,
          headers: { 'Content-Type': 'application/fhir+json' },
        })
      );
    }
    if (url.endsWith('/waechter/config')) return options.config?.() ?? jsonResponse(CONFIG);
    if (url === `${BASE}/overview`) return options.overview?.() ?? jsonResponse(OVERVIEW);
    if (url === `${BASE}/timeline` || url.startsWith(`${BASE}/timeline?`)) {
      return options.timeline?.(url) ?? jsonResponse(TIMELINE);
    }
    if (url === `${BASE}/summary` && init?.method === 'POST') {
      return options.summaryPost?.() ?? jsonResponse(NEW_SUMMARY, 201);
    }
    if (url.startsWith(`${BASE}/facts/`)) {
      const factId = decodeURIComponent(url.slice(`${BASE}/facts/`.length));
      return options.fact?.(factId) ?? jsonResponse(factFor(factId));
    }
    return defaultApiResponse(url);
  });
}

/** jsdom kennt keine Medienabfragen: Breite ≥ 768 px (Tabelle) oder schmal (Karten) vorgeben. */
export function setViewport(wide: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({
      matches: wide && query.includes('min-width: 768px'),
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

export const ERROR_BODY = (code: string) => ({ code, message: code, field_errors: [] });

export function timelineCalls(fetchMock: ReturnType<typeof serve>): string[] {
  return fetchMock.mock.calls
    .map(([input]) => (typeof input === 'string' ? input : ''))
    .filter((url) => stripLang(url).startsWith(`${BASE}/timeline`))
    .map(stripLang);
}
