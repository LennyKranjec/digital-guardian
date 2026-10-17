import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { contrastRatio } from './contrast';
import { MIN_CONTRAST, contrastPairs, evaluateContrast, parseTokenCss } from './tokens';

const css = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8');
const tokens = parseTokenCss(css);

describe('contrastRatio (WCAG-Referenzwerte)', () => {
  it('schwarz auf weiß = 21:1', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
  });
  it('gleiche Farbe = 1:1', () => {
    expect(contrastRatio('#336699', '#336699')).toBeCloseTo(1, 5);
  });
  it('ist symmetrisch', () => {
    expect(contrastRatio('#0e6f68', '#faf7f2')).toBeCloseTo(
      contrastRatio('#faf7f2', '#0e6f68'),
      10,
    );
  });
  it('#777777 auf weiß ≈ 4.48:1 (bekannter Grenzfall unter AA)', () => {
    expect(contrastRatio('#777777', '#ffffff')).toBeCloseTo(4.48, 2);
  });
});

describe('tokens.css', () => {
  it('Dark überschreibt dieselben Farb-Tokens wie Light (keine Lücken)', () => {
    expect(Object.keys(tokens.dark).sort()).toEqual(Object.keys(tokens.light).sort());
    const overridden = Object.keys(tokens.light).filter((k) => tokens.dark[k] !== tokens.light[k]);
    expect(overridden.length).toBeGreaterThan(15);
  });

  it('jede deklarierte Paarung verweist auf existierende Tokens', () => {
    for (const pair of contrastPairs) {
      expect(tokens.light[pair.foreground], pair.foreground).toBeDefined();
      expect(tokens.light[pair.background], pair.background).toBeDefined();
    }
  });
});

describe('WCAG-2.2-AA-Kontrast aller Token-Paare', () => {
  const results = evaluateContrast(tokens);

  it('jede Paarung hat eine eindeutige ID', () => {
    const ids = contrastPairs.map((pair) => pair.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('deckt beide Themes und beide Arten ab', () => {
    expect(results.some((r) => r.theme === 'light' && r.kind === 'text')).toBe(true);
    expect(results.some((r) => r.theme === 'dark' && r.kind === 'ui')).toBe(true);
    expect(results).toHaveLength(contrastPairs.length * 2);
  });

  for (const result of results) {
    const label = `${result.theme}: ${result.id} ≥ ${MIN_CONTRAST[result.kind]}`;
    it(label, () => {
      expect(
        result.ratio,
        `${result.id} im ${result.theme}-Modus: ${result.ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(MIN_CONTRAST[result.kind]);
    });
  }
});

describe('Mindestschrift (ui.md v1.2, A3 F-01)', () => {
  const theme = readFileSync(
    fileURLToPath(new URL('./tailwind-theme.css', import.meta.url)),
    'utf8',
  );

  it('keine Textgrößen-Variable unter 1rem (16 px)', () => {
    const sizes = [...theme.matchAll(/--text-[\w-]+:\s*([\d.]+)rem;/g)].map((m) => Number(m[1]));
    expect(sizes.length).toBeGreaterThan(0);
    for (const size of sizes) expect(size).toBeGreaterThanOrEqual(1);
  });
});
