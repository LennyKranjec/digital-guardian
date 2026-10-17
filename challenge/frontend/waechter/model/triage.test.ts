import { describe, expect, it } from 'vitest';

import {
  adviceRows,
  askedOf,
  hasSpan,
  isPlaceholderStatus,
  lightOf,
  orderReasons,
  shortHash,
  sortRulesRedFirst,
  splitCounterfactuals,
  verificationClean,
  verificationPassed,
  verificationScope,
} from './triage';
import { ADVICE_FILE, TRIAGE_RED, TRIAGE_YELLOW } from '../testing/triage-fixtures';

describe('Triage-Aufbereitung für die Ärztin', () => {
  it('ordnet Begründungen: Schutzboden, Pfad, Blatt, Unvollständigkeit; Gleiche bleiben stabil', () => {
    const ordered = orderReasons([
      { code: 'a', kind: 'incomplete' },
      { code: 'b', kind: 'path' },
      { code: 'c', kind: 'shield' },
      { code: 'd', kind: 'path' },
      { code: 'e', kind: 'leaf' },
      { code: 'f' },
    ]);
    expect(ordered.map((entry) => entry.code)).toEqual(['c', 'b', 'd', 'e', 'a', 'f']);
    expect(orderReasons([])).toEqual([]);
  });

  it('bildet Stufen auf Symbole ab und erkennt eine Spanne nur bei Unterschied', () => {
    expect(lightOf('RED')).toBe('red');
    expect(lightOf('YELLOW')).toBe('yellow');
    expect(lightOf('GREEN')).toBe('green');
    expect(hasSpan(TRIAGE_RED)).toBe(false);
    expect(hasSpan(TRIAGE_YELLOW)).toBe(true);
  });

  it('kürzt Hashes und lässt kurze Werte unverändert', () => {
    expect(shortHash('a1b2c3d4e5f60718')).toBe('a1b2c3d4');
    expect(shortHash('tree-7f3a')).toBe('tree-7f3a'.slice(0, 8));
    expect(shortHash('abc')).toBe('abc');
    expect(shortHash('0123456789abcdef', 12)).toBe('0123456789ab');
  });

  it('zeigt den Platzhalter-Hinweis, solange der Server nichts anderes meldet', () => {
    expect(isPlaceholderStatus('placeholder')).toBe(true);
    expect(isPlaceholderStatus(undefined)).toBe(true);
    expect(isPlaceholderStatus(null)).toBe(true);
    expect(isPlaceholderStatus('approved')).toBe(false);
  });

  it('trennt Kontrafaktische in „sinkt“, „nächste Verschlechterung“ und Schild-Hinweise', () => {
    expect(splitCounterfactuals(TRIAGE_RED)).toEqual({
      lower: ['Durchfall (Schwere) auf ≤ 2 sinkt'],
      raise: ['wenn ein weiteres Symptom Stufe 3 erreicht'],
      shields: ['Boden FLOOR-FEVER verhindert Senkung'],
    });
    expect(splitCounterfactuals({ ...TRIAGE_RED, counterfactuals: undefined })).toEqual({
      lower: [],
      raise: [],
      shields: [],
    });
    // Eintrag ohne kind gilt als normaler Satzteil
    expect(
      splitCounterfactuals({
        ...TRIAGE_RED,
        counterfactuals: [{ direction: 'lower', text: 'x sinkt' }],
      }),
    ).toEqual({ lower: ['x sinkt'], raise: [], shields: [] });
  });

  it('erkennt den Prüfumfang und vergibt den Haken nur bei sauberer, vollständiger Prüfung', () => {
    expect(verificationScope('exhaustive_raw')).toBe('exhaustive');
    expect(verificationScope('exhaustive_orbit')).toBe('exhaustive');
    expect(verificationScope('exhaustive')).toBe('exhaustive');
    expect(verificationScope('sampled_raw')).toBe('sampled');
    expect(verificationScope('irgendwas')).toBe('unknown');
    expect(verificationScope(undefined)).toBe('unknown');
    const clean = { points: 10, under: 0, over: 0, monotone_violations: 0 };
    expect(verificationPassed({ ...clean, scope: 'exhaustive_raw' })).toBe(true);
    expect(verificationPassed({ ...clean, scope: 'sampled_raw' })).toBe(false);
    expect(verificationPassed({ ...clean })).toBe(false);
    expect(verificationPassed({ ...clean, under: 1, scope: 'exhaustive_raw' })).toBe(false);
  });

  it('zeigt „gefragt x von y“ nur mit beiden Zahlen', () => {
    expect(askedOf(TRIAGE_RED)).toEqual({ asked: 5, full: 14 });
    expect(askedOf({ asked_questions: 3 })).toBeNull();
    expect(askedOf({})).toBeNull();
    expect(askedOf({ asked_questions: 0, full_questions: 0 })).toEqual({ asked: 0, full: 0 });
  });

  it('sortiert Regeln rot zuerst und stabil', () => {
    const sorted = sortRulesRedFirst([
      { level: 'YELLOW', text: '1' },
      { level: 'RED', text: '2' },
      { level: 'yellow', text: '3' },
      { level: 'red', text: '4' },
      { level: 'other', text: '5' },
    ]);
    expect(sorted.map((rule) => rule.text)).toEqual(['2', '4', '1', '3', '5']);
  });

  it('erkennt eine saubere Verifikation nur bei 0/0/0', () => {
    expect(verificationClean({ points: 10, under: 0, over: 0, monotone_violations: 0 })).toBe(true);
    expect(verificationClean({ points: 10, under: 1, over: 0, monotone_violations: 0 })).toBe(
      false,
    );
    expect(verificationClean({ points: 10, under: 0, over: 1, monotone_violations: 0 })).toBe(
      false,
    );
    expect(verificationClean({ points: 10, under: 0, over: 0, monotone_violations: 3 })).toBe(
      false,
    );
  });

  it('bereitet Tipp-Regeln auf: Bereich mit Standard 4, Tippzahl, Quellentitel', () => {
    expect(adviceRows(ADVICE_FILE)).toEqual([
      {
        id: 'ADV-NAUSEA-01',
        symptomKey: 'nausea',
        rangeMin: 2,
        rangeMax: 3,
        tipCount: 2,
        sources: ['Nausea and Vomiting, NCI'],
        status: 'draft',
      },
      {
        id: 'ADV-NAUSEA-02',
        symptomKey: 'nausea',
        rangeMin: 4,
        rangeMax: 4,
        tipCount: 1,
        sources: ['Nausea and Vomiting, NCI', 'SRC-UNKNOWN'],
        status: 'draft',
      },
    ]);
    expect(adviceRows({ advice: [] })).toEqual([]);
  });
});
