import { describe, expect, it } from 'vitest';

import { alertTriageSchema } from './client';

// T-16G (A3 T-16 F-01): ein Altbestand aus reinen Codes darf die Übersicht nie kippen.
describe('alertTriageSchema.reason_codes', () => {
  it('nimmt Objekte laut Vertrag unverändert an', () => {
    const parsed = alertTriageSchema.parse({
      level: 'RED',
      reason_codes: [{ code: 'F_FEVER', text: 'Horečka', kind: 'shield', items: ['fever'] }],
    });
    expect(parsed.reason_codes).toEqual([
      { code: 'F_FEVER', text: 'Horečka', kind: 'shield', items: ['fever'] },
    ]);
  });

  it('wandelt reine Codes in Objekte mit dem Code als Text', () => {
    const parsed = alertTriageSchema.parse({ level: 'RED', reason_codes: ['F_FEVER'] });
    expect(parsed.reason_codes).toEqual([{ code: 'F_FEVER', text: 'F_FEVER' }]);
  });

  it('lehnt andere Formen weiter ab', () => {
    expect(alertTriageSchema.safeParse({ level: 'RED', reason_codes: [42] }).success).toBe(false);
  });
});
