import { describe, expect, it } from 'vitest';

import { rulesFileSchema } from '../api/client';
import { CONFIG } from '../testing/cockpit-fixtures';
import {
  buildRulesUpdate,
  formatParam,
  hasActiveRedRule,
  initialDrafts,
  initialNoise,
  invalidParams,
  isCooldownValid,
  mapRuleErrors,
  normalizeSections,
  parseParam,
  reportChanged,
  rulesChanged,
  toggleSection,
} from './settings';

const file = rulesFileSchema.parse(CONFIG.rules);

describe('parseParam / formatParam', () => {
  it('liest Dezimalkomma und -punkt, lehnt Leeres, Negatives und Text ab', () => {
    expect(parseParam('3')).toBe(3);
    expect(parseParam(' 0,15 ')).toBe(0.15);
    expect(parseParam('2.5')).toBe(2.5);
    for (const bad of ['', '  ', '-1', 'abc', '1,2,3', '1e3', '3 Tage', ',5']) {
      expect(parseParam(bad), bad).toBeNull();
    }
    expect(formatParam(0.15)).toBe('0,15');
    expect(formatParam(3)).toBe('3');
  });
});

describe('Entwürfe und Änderungserkennung', () => {
  it('startet unverändert und erkennt Änderungen an Aktivierung, Parametern und Rauschbremse', () => {
    const drafts = initialDrafts(file.rules);
    const noise = initialNoise(file.noise);
    expect(rulesChanged(file, drafts, noise)).toBe(false);
    expect(
      rulesChanged(
        file,
        { ...drafts, 'R-SEV-01': { ...drafts['R-SEV-01']!, enabled: false } },
        noise,
      ),
    ).toBe(true);
    expect(
      rulesChanged(
        file,
        { ...drafts, 'R-SEV-01': { enabled: true, params: { min_value: '2,5' } } },
        noise,
      ),
    ).toBe(true);
    // "3" und "3,0" sind derselbe Wert ⇒ keine Änderung
    expect(
      rulesChanged(
        file,
        { ...drafts, 'R-SEV-01': { enabled: true, params: { min_value: '3,0' } } },
        noise,
      ),
    ).toBe(false);
    expect(rulesChanged(file, drafts, { ...noise, cooldown: '12' })).toBe(true);
    expect(rulesChanged(file, drafts, { ...noise, notify: ['red', 'yellow'] })).toBe(true);
    expect(rulesChanged(file, drafts, { ...noise, notify: [...noise.notify] })).toBe(false);
  });

  it('meldet ungültige Parameter je Regel und ungültige Sperrzeit', () => {
    const drafts = initialDrafts(file.rules);
    const bad = { ...drafts, 'R-DLT-01': { enabled: true, params: { min_delta: 'x' } } };
    expect(invalidParams(file.rules, bad)).toEqual({ 'R-DLT-01': ['min_delta'] });
    expect(invalidParams(file.rules, drafts)).toEqual({});
    expect(isCooldownValid({ cooldown: '24', notify: [] })).toBe(true);
    expect(isCooldownValid({ cooldown: 'a', notify: [] })).toBe(false);
  });

  it('prüft vorab, ob eine aktive rote Regel bleibt', () => {
    const drafts = initialDrafts(file.rules);
    expect(hasActiveRedRule(file.rules, drafts)).toBe(true);
    const off = {
      ...drafts,
      'R-SEV-01': { ...drafts['R-SEV-01']!, enabled: false },
      'R-URG-01': { ...drafts['R-URG-01']!, enabled: false },
    };
    expect(hasActiveRedRule(file.rules, off)).toBe(false);
  });
});

describe('buildRulesUpdate', () => {
  it('sendet die vollständige Regeldatei ohne Version, bedingt über die gelesene Version', () => {
    const drafts = {
      ...initialDrafts(file.rules),
      'R-SEV-01': { enabled: true, params: { min_value: '2,5' } },
    };
    const update = buildRulesUpdate(
      file,
      drafts,
      { cooldown: '12', notify: ['red', 'grey'] },
      'de',
      '  Notiz  ',
    );
    expect(update.expected_version).toBe('rules-v1');
    expect(update.change_note).toBe('Notiz');
    expect(update.rules.rules).toHaveLength(file.rules.length);
    expect(update.rules.rules[0]?.params).toEqual({ min_value: 2.5 });
    expect(update.rules.noise).toEqual({
      notify_levels: ['red', 'grey'],
      digest_levels: ['yellow', 'grey'],
      cooldown_hours: 12,
    });
    expect(update.rules).not.toHaveProperty('version');
  });

  it('lässt unveränderte Felder (Begründung, Quelle, Geltungsbereich) unberührt', () => {
    const update = buildRulesUpdate(
      file,
      initialDrafts(file.rules),
      initialNoise(file.noise),
      'de',
      'n',
    );
    expect(update.rules.rules[0]).toMatchObject({
      id: 'R-SEV-01',
      attributes: ['severity', 'interference'],
      source_id: 'SRC-DEMO',
      rationale: {
        cs: 'Demonstrační práh, klinicky neověřeno.',
        en: 'Demo threshold, not clinically validated.',
      },
    });
  });

  it('macht aus einer schon lokalisierten Begründung wieder ein Objekt in der Anfragesprache', () => {
    const localizedFile = {
      ...file,
      rules: file.rules.map((rule) => ({ ...rule, rationale: 'Nur Deutsch' })),
    };
    const update = buildRulesUpdate(
      localizedFile,
      initialDrafts(localizedFile.rules),
      initialNoise(file.noise),
      'de',
      'n',
    );
    expect(update.rules.rules[0]?.rationale).toEqual({ de: 'Nur Deutsch' });
  });

  it('behält den ursprünglichen Wert, wenn eine Eingabe ungültig ist (wird vorher abgefangen)', () => {
    const drafts = {
      ...initialDrafts(file.rules),
      'R-SEV-01': { enabled: true, params: { min_value: 'x' } },
    };
    expect(
      buildRulesUpdate(file, drafts, initialNoise(file.noise), 'de', 'n').rules.rules[0]?.params,
    ).toEqual({
      min_value: 3,
    });
  });
});

describe('mapRuleErrors', () => {
  const sent = file.rules.map((rule) => ({ id: rule.id }));

  it('erkennt gängige Pfadschreibweisen und die Regelkennung', () => {
    for (const field of [
      'rules.2.params.min_value',
      'rules.rules.2.enabled',
      'rules[2].params',
      'body.rules.rules.2',
      'rules/2/x',
    ]) {
      const mapped = mapRuleErrors([{ field, code: 'x', message: 'm' }], sent);
      expect(mapped.byRule.get('R-OFF-01'), field).toEqual(['m']);
    }
    const byId = mapRuleErrors(
      [{ field: 'rules[R-DLT-01].params', code: 'x', message: 'id' }],
      sent,
    );
    expect(byId.byRule.get('R-DLT-01')).toEqual(['id']);
  });

  it('sammelt Unbekanntes und Allgemeines getrennt', () => {
    const mapped = mapRuleErrors(
      [
        { field: 'change_note', code: 'x', message: 'a' },
        { field: 'rules.9.params', code: 'x', message: 'b' },
        { field: 'rules', code: 'no_red_rule', message: 'c' },
      ],
      sent,
    );
    expect(mapped.byRule.size).toBe(0);
    expect(mapped.general).toEqual(['a', 'b', 'c']);
  });
});

describe('Berichtsabschnitte', () => {
  it('normalisiert auf bekannte Abschnitte in fester Reihenfolge', () => {
    expect(normalizeSections(['audit', 'x', 'summary'])).toEqual(['summary', 'audit']);
  });

  it('schaltet Abschnitte ein und aus, ohne die Reihenfolge zu ändern', () => {
    const start = normalizeSections(['summary', 'audit']);
    expect(toggleSection(start, 'alerts', true)).toEqual(['summary', 'alerts', 'audit']);
    expect(toggleSection(start, 'summary', false)).toEqual(['audit']);
    expect(toggleSection(start, 'summary', true)).toEqual(['summary', 'audit']);
  });

  it('erkennt Änderungen an Abschnitten und Zeitraum', () => {
    const original = { since: 'last_visit', sections: ['summary', 'alerts'] };
    expect(reportChanged(original, { since: 'last_visit', sections: ['summary', 'alerts'] })).toBe(
      false,
    );
    expect(reportChanged(original, { since: 'days_14', sections: ['summary', 'alerts'] })).toBe(
      true,
    );
    expect(reportChanged(original, { since: 'last_visit', sections: ['summary'] })).toBe(true);
    expect(
      reportChanged({ sections: ['summary'] }, { since: 'last_visit', sections: ['summary'] }),
    ).toBe(false);
  });
});
