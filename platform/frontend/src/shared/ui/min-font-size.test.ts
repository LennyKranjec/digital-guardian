import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = join(process.cwd(), 'src'); // vitest läuft im Verzeichnis frontend/

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(tsx|css)$/.test(name) && !/\.test\./.test(name) ? [path] : [];
  });
}

/** ui.md v1.2: kleinste Textgröße 16 px – keine Utility-Klassen für kleinere Schrift im Frontend. */
describe('Mindestschrift im Frontend-Quelltext', () => {
  it('verwendet kein text-xs und keine festen Pixelgrößen unter 16 px', () => {
    const offenders = sourceFiles(SRC).flatMap((file) => {
      const text = readFileSync(file, 'utf8');
      const hits: string[] = [];
      if (/\btext-xs\b/.test(text)) hits.push('text-xs');
      for (const match of text.matchAll(/text-\[(\d+(?:\.\d+)?)(px|rem)\]/g)) {
        const px = match[2] === 'rem' ? Number(match[1]) * 16 : Number(match[1]);
        if (px < 16) hits.push(match[0]);
      }
      for (const match of text.matchAll(/font-size:\s*(\d+(?:\.\d+)?)(px|rem)/g)) {
        const px = match[2] === 'rem' ? Number(match[1]) * 16 : Number(match[1]);
        if (px < 16) hits.push(match[0]);
      }
      return hits.map((hit) => `${file}: ${hit}`);
    });
    expect(offenders).toEqual([]);
  });
});
