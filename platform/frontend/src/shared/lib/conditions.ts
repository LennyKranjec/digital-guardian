/**
 * Bedingungen für Sichtbarkeit (Formular-Sichtbarkeit). Die Semantik ist verbindlich identisch zu
 * `platform/backend/app/core/conditions.py` und wird von beiden Seiten gegen
 * `platform/packages/contracts/condition-vectors.json` geprüft. Kein `eval`.
 *
 * Das Backend entscheidet beim Speichern/Einreichen endgültig; die Auswertung hier steuert nur,
 * welche Fragen das Formular zeigt.
 */

export type Scalar = boolean | number | string;
export type AnswerValue = Scalar | string[];
export type Answers = Readonly<Record<string, AnswerValue | null | undefined>>;

export type Op =
  | 'eq'
  | 'neq'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'in'
  | 'not_in'
  | 'contains'
  | 'answered'
  | 'not_answered';

export interface Leaf {
  item: string;
  op: Op;
  value?: Scalar | Scalar[] | null;
}
export interface AllCondition {
  all: Condition[];
}
export interface AnyCondition {
  any: Condition[];
}
export interface NotCondition {
  not: Condition;
}
export type Condition = Leaf | AllCondition | AnyCondition | NotCondition;

type Kind = 'number' | 'boolean' | 'string' | 'other';

function kindOf(value: unknown): Kind {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number' && Number.isFinite(value)) return 'number';
  if (typeof value === 'string') return 'string';
  return 'other';
}

function sameType(a: unknown, b: unknown): boolean {
  const kind = kindOf(a);
  return kind !== 'other' && kind === kindOf(b);
}

/** Typgleiche Gleichheit: Zahl/Zahl, String/String, Bool/Bool; sonst `false`. */
function strictEqual(a: unknown, b: unknown): boolean {
  return sameType(a, b) && a === b;
}

/** „Beantwortet“ = Wert vorhanden und nicht null, nicht "", keine leere Liste. */
export function isAnswered(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return value !== '';
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

function evaluateLeaf(leaf: Leaf, answers: Answers): boolean {
  const value = answers[leaf.item];
  const answered = isAnswered(value);
  if (leaf.op === 'answered') return answered;
  if (leaf.op === 'not_answered') return !answered;
  if (!answered) return false;

  const target = leaf.value;
  if (leaf.op === 'contains') {
    return Array.isArray(value) && value.some((entry) => strictEqual(entry, target));
  }
  if (leaf.op === 'in' || leaf.op === 'not_in') {
    if (!Array.isArray(target) || Array.isArray(value)) return false;
    if (!target.some((entry) => sameType(value, entry))) return false;
    const member = target.some((entry) => strictEqual(value, entry));
    return leaf.op === 'in' ? member : !member;
  }
  if (Array.isArray(value) || Array.isArray(target) || !sameType(value, target)) return false;
  if (leaf.op === 'eq') return strictEqual(value, target);
  if (leaf.op === 'neq') return !strictEqual(value, target);
  if (typeof value !== 'number' || typeof target !== 'number') return false;
  switch (leaf.op) {
    case 'gt':
      return value > target;
    case 'gte':
      return value >= target;
    case 'lt':
      return value < target;
    default:
      return value <= target;
  }
}

export function evaluateCondition(condition: Condition, answers: Answers): boolean {
  if ('all' in condition) return condition.all.every((child) => evaluateCondition(child, answers));
  if ('any' in condition) return condition.any.some((child) => evaluateCondition(child, answers));
  if ('not' in condition) return !evaluateCondition(condition.not, answers);
  return evaluateLeaf(condition, answers);
}
