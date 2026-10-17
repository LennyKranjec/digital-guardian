import type {
  AssessmentCreate,
  AssessmentTemplate,
  Attribution,
  FieldErrorLike,
  TemplateTerm,
} from '../api/client';

/**
 * Reine Logik der CTCAE-Aufnahme: nur definierte Grade anbieten, Nutzlast bauen, Serverfehler
 * den Begriffen zuordnen. Die Ärztin wählt jeden Grad selbst – es gibt keine Vorauswahl und
 * keinen Vorschlag aus den PRO-Werten.
 */

export interface TermDraft {
  /** `null` = nicht bewertet (Begriff wird nicht gesendet) */
  grade: number | null;
  attribution: Attribution;
  note: string;
}

export const EMPTY_DRAFT: TermDraft = { grade: null, attribution: 'unknown', note: '' };

export type DraftMap = Readonly<Record<string, TermDraft>>;

export interface GradeOption {
  grade: number;
  /** CTCAE-Gradtext; `null` für Grad 0 (nicht vorhanden) */
  text: string | null;
}

/** Grad 0 plus alle in CTCAE definierten Grade 1–5 (leere oder undefinierte Grade werden nicht angeboten). */
export function availableGrades(term: Pick<TemplateTerm, 'grades'>): GradeOption[] {
  const defined = Object.entries(term.grades)
    .map(([key, text]) => ({ grade: Number(key), text: text.trim() }))
    .filter(
      (entry) =>
        Number.isInteger(entry.grade) && entry.grade >= 1 && entry.grade <= 5 && entry.text !== '',
    )
    .sort((a, b) => a.grade - b.grade);
  return [{ grade: 0, text: null }, ...defined];
}

export function draftOf(drafts: DraftMap, termId: string): TermDraft {
  return drafts[termId] ?? EMPTY_DRAFT;
}

/** Nutzlast ohne ID: nur bewertete Begriffe in Reihenfolge der Vorlage; Notiz nur, wenn nicht leer. */
export function buildItems(
  template: Pick<AssessmentTemplate, 'terms'>,
  drafts: DraftMap,
): AssessmentCreate['items'] {
  return template.terms.flatMap((term) => {
    const draft = draftOf(drafts, term.ctcae_term_id);
    if (draft.grade === null) return [];
    const note = draft.note.trim();
    return [
      {
        ctcae_term_id: term.ctcae_term_id,
        grade: draft.grade,
        attribution: draft.attribution,
        ...(note ? { note } : {}),
      },
    ];
  });
}

export function assessmentFingerprint(
  patientId: string,
  items: AssessmentCreate['items'],
  relatedAlertIds: readonly string[],
): string {
  return JSON.stringify([patientId, items, [...relatedAlertIds].sort()]);
}

export interface TermErrors {
  byTerm: ReadonlyMap<string, string[]>;
  general: string[];
}

/**
 * Ordnet Serverfehler (422) den Begriffskarten zu. Feldpfade wie `items[2].grade`, `items.2.grade`,
 * `body.items.2.grade` verweisen auf die Position in der gesendeten Liste, `items[CTCAE-X]` auf die
 * Begriffskennung; alles andere bleibt allgemein.
 */
export function mapFieldErrors(
  fieldErrors: readonly FieldErrorLike[],
  sentItems: AssessmentCreate['items'],
): TermErrors {
  const byTerm = new Map<string, string[]>();
  const general: string[] = [];
  for (const error of fieldErrors) {
    const match = /items(?:\[|\.|\/)([A-Za-z0-9_-]+)/.exec(error.field);
    let termId: string | undefined;
    if (match?.[1]) {
      termId = /^\d+$/.test(match[1])
        ? sentItems[Number(match[1])]?.ctcae_term_id
        : sentItems.find((item) => item.ctcae_term_id === match[1])?.ctcae_term_id;
    }
    if (termId) byTerm.set(termId, [...(byTerm.get(termId) ?? []), error.message]);
    else general.push(error.message);
  }
  return { byTerm, general };
}

/**
 * PRO-Hinweisschlüssel des Backends: `<symptom>.<merkmal>.<max|last>` (z. B. `nausea.severity.max`);
 * ältere/kurze Formen `severity_max` und `severity` werden ebenfalls gelesen.
 */
export function parseHintKey(key: string): {
  symptom: string | null;
  attribute: string | null;
  stat: 'max' | 'last' | null;
} {
  const match =
    /^(?:([a-z0-9_]+)\.)?(frequency|severity|interference|presence|amount)(?:[_.](max|last))?$/.exec(
      key,
    );
  if (!match) return { symptom: null, attribute: null, stat: null };
  return {
    symptom: match[1] ?? null,
    attribute: match[2] ?? null,
    stat: (match[3] as 'max' | 'last' | undefined) ?? null,
  };
}
