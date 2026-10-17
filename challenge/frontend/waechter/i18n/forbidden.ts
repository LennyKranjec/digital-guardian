/**
 * Verbotsliste für Patiententexte (COMMON §2, Vertrag §2): keine Diagnose, keine Beruhigung, kein
 * Alarm, keine Ampel/Stufe, keine Reaktionszusage. Vergleich auf Kleinbuchstaben als Teilzeichenfolge.
 * Der Test (`i18n.test.ts`) prüft damit alle Texte unter `waechter.nav` und `waechter.patient`
 * in cs, en und de.
 */
export const FORBIDDEN_PHRASES: readonly string[] = [
  // Beruhigung
  'keine sorge',
  'keine sorgen',
  'harmlos',
  'alles in ordnung',
  'unbedenklich',
  'keine gefahr',
  'nebojte',
  'v pořádku',
  'neškodn',
  'nic se neděje',
  'žádný důvod k obavám',
  "don't worry",
  'do not worry',
  'harmless',
  'you are fine',
  "you're fine",
  'nothing to worry',
  'all clear',
  'no cause for concern',
  // Diagnose
  'diagnose',
  'diagnos',
  'diagnóz',
  // Alarm, Ampel, Stufe
  'alarm',
  'notfall',
  'lebensgefahr',
  'ampel',
  'semafor',
  'traffic light',
  // Reaktionszusage
  'wir melden uns',
  'wir kümmern uns',
  'wird sich melden',
  'ozveme se',
  'we will contact you',
  "we'll contact you",
  'we will call you',
  'someone will call',
];

/** Gefundene verbotene Wendungen in einem Text (leer = unbedenklich im Sinne der Liste). */
export function findForbidden(text: string): string[] {
  const lower = text.toLocaleLowerCase();
  return FORBIDDEN_PHRASES.filter((phrase) => lower.includes(phrase));
}

/**
 * Verbotsliste für Texte an die Ärztin (Oberfläche der Klinikseiten): das System stellt keine
 * Diagnose, gibt keine Therapieempfehlung oder -entscheidung vor und beruhigt nicht. (Ampel- und
 * Alarmwörter sind hier erlaubt, sie gehören zur Arbeitsliste.) Teilzeichenfolgen, Kleinbuchstaben.
 */
export const FORBIDDEN_CLINICIAN_PHRASES: readonly string[] = [
  // Diagnose
  'diagnose',
  'diagnos',
  'diagnóz',
  // Therapieempfehlung / -entscheidung
  'empfehl',
  'recommend',
  'doporuč',
  'therapieentscheid',
  'treatment decision',
  'sollte behandelt',
  'should be treated',
  'dosis',
  'dosage',
  'dávkov',
  // Beruhigung
  'keine sorge',
  'harmlos',
  'alles in ordnung',
  'unbedenklich',
  'harmless',
  "don't worry",
  'nebojte',
  'v pořádku',
];

export function findForbiddenClinician(text: string): string[] {
  const lower = text.toLocaleLowerCase();
  return FORBIDDEN_CLINICIAN_PHRASES.filter((phrase) => lower.includes(phrase));
}
