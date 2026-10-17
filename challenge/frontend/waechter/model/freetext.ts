import type { Alert, FreeText, FreeTextSuggestion } from '../api/client';

/** Ein Abschnitt des Freitexts; `suggestions` nicht leer ⇒ Hervorhebung (Zitat eines Vorschlags). */
export interface TextSegment {
  text: string;
  suggestions: FreeTextSuggestion[];
}

/**
 * Zerlegt den Text an den Zitatgrenzen der Vorschläge (`start`/`end` vom Server). Überlappende Zitate
 * ergeben einen Abschnitt mit mehreren Vorschlägen; ungültige Positionen (außerhalb des Textes oder
 * ungleich dem Zitat) werden ignoriert, nie geraten.
 */
export function segmentsOf(
  text: string,
  suggestions: readonly FreeTextSuggestion[],
): TextSegment[] {
  const valid = suggestions.filter(
    (s) =>
      s.start >= 0 &&
      s.end <= text.length &&
      s.start < s.end &&
      text.slice(s.start, s.end) === s.quote,
  );
  const cuts = [...new Set([0, text.length, ...valid.flatMap((s) => [s.start, s.end])])].sort(
    (a, b) => a - b,
  );
  const result: TextSegment[] = [];
  for (let i = 0; i < cuts.length - 1; i += 1) {
    const start = cuts[i] ?? 0;
    const end = cuts[i + 1] ?? text.length;
    if (start === end) continue;
    result.push({
      text: text.slice(start, end),
      suggestions: valid.filter((s) => s.start <= start && s.end >= end),
    });
  }
  return result;
}

/** Eindeutige Chips je Symptom (ein Chip, auch wenn das Symptom mehrfach zitiert wird). */
export function chipsOf(item: FreeText): FreeTextSuggestion[] {
  const seen = new Set<string>();
  return item.suggestions.filter((s) => {
    const key = `${s.symptom_key}:${s.attribute ?? ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Zitat eines Freitexts zu einem Symptom („Patientin schrieb …“). */
export interface Mention {
  item: FreeText;
  suggestion: FreeTextSuggestion;
}

/** Zitate zu diesen Symptomen, neueste zuerst (die Liste kommt neueste zuerst vom Server). */
export function mentionsFor(
  items: readonly FreeText[],
  symptomKeys: readonly string[],
  limit = 3,
): Mention[] {
  const wanted = new Set(symptomKeys);
  return items
    .flatMap((item) =>
      item.suggestions
        .filter((suggestion) => wanted.has(suggestion.symptom_key))
        .map((suggestion) => ({ item, suggestion })),
    )
    .slice(0, limit);
}

/** Symptome, an denen eine Meldung beteiligt ist: ihr eigenes und die der Triage-Begründung. */
export function alertSymptoms(alert: Alert): string[] {
  const own = alert.symptom_key ? [alert.symptom_key] : [];
  const reasons = alert.explanation?.triage?.reason_codes ?? [];
  return [...new Set([...own, ...reasons.flatMap((reason) => reason.items ?? [])])];
}
