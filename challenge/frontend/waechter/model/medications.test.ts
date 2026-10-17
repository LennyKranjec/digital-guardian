import { describe, expect, it } from 'vitest';

import { CONFIG } from '../testing/cockpit-fixtures';
import { FOLINATE, OXALIPLATIN } from '../testing/medication-fixtures';
import {
  canSearch,
  cleanQuery,
  displayName,
  medicationSearchPath,
  spcUrl,
  symptomLabels,
} from './medications';

describe('Arzneimittelsuche: reine Logik', () => {
  it('putzt den Suchtext und sucht erst ab 2 Zeichen', () => {
    expect(cleanQuery('  oxali   platin ')).toBe('oxali platin');
    expect(canSearch('o')).toBe(false);
    expect(canSearch(' o ')).toBe(false);
    expect(canSearch('')).toBe(false);
    expect(canSearch('ox')).toBe(true);
    expect(canSearch('0239968')).toBe(true);
  });

  it('verlinkt SPC nur mit http(s)', () => {
    expect(spcUrl('https://prehledy.sukl.cz/x')).toBe('https://prehledy.sukl.cz/x');
    expect(spcUrl('javascript:alert(1)')).toBeNull();
    expect(spcUrl('//evil.example')).toBeNull();
    expect(spcUrl(null)).toBeNull();
  });

  it('zeigt Etiketten der Konfiguration, sonst den Schlüssel', () => {
    expect(symptomLabels(['nausea', 'unbekannt'], CONFIG, 'en')).toEqual(['Nausea', 'unbekannt']);
    expect(symptomLabels(['nausea'], CONFIG, 'cs')).toEqual(['Nevolnost']);
    expect(symptomLabels(undefined, CONFIG, 'en')).toEqual([]);
    expect(symptomLabels(['nausea'], undefined, 'en')).toEqual(['nausea']);
  });

  it('nennt zuerst den Handelsnamen, sonst den Wirkstoff', () => {
    expect(displayName(OXALIPLATIN)).toBe('Oxaliplatin Accord 5 mg/ml');
    expect(displayName(FOLINATE)).toBe('calcium folinate');
    expect(displayName({ trade_name: '  ', inn: 'x' })).toBe('x');
  });

  it('baut den Link vom Cockpit-Kopf mit kodiertem Namen', () => {
    expect(medicationSearchPath('Wirkstoff X')).toBe('/clinic/medications?q=Wirkstoff%20X');
    expect(medicationSearchPath(' kalcium-folinát ')).toBe(
      '/clinic/medications?q=kalcium-folin%C3%A1t',
    );
  });
});
