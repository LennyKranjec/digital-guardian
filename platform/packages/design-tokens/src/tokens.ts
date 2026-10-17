import { contrastRatio } from './contrast';

export type ThemeName = 'light' | 'dark';
export type TokenMap = Record<string, string>;
export type ResolvedTokens = Record<ThemeName, TokenMap>;

/** `kind: text` verlangt ≥ 4.5:1, `kind: ui` (Rahmen, Fokus, Diagrammlinien) ≥ 3:1 (WCAG 2.2 AA). */
export interface ContrastPair {
  id: string;
  kind: 'text' | 'ui';
  foreground: string;
  background: string;
}

export const MIN_CONTRAST = { text: 4.5, ui: 3 } as const;

const text = (fg: string, bg: string): ContrastPair => ({
  id: `text: ${fg} / ${bg}`,
  kind: 'text',
  foreground: fg,
  background: bg,
});
const ui = (fg: string, bg: string): ContrastPair => ({
  id: `ui: ${fg} / ${bg}`,
  kind: 'ui',
  foreground: fg,
  background: bg,
});

/** Alle Text- und UI-Paarungen, die die Oberfläche verwendet (Token-Namen ohne `--rk-`). */
export const contrastPairs: readonly ContrastPair[] = [
  text('text', 'bg'),
  text('text', 'surface'),
  text('text', 'surface-sunken'),
  text('text-muted', 'bg'),
  text('text-muted', 'surface'),
  text('text-muted', 'surface-sunken'),
  text('accent', 'bg'),
  text('accent', 'surface'),
  text('on-accent', 'accent'),
  text('on-accent', 'accent-hover'),
  text('accent-subtle-text', 'accent-subtle'),
  text('danger', 'bg'),
  text('danger', 'surface'),
  text('status-neutral-fg', 'status-neutral-bg'),
  text('status-info-fg', 'status-info-bg'),
  text('status-caution-fg', 'status-caution-bg'),
  text('status-critical-fg', 'status-critical-bg'),
  ui('border-strong', 'bg'),
  ui('border-strong', 'surface'),
  ui('focus', 'bg'),
  ui('focus', 'surface'),
  ui('accent', 'surface'),
  ui('chart-1', 'surface'),
  ui('chart-2', 'surface'),
];

function parseBlock(block: string): TokenMap {
  const tokens: TokenMap = {};
  for (const match of block.matchAll(/--rk-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    tokens[match[1] as string] = match[2] as string;
  }
  return tokens;
}

/** Liest Farb-Tokens aus tokens.css; Dark erbt alles, was es nicht überschreibt, aus Light. */
export function parseTokenCss(css: string): ResolvedTokens {
  const light = /:root\s*\{([^}]*)\}/.exec(css);
  const dark = /:root\[data-theme='dark'\]\s*\{([^}]*)\}/.exec(css);
  if (!light || !dark) {
    throw new Error('tokens.css: :root- oder :root[data-theme=dark]-Block fehlt');
  }
  const lightTokens = parseBlock(light[1] as string);
  return { light: lightTokens, dark: { ...lightTokens, ...parseBlock(dark[1] as string) } };
}

export interface ContrastResult extends ContrastPair {
  theme: ThemeName;
  ratio: number;
  minimum: number;
  passes: boolean;
}

export function evaluateContrast(tokens: ResolvedTokens): ContrastResult[] {
  const results: ContrastResult[] = [];
  for (const theme of ['light', 'dark'] as const) {
    for (const pair of contrastPairs) {
      const fg = tokens[theme][pair.foreground];
      const bg = tokens[theme][pair.background];
      if (!fg || !bg) {
        throw new Error(`Token fehlt in ${theme}: ${pair.foreground} oder ${pair.background}`);
      }
      const ratio = contrastRatio(fg, bg);
      const minimum = MIN_CONTRAST[pair.kind];
      results.push({ ...pair, theme, ratio, minimum, passes: ratio >= minimum });
    }
  }
  return results;
}
