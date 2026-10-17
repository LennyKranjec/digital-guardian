import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { expect, test } from '@playwright/test';

import {
  evaluateCondition,
  type Answers,
  type Condition,
} from '../../../platform/frontend/src/shared/lib/conditions';

interface Vector {
  name: string;
  condition: Condition;
  answers: Answers;
  expected: boolean;
}

// Dieselbe Vektordatei wie tests/backend/unit/test_conditions_vectors.py.
const PATH = join(
  process.cwd(),
  'platform',
  'packages',
  'contracts',
  'condition-vectors-extra.json',
);
const VECTORS = JSON.parse(readFileSync(PATH, 'utf8')) as Vector[];

for (const vector of VECTORS) {
  test(`[H2] ${vector.name}`, () => {
    expect(evaluateCondition(vector.condition, vector.answers)).toBe(vector.expected);
  });
}
