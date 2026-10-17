import type {
  AlertLevel,
  ConfigRule,
  FieldErrorLike,
  Lang,
  Noise,
  ReportSection,
  ReportSince,
  RulesFile,
  RulesUpdate,
} from '../api/client';
import { REPORT_SECTIONS } from '../api/client';

/**
 * Reine Logik der Einstellungsseite: Entwürfe der Regelparameter, Eingabeprüfung, Nutzlast für
 * `PUT /config/rules` und `PUT /config/report`, Zuordnung von Serverfehlern zu Regelzeilen.
 * Der Server bleibt maßgeblich (Version, Pflicht „mindestens eine aktive rote Regel“).
 */

export interface RuleDraft {
  enabled: boolean;
  /** Eingaben als Text, damit halbfertige Eingaben (z. B. „0,“) erhalten bleiben */
  params: Readonly<Record<string, string>>;
}
export type RuleDrafts = Readonly<Record<string, RuleDraft>>;

export interface NoiseDraft {
  cooldown: string;
  notify: readonly AlertLevel[];
}

export function formatParam(value: number): string {
  return String(value).replace('.', ',');
}

/** Dezimalzahl mit Komma oder Punkt; leer, negativ oder keine Zahl ⇒ `null`. */
export function parseParam(text: string): number | null {
  const normalized = text.trim().replace(',', '.');
  if (normalized === '' || !/^\d+(\.\d+)?$/.test(normalized)) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

export function initialDrafts(rules: readonly ConfigRule[]): RuleDrafts {
  return Object.fromEntries(
    rules.map((rule) => [
      rule.id,
      {
        enabled: rule.enabled,
        params: Object.fromEntries(
          Object.entries(rule.params).map(([key, value]) => [key, formatParam(value)]),
        ),
      },
    ]),
  );
}

export function initialNoise(noise: Noise | null | undefined): NoiseDraft {
  return {
    cooldown: formatParam(noise?.cooldown_hours ?? 0),
    notify: noise?.notify_levels ?? ['red'],
  };
}

/** Parameter mit ungültiger Eingabe je Regel (`ruleId → [paramKey]`). */
export function invalidParams(
  rules: readonly ConfigRule[],
  drafts: RuleDrafts,
): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const rule of rules) {
    const draft = drafts[rule.id];
    if (!draft) continue;
    const bad = Object.keys(rule.params).filter(
      (key) => parseParam(draft.params[key] ?? '') === null,
    );
    if (bad.length > 0) result[rule.id] = bad;
  }
  return result;
}

export function isCooldownValid(noise: NoiseDraft): boolean {
  return parseParam(noise.cooldown) !== null;
}

export function rulesChanged(file: RulesFile, drafts: RuleDrafts, noiseDraft: NoiseDraft): boolean {
  const base = initialDrafts(file.rules);
  const baseNoise = initialNoise(file.noise);
  const rulesDiffer = file.rules.some((rule) => {
    const a = base[rule.id];
    const b = drafts[rule.id];
    if (!a || !b) return false;
    return (
      a.enabled !== b.enabled ||
      Object.keys(rule.params).some(
        (key) => parseParam(a.params[key] ?? '') !== parseParam(b.params[key] ?? ''),
      )
    );
  });
  const notifyDiffer = [...baseNoise.notify].sort().join() !== [...noiseDraft.notify].sort().join();
  return (
    rulesDiffer ||
    notifyDiffer ||
    parseParam(baseNoise.cooldown) !== parseParam(noiseDraft.cooldown)
  );
}

/** Vorab-Hinweis (der Server prüft maßgeblich): bleibt mindestens eine aktive rote Regel? */
export function hasActiveRedRule(rules: readonly ConfigRule[], drafts: RuleDrafts): boolean {
  return rules.some((rule) => rule.level === 'red' && (drafts[rule.id]?.enabled ?? rule.enabled));
}

/**
 * Nutzlast für `PUT /config/rules`: vollständige Regeldatei ohne `version`. Die Begründung wird so
 * zurückgeschickt, wie sie gelesen wurde (liegt sie nur lokalisiert als Text vor, in der Anfragesprache
 * als Objekt), damit nichts außer Aktivierung, Parametern und Rauschbremse verändert wird.
 */
export function buildRulesUpdate(
  file: RulesFile,
  drafts: RuleDrafts,
  noiseDraft: NoiseDraft,
  lang: Lang,
  changeNote: string,
): RulesUpdate {
  const rules = file.rules.map((rule) => {
    const draft = drafts[rule.id];
    const params = Object.fromEntries(
      Object.entries(rule.params).map(([key, original]) => [
        key,
        parseParam(draft?.params[key] ?? '') ?? original,
      ]),
    );
    const rationale =
      typeof rule.rationale === 'string' ? { [lang]: rule.rationale } : rule.rationale;
    return {
      ...rule,
      enabled: draft?.enabled ?? rule.enabled,
      params,
      ...(rationale ? { rationale } : {}),
    };
  });
  const baseNoise = file.noise;
  return {
    expected_version: file.version,
    rules: {
      rules,
      ...(baseNoise
        ? {
            noise: {
              ...baseNoise,
              cooldown_hours: parseParam(noiseDraft.cooldown) ?? baseNoise.cooldown_hours,
              notify_levels: [...noiseDraft.notify],
            },
          }
        : {}),
    },
    change_note: changeNote.trim(),
  };
}

export interface RuleErrors {
  byRule: ReadonlyMap<string, string[]>;
  general: string[];
}

/**
 * Ordnet 422-Feldfehler Regelzeilen zu. Gelesen werden Pfade mit Position in der gesendeten
 * Regelliste: `rules.<i>…`, `rules.rules.<i>…`, `rules[<i>]…`, `body.rules.rules.<i>…`, oder der
 * Regelkennung statt der Position. Alles andere (z. B. `change_note`, `rules`) bleibt allgemein.
 */
export function mapRuleErrors(
  fieldErrors: readonly FieldErrorLike[],
  sentRules: readonly { id: string }[],
): RuleErrors {
  const byRule = new Map<string, string[]>();
  const general: string[] = [];
  for (const error of fieldErrors) {
    const match = /rules(?:\.rules)?(?:\[|\.|\/)(\d+|R-[A-Z]+-\d+)/.exec(error.field);
    let ruleId: string | undefined;
    if (match?.[1]) {
      ruleId = /^\d+$/.test(match[1])
        ? sentRules[Number(match[1])]?.id
        : sentRules.find((rule) => rule.id === match[1])?.id;
    }
    if (ruleId) byRule.set(ruleId, [...(byRule.get(ruleId) ?? []), error.message]);
    else general.push(error.message);
  }
  return { byRule, general };
}

/* ---------- Bericht ---------- */

export interface ReportDraft {
  since: ReportSince;
  sections: readonly ReportSection[];
}

/** Bekannte Abschnitte in fester Reihenfolge; unbekannte Namen der Konfiguration werden verworfen. */
export function normalizeSections(sections: readonly string[]): ReportSection[] {
  return REPORT_SECTIONS.filter((section) => sections.includes(section));
}

export function toggleSection(
  sections: readonly ReportSection[],
  section: ReportSection,
  on: boolean,
): ReportSection[] {
  const next = new Set(sections);
  if (on) next.add(section);
  else next.delete(section);
  return REPORT_SECTIONS.filter((entry) => next.has(entry));
}

export function reportChanged(
  original: { since?: string | null; sections: readonly string[] },
  draft: ReportDraft,
): boolean {
  return (
    (original.since ?? 'last_visit') !== draft.since ||
    normalizeSections(original.sections).join() !== draft.sections.join()
  );
}
