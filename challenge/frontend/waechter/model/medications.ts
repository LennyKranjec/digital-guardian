import { localized, type Lang, type ConfigBundle, type Medication } from '../api/client';

/**
 * Reine Logik der Arzneimittelsuche (keine UI, keine Bewertung): wann gesucht wird, wie Symptomschlüssel
 * zu Etiketten werden und welche Links erlaubt sind. Treffer, Reihenfolge und „gefunden über“ kommen
 * vom Server; das Arzneimittelverzeichnis dient nur der Identifikation (triage.md §8).
 */

export const MIN_QUERY_LENGTH = 2;
export const MAX_QUERY_LENGTH = 60;
export const SEARCH_DEBOUNCE_MS = 250;

/** Suchtext für die Anfrage: Ränder weg, Mehrfach-Leerzeichen zu einem. */
export function cleanQuery(raw: string): string {
  return raw.trim().replace(/\s+/g, ' ');
}

/** Gesucht wird erst ab 2 Zeichen (kürzer ⇒ der Server antwortet mit 422). */
export function canSearch(raw: string): boolean {
  return cleanQuery(raw).length >= MIN_QUERY_LENGTH;
}

/** Nur http(s)-Links zu SPC-Quellen (kein javascript:). */
export function spcUrl(url: string | null | undefined): string | null {
  const value = (url ?? '').trim();
  return /^https?:\/\//i.test(value) ? value : null;
}

/** Symptomschlüssel eines Regimes als lokalisierte Etiketten (Konfiguration), sonst der Schlüssel. */
export function symptomLabels(
  keys: readonly string[] | null | undefined,
  config: Pick<ConfigBundle, 'items'> | undefined,
  lang: Lang,
): string[] {
  return (keys ?? []).map(
    (key) =>
      localized(config?.items.items.find((item) => item.symptom_key === key)?.label, lang) || key,
  );
}

/** Name zum Anzeigen: Handelsname, sonst Wirkstoff. */
export function displayName(medication: Pick<Medication, 'trade_name' | 'inn'>): string {
  return medication.trade_name?.trim() || medication.inn;
}

/** T-33: Treffer nur aus der SÚKL-Datenbank (kein kuratiertes Therapieprofil). */
export function isSuklOnly(medication: Pick<Medication, 'status'>): boolean {
  return medication.status === 'sukl_only';
}

/** Link vom Cockpit-Kopf auf die Suche nach einem Wirkstoffnamen. */
export function medicationSearchPath(name: string): string {
  return `/clinic/medications?q=${encodeURIComponent(cleanQuery(name))}`;
}
