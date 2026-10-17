import { describe, expect, it } from 'vitest';

import { TEMPLATE } from '../testing/cockpit-fixtures';
import {
  assessmentFingerprint,
  availableGrades,
  buildItems,
  draftOf,
  parseHintKey,
  type DraftMap,
} from './assessment';

describe('availableGrades', () => {
  it('bietet Grad 0 (ohne Text) und nur definierte Grade 1–5 aufsteigend an', () => {
    expect(availableGrades({ grades: { '3': 'c', '1': 'a', '2': 'b' } })).toEqual([
      { grade: 0, text: null },
      { grade: 1, text: 'a' },
      { grade: 2, text: 'b' },
      { grade: 3, text: 'c' },
    ]);
  });

  it('lässt leere, undefinierte und ungültige Grade weg', () => {
    expect(
      availableGrades({
        grades: {
          '1': 'a',
          '2': '   ',
          '4': '',
          '0': 'x',
          '6': 'y',
          '-1': 'z',
          abc: 'q',
          '2.5': 'h',
        },
      }),
    ).toEqual([
      { grade: 0, text: null },
      { grade: 1, text: 'a' },
    ]);
    expect(availableGrades({ grades: {} })).toEqual([{ grade: 0, text: null }]);
  });
});

describe('buildItems', () => {
  const drafts: DraftMap = {
    'CTCAE-FEVER': { grade: 0, attribution: 'unknown', note: '' },
    'CTCAE-NAUSEA': { grade: 2, attribution: 'possible', note: '  nach Gabe  ' },
    'CTCAE-FATIGUE': { grade: null, attribution: 'definite', note: 'ignoriert' },
  };

  it('sendet nur bewertete Begriffe in Reihenfolge der Vorlage, Grad 0 eingeschlossen', () => {
    expect(buildItems(TEMPLATE, drafts)).toEqual([
      { ctcae_term_id: 'CTCAE-NAUSEA', grade: 2, attribution: 'possible', note: 'nach Gabe' },
      { ctcae_term_id: 'CTCAE-FEVER', grade: 0, attribution: 'unknown' },
    ]);
  });

  it('liefert ohne Bewertung eine leere Liste', () => {
    expect(buildItems(TEMPLATE, {})).toEqual([]);
    expect(draftOf({}, 'x')).toEqual({ grade: null, attribution: 'unknown', note: '' });
  });
});

describe('assessmentFingerprint', () => {
  const items = [{ ctcae_term_id: 'A', grade: 1 }];

  it('ist unabhängig von der Reihenfolge der verknüpften Meldungen, aber nicht vom Inhalt', () => {
    expect(assessmentFingerprint('p', items, ['b', 'a'])).toBe(
      assessmentFingerprint('p', items, ['a', 'b']),
    );
    expect(assessmentFingerprint('p', items, ['a'])).not.toBe(
      assessmentFingerprint('p', items, ['a', 'b']),
    );
    expect(assessmentFingerprint('p', items, [])).not.toBe(
      assessmentFingerprint('p', [{ ctcae_term_id: 'A', grade: 2 }], []),
    );
    expect(assessmentFingerprint('p', items, [])).not.toBe(assessmentFingerprint('q', items, []));
  });
});

describe('parseHintKey', () => {
  it('trennt Merkmal und Statistik', () => {
    expect(parseHintKey('nausea.severity.max')).toEqual({
      symptom: 'nausea',
      attribute: 'severity',
      stat: 'max',
    });
    expect(parseHintKey('peripheral_neuropathy.interference.last')).toEqual({
      symptom: 'peripheral_neuropathy',
      attribute: 'interference',
      stat: 'last',
    });
    expect(parseHintKey('severity_max')).toEqual({
      symptom: null,
      attribute: 'severity',
      stat: 'max',
    });
    expect(parseHintKey('presence.last')).toEqual({
      symptom: null,
      attribute: 'presence',
      stat: 'last',
    });
    expect(parseHintKey('amount')).toEqual({ symptom: null, attribute: 'amount', stat: null });
    expect(parseHintKey('etwas_anderes')).toEqual({ symptom: null, attribute: null, stat: null });
  });
});
