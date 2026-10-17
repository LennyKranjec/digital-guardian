import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { newSubmissionId, type Due, type Escalation } from '../api/client';

/**
 * Reine Logik des adaptiven Check-ins (keine UI): Sitzungskennung im sessionStorage, Behandlung der
 * Fehlerantworten des Servers und Aufbereitung von Eskalation und Fälligkeit für die Anzeige.
 * Die Auswahl der nächsten Frage, der Stopp und jede Bewertung bleiben serverseitig (triage.md §3).
 */

export const SESSION_STORAGE_KEY = 'waechter.checkin.client_session_id';

function safeStorage(): Storage | undefined {
  try {
    return typeof window === 'undefined' ? undefined : window.sessionStorage;
  } catch {
    return undefined;
  }
}

/** Gespeicherte `client_session_id` (derselbe Wert nach Neuladen ⇒ Sitzung wird fortgesetzt). */
export function readClientSessionId(
  storage: Pick<Storage, 'getItem'> | undefined = safeStorage(),
): string | null {
  try {
    const value = storage?.getItem(SESSION_STORAGE_KEY);
    return value && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

export function writeClientSessionId(
  id: string,
  storage: Pick<Storage, 'setItem'> | undefined = safeStorage(),
): void {
  try {
    storage?.setItem(SESSION_STORAGE_KEY, id);
  } catch {
    // Speicher gesperrt (privates Fenster o. Ä.): die Sitzung läuft, nur ohne Fortsetzung nach Neuladen
  }
}

export function clearClientSessionId(
  storage: Pick<Storage, 'removeItem'> | undefined = safeStorage(),
): void {
  try {
    storage?.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // siehe oben
  }
}

export const SESSION_META_KEY = 'waechter.checkin.session';

/**
 * Was nach dem Stopp im sessionStorage bleibt (Vertrag v2.5, DR-029): nur Kennungen und ein Zeitpunkt,
 * nie Antworten, Beleg oder Texte. Beim nächsten Öffnen von /patient holt `GET /me/sessions/{id}` den Beleg.
 */
export interface SessionMeta {
  sessionId: string;
  closed: boolean;
  /** nächste Fälligkeit (ISO): danach gilt die beendete Sitzung nicht mehr als „aktuell“ */
  until: string | null;
}

export function readSessionMeta(
  storage: Pick<Storage, 'getItem'> | undefined = safeStorage(),
): SessionMeta | null {
  try {
    const raw = storage?.getItem(SESSION_META_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SessionMeta>;
    if (typeof parsed.sessionId !== 'string' || parsed.sessionId === '') return null;
    return {
      sessionId: parsed.sessionId,
      closed: parsed.closed === true,
      until: typeof parsed.until === 'string' ? parsed.until : null,
    };
  } catch {
    return null;
  }
}

export function writeSessionMeta(
  meta: SessionMeta,
  storage: Pick<Storage, 'setItem'> | undefined = safeStorage(),
): void {
  try {
    storage?.setItem(SESSION_META_KEY, JSON.stringify(meta));
  } catch {
    // Speicher gesperrt: ohne Fortsetzung nach Neuladen, die Sitzung läuft trotzdem
  }
}

export function clearSessionMeta(
  storage: Pick<Storage, 'removeItem'> | undefined = safeStorage(),
): void {
  try {
    storage?.removeItem(SESSION_META_KEY);
  } catch {
    // siehe oben
  }
}

/** Beendete Sitzung nach ihrer nächsten Fälligkeit nicht mehr als Beleg zeigen (nur mit bekannter Serverzeit). */
export function metaExpired(meta: SessionMeta, serverNow: Date | null): boolean {
  if (!meta.closed || !meta.until || !serverNow) return false;
  const until = new Date(meta.until);
  return !Number.isNaN(until.getTime()) && serverNow.getTime() >= until.getTime();
}

/** Vorhandene Kennung oder eine neue (wird sofort gespeichert). */
export function ensureClientSessionId(
  storage: Pick<Storage, 'getItem' | 'setItem'> | undefined = safeStorage(),
): string {
  const existing = readClientSessionId(storage);
  if (existing) return existing;
  const id = newSubmissionId();
  writeClientSessionId(id, storage);
  return id;
}

/** Was nach einem Fehler zu tun ist (Statuscodes und Codes laut openapi v2.0). */
export type SessionErrorAction =
  /** 409 not_current_question: dieselbe Kennung erneut senden ⇒ aktuelle Frage des Servers */
  | 'reload'
  /** 409 session_closed: Sitzung ist beendet ⇒ neue Kennung, neue Sitzung */
  | 'restart'
  /** 404/501 beim Start: Sitzungs-API nicht vorhanden ⇒ Vollformular als Rückfall */
  | 'fallback'
  | 'network'
  | 'forbidden'
  | 'invalid'
  | 'generic';

export function sessionErrorAction(
  error: unknown,
  phase: 'start' | 'answer' | 'resume',
): SessionErrorAction {
  if (!(error instanceof ApiClientError)) return 'generic';
  if (error.isNetwork) return 'network';
  if (error.status === 409) return error.code === 'session_closed' ? 'restart' : 'reload';
  // Beleg abrufen: unbekannte/fremde Sitzung (404) ⇒ vergessen und normal starten
  if (phase === 'resume' && error.status === 404) return 'restart';
  if (phase === 'start' && (error.status === 404 || error.status === 501)) return 'fallback';
  if (error.status === 401 || error.status === 403) return 'forbidden';
  if (error.status === 422) return 'invalid';
  return 'generic';
}

/** Platzhalter in eckigen Klammern („[Telefon folgt]“) werden Patientinnen nie angezeigt. */
export function hasPlaceholder(text: string | null | undefined): boolean {
  return /\[[^\]]*\]/.test(text ?? '');
}

export function visiblePhone(phone: string | null | undefined): string | null {
  const value = (phone ?? '').trim();
  return value === '' || hasPlaceholder(value) ? null : value;
}

/** Text ohne Platzhalter-Teile; leer, wenn nichts Lesbares übrig bleibt. */
export function visibleText(text: string | null | undefined): string {
  return (text ?? '')
    .replace(/\[[^\]]*\]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

export interface EscalationView {
  acute: boolean;
  /** Text ohne Platzhalter; leer ⇒ der Katalog liefert den Klinikwortlaut als Rückfall (nur akut) */
  text: string;
  phone: string | null;
}

export function escalationView(escalation: Escalation): EscalationView {
  return {
    acute: escalation.level === 'acute',
    text: visibleText(escalation.text),
    phone: visiblePhone(escalation.ambulance_phone),
  };
}

/** Nur http(s)-Links aus Quellen werden verlinkt (kein javascript:). */
export function safeUrl(url: string | null | undefined): string | null {
  const value = (url ?? '').trim();
  return /^https?:\/\//i.test(value) ? value : null;
}

/** „Frage x (höchstens y)“: `max` ist nur eine Obergrenze; x zählt die gerade angezeigte Frage. */
export function questionNumber(progress: { asked: number; max: number }): {
  current: number;
  max: number;
} {
  const current = progress.asked + 1;
  return { current, max: Math.max(progress.max, current) };
}

export interface DueView {
  overdue: boolean;
  /** ISO-Zeitpunkt der nächsten Fälligkeit, sofern bekannt */
  at: string | null;
}

export function dueView(due: Due | null | undefined): DueView | null {
  if (!due) return null;
  const at = due.next_due_at ?? null;
  const overdue = due.overdue === true;
  return at || overdue ? { overdue, at } : null;
}
