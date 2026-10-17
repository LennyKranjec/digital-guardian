import type {
  AdviceFile,
  TriageDecision,
  TriageLevel,
  TriageProfile,
  TrafficLightLevel,
} from '../api/client';

/**
 * Reine Aufbereitung der Triage-Anzeige für die Ärztin (keine UI, keine Bewertung): Reihenfolge der
 * Begründungen, Stufe → Symbol, Kurzform der Hashes, Sortierung der Regelkarte, Zeilen der Tipp-Regeln.
 * Stufe, Pfade und Kontrafaktische kommen fertig vom Server; hier wird nichts berechnet oder geändert.
 */

const LEVEL_TO_LIGHT: Record<TriageLevel, TrafficLightLevel> = {
  RED: 'red',
  YELLOW: 'yellow',
  GREEN: 'green',
};

export const lightOf = (level: TriageLevel): TrafficLightLevel => LEVEL_TO_LIGHT[level];

const REASON_ORDER: Record<string, number> = { shield: 0, path: 1, leaf: 2, incomplete: 3 };

/** Schutzböden (Schloss) zuerst, dann Pfadbedingungen, dann Blatt und Unvollständigkeit; stabil. */
export function orderReasons<T extends { kind?: string | null }>(reasons: readonly T[]): T[] {
  return reasons
    .map((reason, index) => ({ reason, index }))
    .sort(
      (a, b) =>
        (REASON_ORDER[a.reason.kind ?? ''] ?? 4) - (REASON_ORDER[b.reason.kind ?? ''] ?? 4) ||
        a.index - b.index,
    )
    .map(({ reason }) => reason);
}

/** Spanne `level_lo`–`level_hi` nur, wenn sie von einer einzigen Stufe abweicht. */
export function hasSpan(decision: Pick<TriageDecision, 'level_lo' | 'level_hi'>): boolean {
  return decision.level_lo !== decision.level_hi;
}

/** Erste Zeichen eines Hashes (KB-Hash) – die Ärztin braucht eine wiedererkennbare Kurzform. */
export function shortHash(value: string, length = 8): string {
  return value.length > length ? value.slice(0, length) : value;
}

/** „Regelwerk: Platzhalter, klinisch nicht freigegeben“ gilt, solange der Server es nicht anders meldet. */
export function isPlaceholderStatus(status: string | null | undefined): boolean {
  return status === undefined || status === null || status === 'placeholder';
}

const COUNTERFACTUAL_ORDER = { lower: 0, raise: 1 } as const;

export function splitCounterfactuals(decision: TriageDecision): {
  lower: string[];
  raise: string[];
  /** Schild-Hinweise („Boden F_X verhindert Senkung“): eigener Eintrag, kein Satzteil */
  shields: string[];
} {
  const entries = [...(decision.counterfactuals ?? [])].sort(
    (a, b) => COUNTERFACTUAL_ORDER[a.direction] - COUNTERFACTUAL_ORDER[b.direction],
  );
  const changes = entries.filter((entry) => entry.kind !== 'shield');
  return {
    lower: changes.filter((entry) => entry.direction === 'lower').map((entry) => entry.text),
    raise: changes.filter((entry) => entry.direction === 'raise').map((entry) => entry.text),
    shields: entries.filter((entry) => entry.kind === 'shield').map((entry) => entry.text),
  };
}

/**
 * Prüfumfang der Verifikation (Vertrag v2.2 H4/v2.7): `exhaustive_*` = alle Punkte, `sampled_raw` = Stichprobe.
 * Unbekannt/fehlend ⇒ kein Anspruch auf Vollständigkeit.
 */
export type VerificationScope = 'exhaustive' | 'sampled' | 'unknown';

export function verificationScope(scope: string | null | undefined): VerificationScope {
  const value = (scope ?? '').toLowerCase();
  if (value.startsWith('exhaustive')) return 'exhaustive';
  if (value.startsWith('sampled')) return 'sampled';
  return 'unknown';
}

/** Haken nur bei sauberer Verifikation UND vollständigem Prüfumfang. */
export function verificationPassed(
  verification: NonNullable<TriageProfile['verification']>,
): boolean {
  return verificationClean(verification) && verificationScope(verification.scope) === 'exhaustive';
}

/** „Gefragt: x von y Fragen“ nur, wenn beide Zahlen vorliegen. */
export function askedOf(
  decision: Pick<TriageDecision, 'asked_questions' | 'full_questions'>,
): { asked: number; full: number } | null {
  const asked = decision.asked_questions;
  const full = decision.full_questions;
  return typeof asked === 'number' && typeof full === 'number' ? { asked, full } : null;
}

const LEVEL_RANK: Record<string, number> = { RED: 0, YELLOW: 1, GREEN: 2 };

/** Regeln rot zuerst, dann gelb, sonst unverändert (stabil). */
export function sortRulesRedFirst<T extends { level: string }>(rules: readonly T[]): T[] {
  return rules
    .map((rule, index) => ({ rule, index }))
    .sort(
      (a, b) =>
        (LEVEL_RANK[a.rule.level.toUpperCase()] ?? 3) -
          (LEVEL_RANK[b.rule.level.toUpperCase()] ?? 3) || a.index - b.index,
    )
    .map(({ rule }) => rule);
}

/** Verifikation ohne Befund: 0 Untertriage, 0 Obertriage, 0 Monotonie-Verletzungen. */
export function verificationClean(
  verification: NonNullable<TriageProfile['verification']>,
): boolean {
  return (
    verification.under === 0 && verification.over === 0 && verification.monotone_violations === 0
  );
}

export interface AdviceRuleRow {
  id: string;
  symptomKey: string;
  rangeMin: number;
  rangeMax: number;
  tipCount: number;
  sources: string[];
  status: string;
}

/** Tipp-Regeln als Tabellenzeilen: Bereich (max Standard 4), Anzahl Tipps, Quellen mit Titel. */
export function adviceRows(file: AdviceFile): AdviceRuleRow[] {
  const titles = new Map(
    (file.sources ?? []).map((source) => [source.id, source.title ?? source.id]),
  );
  return file.advice.map((rule) => ({
    id: rule.id,
    symptomKey: rule.symptom_key,
    rangeMin: rule.min_value,
    rangeMax: rule.max_value ?? 4,
    tipCount: (rule.tips ?? []).length,
    sources: (rule.source_ids ?? []).map((id) => titles.get(id) ?? id),
    status: rule.status ?? '',
  }));
}
