import type { Medication } from '../api/client';

/** Testdaten (synthetisch) nach openapi v2.3 (Medication); nicht Teil der Laufzeit. */
export const OXALIPLATIN: Medication = {
  medication_id: 'MED-OXALIPLATIN-ACCORD',
  inn: 'oxaliplatin',
  trade_name: 'Oxaliplatin Accord 5 mg/ml',
  sukl_code: '0239968',
  atc: 'L01XA03',
  status: 'reviewed',
  regimens: [
    {
      regimen_id: 'FOLFOX',
      label: 'FOLFOX (oxaliplatin, fluorouracil)',
      symptom_keys: ['nausea', 'peripheral_neuropathy'],
    },
  ],
  spc: {
    title: 'Oxaliplatin Accord – SPC (SÚKL)',
    url: 'https://prehledy.sukl.cz/spc-oxaliplatin',
    locator: '§4.4',
  },
  match: 'name',
  patients_on_regimen: 3,
};

/** Kein Handelsname, kein SÚKL-Code, Status Entwurf, SPC-Link unsicher. */
export const FOLINATE: Medication = {
  medication_id: 'MED-CALCIUM-FOLINATE',
  inn: 'calcium folinate',
  trade_name: null,
  sukl_code: null,
  atc: 'V03AF03',
  status: 'draft',
  regimens: [{ regimen_id: 'FOLFOX', label: 'FOLFOX', symptom_keys: ['unknown_symptom'] }],
  spc: { title: 'Ohne Link', url: 'javascript:alert(1)' },
  match: 'synonym',
  patients_on_regimen: 0,
};

export const MEDICATIONS: Medication[] = [OXALIPLATIN, FOLINATE];

/** T-33: Treffer nur aus dem SÚKL-Index (synthetische Werte), kein Therapieprofil. */
export const SUKL_ONLY: Medication = {
  medication_id: 'SUKL-0000123',
  inn: 'PARALEN TEST',
  trade_name: 'PARALEN TEST',
  sukl_code: '0000123',
  atc: 'N02BE01',
  status: 'sukl_only',
  regimens: [],
  spc: null,
  match: 'name',
  patients_on_regimen: 0,
  sukl: {
    name: 'PARALEN TEST',
    strength: '500MG',
    package: '500MG TBL NOB 24',
    form: 'TBL NOB',
    holder: 'Testfirma s.r.o., Praha',
  },
};
