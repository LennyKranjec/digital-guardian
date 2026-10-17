import { describe, expect, it } from 'vitest';

import css from './clinic-theme.css?raw';
import layout from './components/ClinicLayout.tsx?raw';

/** WCAG-2.x-Kontrast aus den Hex-Werten der Klinik-Palette (clinic-theme.css), Light und Dark. */
function block(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) throw new Error(`Block ${selector} fehlt`);
  const body = css.slice(start, css.indexOf('}', start));
  const tokens: Record<string, string> = {};
  for (const match of body.matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    tokens[match[1]!] = match[2]!.toLowerCase();
  }
  return tokens;
}

function luminance(hex: string): number {
  const channel = (offset: number): number => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const LIGHT = block('.clinic-theme');
const DARK = block(":root[data-theme='dark'] .clinic-theme");

/** [Vordergrund, Hintergrund, Mindestkontrast] – Text 4,5:1, Bedienelemente/Rahmen 3:1 */
const PAIRS: ReadonlyArray<readonly [string, string, number]> = [
  ['--rk-text', '--rk-bg', 4.5],
  ['--rk-text', '--rk-surface', 4.5],
  ['--rk-text', '--rk-surface-sunken', 4.5],
  ['--rk-text-muted', '--rk-bg', 4.5],
  ['--rk-text-muted', '--rk-surface', 4.5],
  ['--rk-text-muted', '--rk-surface-sunken', 4.5],
  ['--rk-accent', '--rk-bg', 4.5],
  ['--rk-accent', '--rk-surface', 4.5],
  ['--rk-on-accent', '--rk-accent', 4.5],
  ['--rk-on-accent', '--rk-accent-hover', 4.5],
  ['--rk-accent-subtle-text', '--rk-accent-subtle', 4.5],
  ['--clinic-title', '--rk-bg', 4.5],
  ['--clinic-title', '--rk-surface', 4.5],
  ['--rk-danger', '--rk-bg', 4.5],
  ['--rk-danger', '--rk-surface', 4.5],
  ['--rk-border-strong', '--rk-bg', 3],
  ['--rk-border-strong', '--rk-surface', 3],
  ['--rk-focus', '--rk-bg', 3],
  ['--rk-focus', '--rk-surface', 3],
];

describe('Klinik-Farbschema (T-32): WCAG AA rechnerisch', () => {
  it('nutzt die vorgegebene Palette', () => {
    expect(LIGHT['--rk-bg']).toBe('#faf6f1');
    expect(LIGHT['--rk-surface']).toBe('#f5e3cd');
    expect(LIGHT['--clinic-title']).toBe('#7a5c44');
    expect(LIGHT['--rk-border-strong']).toBe('#8b6b52');
    expect(LIGHT['--rk-accent-subtle']).toBe('#f0b8ae');
    expect(LIGHT['--rk-accent']).toBe('#0f6b63');
    expect(LIGHT['--rk-text']).toBe('#2b2220');
  });

  for (const [name, tokens] of [
    ['hell', LIGHT],
    ['dunkel', DARK],
  ] as const) {
    it(`erreicht in der ${name}en Darstellung alle Mindestkontraste`, () => {
      const failures = PAIRS.flatMap(([fg, bg, min]) => {
        const front = tokens[fg];
        const back = tokens[bg];
        if (front === undefined || back === undefined) return [`${fg}/${bg}: Token fehlt`];
        const value = ratio(front, back);
        return value >= min ? [] : [`${fg} auf ${bg}: ${value.toFixed(2)} < ${min}`];
      });
      expect(failures).toEqual([]);
    });
  }

  it('bleibt flach: kein Schatten, Radien 24 bis 40 px, Schrift ohne Download', () => {
    expect(css).toMatch(/--rk-shadow:\s*none/);
    expect(css).toMatch(/--rk-radius:\s*1\.5rem/);
    expect(css.replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/gradient|@font-face|@import/);
    expect(css).toContain("'Nunito', 'Poppins', ui-rounded, system-ui, sans-serif");
  });

  it('hält das Hochformat frei von Seitwärtsscrollen und begrenzt den Fließtext außerhalb des Cockpits', () => {
    expect(css).toMatch(/overflow-wrap:\s*anywhere/);
    expect(css).toMatch(/overflow-x:\s*clip/);
    expect(css).toMatch(/\.clinic-prose p\s*\{\s*max-width:\s*70ch/);
    // Cockpit (S5, 1366×768 ohne Scrollen) bekommt die Textbreite nicht: nur der Zweig ohne Cockpit trägt clinic-prose
    expect(layout).toContain(
      "inCockpit ? 'clinic-theme min-w-0' : 'clinic-theme clinic-prose min-w-0'",
    );
  });

  it('lässt die Ampelfarben unberührt', () => {
    expect(css.replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/--rk-status-/);
  });
});
