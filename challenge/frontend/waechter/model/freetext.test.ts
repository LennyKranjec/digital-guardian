import { describe, expect, it } from 'vitest';

import type { FreeText, FreeTextSuggestion } from '../api/client';
import { chipsOf, mentionsFor, segmentsOf } from './freetext';

function suggestion(
  text: string,
  quote: string,
  key = 'diarrhea',
  attribute: string | null = null,
) {
  const start = text.indexOf(quote);
  return {
    symptom_key: key,
    label: key,
    attribute,
    proposed_value: null,
    quote,
    start,
    end: start + quote.length,
    in_questionnaire: true,
    confirmed: false,
    answers: [],
  } satisfies FreeTextSuggestion;
}

describe('segmentsOf: Zitate hervorheben', () => {
  it('liefert ohne Vorschläge den ganzen Text als einen Abschnitt', () => {
    expect(segmentsOf('Mám průjem', [])).toEqual([{ text: 'Mám průjem', suggestions: [] }]);
  });

  it('zerlegt an den Zitatgrenzen und erhält den Text Zeichen für Zeichen', () => {
    const text = 'Mám PRŮJEM a bolí mě to';
    const segments = segmentsOf(text, [
      suggestion(text, 'PRŮJEM'),
      suggestion(text, 'bolí', 'pain'),
    ]);
    expect(segments.map((s) => s.text).join('')).toBe(text);
    expect(segments.filter((s) => s.suggestions.length > 0).map((s) => s.text)).toEqual([
      'PRŮJEM',
      'bolí',
    ]);
  });

  it('ordnet überlappenden Zitaten beide Vorschläge im gemeinsamen Teil zu', () => {
    const text = 'bolest v ústech';
    const segments = segmentsOf(text, [
      suggestion(text, 'bolest v ústech', 'mouth_sores'),
      suggestion(text, 'bolest', 'pain'),
    ]);
    expect(segments.map((s) => [s.text, s.suggestions.length])).toEqual([
      ['bolest', 2],
      [' v ústech', 1],
    ]);
  });

  it('ignoriert Vorschläge, deren Position nicht zum Zitat passt (nie raten)', () => {
    const text = 'Mám průjem';
    const bad: FreeTextSuggestion = { ...suggestion(text, 'průjem'), start: 0, end: 6 };
    const outside: FreeTextSuggestion = { ...suggestion(text, 'průjem'), start: 5, end: 99 };
    expect(segmentsOf(text, [bad, outside])).toEqual([{ text, suggestions: [] }]);
  });
});

describe('chipsOf', () => {
  const base: FreeText = {
    free_text_id: 'f',
    response_id: 'r',
    patient_id: 'p',
    text: 'průjem průjem bolest',
    lang: 'cs',
    created_at: '2026-10-17T09:00:00+02:00',
    suggestions: [],
    mapper: 'template-v1',
    mode: 'template',
    rejected_suggestions: 0,
    unconfirmed: 0,
  };

  it('zeigt je Symptom (und Attribut) nur einen Chip, auch bei mehrfachem Zitat', () => {
    const text = base.text;
    const item = {
      ...base,
      suggestions: [
        suggestion(text, 'průjem'),
        { ...suggestion(text, 'průjem'), start: 7, end: 13 },
        suggestion(text, 'bolest', 'pain'),
        suggestion(text, 'bolest', 'pain', 'severity'),
      ],
    };
    expect(chipsOf(item).map((c) => `${c.symptom_key}:${c.attribute ?? ''}`)).toEqual([
      'diarrhea:',
      'pain:',
      'pain:severity',
    ]);
  });
});

describe('mentionsFor: Zitate zu Symptomen für Meldung und CTCAE-Begriff', () => {
  const make = (id: string, text: string, key: string, confirmed: boolean): FreeText => ({
    free_text_id: id,
    response_id: `r-${id}`,
    patient_id: 'p',
    text,
    lang: 'cs',
    created_at: '2026-10-17T09:00:00+02:00',
    suggestions: [{ ...suggestion(text, text.split(' ')[0] ?? text, key), confirmed }],
    mapper: 'template-v1',
    mode: 'template',
    rejected_suggestions: 0,
    unconfirmed: confirmed ? 0 : 1,
  });

  it('liefert nur Zitate der gefragten Symptome, in der Reihenfolge der Liste', () => {
    const items = [
      make('a', 'průjem trvá', 'diarrhea', true),
      make('b', 'bolest hlavy', 'headache', false),
      make('c', 'průjem znovu', 'diarrhea', false),
    ];
    const result = mentionsFor(items, ['diarrhea']);
    expect(result.map((m) => m.item.free_text_id)).toEqual(['a', 'c']);
    expect(result.map((m) => m.suggestion.confirmed)).toEqual([true, false]);
  });

  it('begrenzt die Zahl und liefert ohne Treffer nichts', () => {
    const items = ['a', 'b', 'c', 'd'].map((id) => make(id, 'průjem x', 'diarrhea', false));
    expect(mentionsFor(items, ['diarrhea'])).toHaveLength(3);
    expect(mentionsFor(items, ['pain'])).toEqual([]);
  });
});
