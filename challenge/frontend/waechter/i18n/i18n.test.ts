import { describe, expect, it } from 'vitest';

import { cs } from './cs';
import { de } from './de';
import { en } from './en';
import {
  FORBIDDEN_CLINICIAN_PHRASES,
  FORBIDDEN_PHRASES,
  findForbidden,
  findForbiddenClinician,
} from './forbidden';

const CATALOGS = { cs, en, de } as const;

/** Flacht einen verschachtelten Katalog zu `a.b.c → Text` ab. */
function flatten(node: unknown, prefix = ''): Record<string, string> {
  if (typeof node === 'string') return { [prefix]: node };
  if (typeof node !== 'object' || node === null) return {};
  return Object.entries(node).reduce<Record<string, string>>(
    (acc, [key, value]) => ({ ...acc, ...flatten(value, prefix ? `${prefix}.${key}` : key) }),
    {},
  );
}

const FLAT = {
  cs: flatten(cs),
  en: flatten(en),
  de: flatten(de),
};

describe('Katalog-Parität cs/en/de', () => {
  it('hat nur Schlüssel unter waechter.*', () => {
    for (const flat of Object.values(FLAT)) {
      expect(Object.keys(flat).length).toBeGreaterThan(20);
      expect(Object.keys(flat).every((key) => key.startsWith('waechter.'))).toBe(true);
    }
  });

  it.each([
    ['cs', 'en'],
    ['cs', 'de'],
    ['en', 'de'],
  ] as const)('%s und %s haben dieselben Schlüssel', (a, b) => {
    expect(Object.keys(FLAT[a]).sort()).toEqual(Object.keys(FLAT[b]).sort());
  });

  it('hat in keiner Sprache leere Texte', () => {
    for (const [locale, flat] of Object.entries(FLAT)) {
      const empty = Object.entries(flat).filter(([, text]) => text.trim() === '');
      expect(empty, locale).toEqual([]);
    }
  });

  it('verwendet in allen Sprachen dieselben Platzhalter {{…}}', () => {
    const placeholders = (text: string) => (text.match(/{{\w+}}/g) ?? []).sort();
    for (const key of Object.keys(FLAT.de)) {
      expect(placeholders(FLAT.cs[key] ?? ''), key).toEqual(placeholders(FLAT.de[key] ?? ''));
      expect(placeholders(FLAT.en[key] ?? ''), key).toEqual(placeholders(FLAT.de[key] ?? ''));
    }
  });
});

describe('Verbotsliste für Patiententexte', () => {
  const patientTexts = (locale: keyof typeof FLAT) =>
    Object.entries(FLAT[locale]).filter(
      ([key]) => key.startsWith('waechter.patient.') || key === 'waechter.nav.patient',
    );

  it('enthält die geforderten Beispielwendungen', () => {
    for (const phrase of [
      'keine sorge',
      'harmlos',
      'alles in ordnung',
      'unbedenklich',
      'diagnose',
      'nebojte',
      'v pořádku',
      "don't worry",
      'harmless',
      'you are fine',
    ]) {
      expect(FORBIDDEN_PHRASES).toContain(phrase);
    }
  });

  it('erkennt verbotene Wendungen (Positivkontrolle, auch mit Großschreibung)', () => {
    expect(findForbidden('Keine Sorge, alles in Ordnung.')).toEqual(
      expect.arrayContaining(['keine sorge', 'alles in ordnung']),
    );
    expect(findForbidden('Nebojte se, je to v pořádku.')).toEqual(
      expect.arrayContaining(['nebojte', 'v pořádku']),
    );
    expect(findForbidden("Don't worry – it is harmless.")).toEqual(
      expect.arrayContaining(["don't worry", 'harmless']),
    );
    expect(findForbidden('Ihre Angaben wurden gespeichert.')).toEqual([]);
  });

  it.each(['cs', 'en', 'de'] as const)(
    '%s: kein Patiententext enthält eine verbotene Wendung',
    (locale) => {
      const texts = patientTexts(locale);
      expect(texts.length).toBeGreaterThan(10);
      const hits = texts
        .map(([key, text]) => ({ key, found: findForbidden(text) }))
        .filter((entry) => entry.found.length > 0);
      expect(hits).toEqual([]);
    },
  );

  it('schließt den Eskalationstext nur als Platzhalter ein', () => {
    const placeholder = {
      cs: '[Text kliniky bude doplněn]',
      en: '[Clinic text to follow]',
      de: '[Text der Klinik folgt]',
    };
    for (const locale of Object.keys(CATALOGS) as (keyof typeof CATALOGS)[]) {
      expect(FLAT[locale]['waechter.patient.response.escalation']).toBe(placeholder[locale]);
    }
  });
  // Vertrag v1.10 (DR-022): Der Akut-Hinweis hat den Klinikwortlaut (Ambulanz oder 155) als Rückfall im
  // Katalog; außer dem einen Platzhalter ohne Serverhinweis steht in Patiententexten nichts in eckigen Klammern.
  it.each(['cs', 'en', 'de'] as const)(
    '%s: Akut-Rückfall nennt 155, keine weiteren Platzhalter',
    (locale) => {
      for (const [key, text] of patientTexts(locale)) {
        if (key === 'waechter.patient.response.escalation') continue;
        expect(text, key).not.toMatch(/\[[^\]]*\]/);
      }
      expect(FLAT[locale]['waechter.patient.acuteFallback']).toContain('155');
    },
  );
});

describe('Verbotsliste für Texte an die Ärztin', () => {
  // Die Fußzeile des Berichts muss laut Auftrag „keine Diagnose“ nennen – ausdrückliche Ausnahme.
  const DISCLAIMER_KEYS = new Set(['waechter.clinic.report.footer']);
  const clinicTexts = (locale: keyof typeof FLAT) =>
    Object.entries(FLAT[locale]).filter(
      ([key]) =>
        (key.startsWith('waechter.clinic.') || key === 'waechter.nav.clinic') &&
        !DISCLAIMER_KEYS.has(key),
    );

  it('enthält Diagnose-, Therapieempfehlungs- und Beruhigungswendungen', () => {
    for (const phrase of ['diagnos', 'empfehl', 'recommend', 'doporuč', 'harmlos']) {
      expect(FORBIDDEN_CLINICIAN_PHRASES).toContain(phrase);
    }
  });

  it('erkennt verbotene Wendungen (Positivkontrolle)', () => {
    expect(findForbiddenClinician('Diagnose: Neutropenie')).toEqual(['diagnose', 'diagnos']);
    expect(findForbiddenClinician('Wir empfehlen eine Dosisreduktion')).toEqual(
      expect.arrayContaining(['empfehl', 'dosis']),
    );
    expect(findForbiddenClinician('We recommend stopping the drug')).toEqual(['recommend']);
    expect(findForbiddenClinician('Warum? Regel und Belege')).toEqual([]);
  });

  it.each(['cs', 'en', 'de'] as const)(
    '%s: kein Klinik-Text enthält eine verbotene Wendung',
    (locale) => {
      const texts = clinicTexts(locale);
      expect(texts.length).toBeGreaterThan(60);
      const hits = texts
        .map(([key, text]) => ({ key, found: findForbiddenClinician(text) }))
        .filter((entry) => entry.found.length > 0);
      expect(hits).toEqual([]);
    },
  );
});
