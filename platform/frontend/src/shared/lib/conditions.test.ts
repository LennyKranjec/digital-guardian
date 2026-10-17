import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { evaluateCondition, isAnswered, type Answers, type Condition } from './conditions';

interface Vector {
  name: string;
  condition: Condition;
  answers: Answers;
  expected: boolean;
}

// vitest läuft im Verzeichnis frontend/; die Vektoren liegen im gemeinsamen Vertragspaket.
const VECTORS_PATH = join(process.cwd(), '..', 'packages', 'contracts', 'condition-vectors.json');
const VECTORS = JSON.parse(readFileSync(VECTORS_PATH, 'utf8')) as Vector[];

describe('Bedingungs-Evaluator gegen gemeinsame Testvektoren (identisch zu pytest)', () => {
  it('lädt mindestens 30 Vektoren mit eindeutigen Namen und beiden Ergebnissen', () => {
    expect(VECTORS.length).toBeGreaterThanOrEqual(30);
    expect(new Set(VECTORS.map((vector) => vector.name)).size).toBe(VECTORS.length);
    expect(new Set(VECTORS.map((vector) => vector.expected))).toEqual(new Set([true, false]));
  });

  it.each(VECTORS.map((vector) => [vector.name, vector] as const))('%s', (_name, vector) => {
    expect(evaluateCondition(vector.condition, vector.answers)).toBe(vector.expected);
  });

  it('deckt alle Operatoren ab', () => {
    const used = new Set<string>();
    const walk = (condition: Condition) => {
      if ('all' in condition) condition.all.forEach(walk);
      else if ('any' in condition) condition.any.forEach(walk);
      else if ('not' in condition) walk(condition.not);
      else used.add(condition.op);
    };
    VECTORS.forEach((vector) => walk(vector.condition));
    expect([...used].sort()).toEqual(
      [
        'answered',
        'contains',
        'eq',
        'gt',
        'gte',
        'in',
        'lt',
        'lte',
        'neq',
        'not_answered',
        'not_in',
      ].sort(),
    );
  });
});

describe('isAnswered', () => {
  it.each([
    [null, false],
    [undefined, false],
    ['', false],
    [[], false],
    [0, true],
    [false, true],
    ['x', true],
    [['a'], true],
  ])('%j → %s', (value, expected) => {
    expect(isAnswered(value)).toBe(expected);
  });
});
