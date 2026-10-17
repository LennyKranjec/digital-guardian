import { describe, expect, it } from 'vitest';

import cs from './cs.json';
import de from './de.json';
import en from './en.json';

type Tree = { [key: string]: string | Tree };

function keys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === 'string' ? [`${prefix}${key}`] : keys(value, `${prefix}${key}.`),
  );
}

describe('i18n-Plattformkatalog', () => {
  it('cs, en und de haben dieselben Schlüssel', () => {
    const reference = keys(en).sort();
    expect(keys(cs).sort()).toEqual(reference);
    expect(keys(de).sort()).toEqual(reference);
  });

  it('enthält die Namespaces, die die Plattformkomponenten nutzen (D-34)', () => {
    for (const namespace of [
      'a11y',
      'auth',
      'banner',
      'ds',
      'home',
      'language',
      'nav',
      'roles',
      'states',
      'status',
      'theme',
    ]) {
      expect(Object.keys(en), namespace).toContain(namespace);
    }
  });

  it('hat keine leeren Texte', () => {
    const empty = (tree: Tree): number =>
      Object.values(tree).filter((v) => (typeof v === 'string' ? v.trim() === '' : empty(v) > 0))
        .length;
    for (const catalog of [cs, en, de]) expect(empty(catalog)).toBe(0);
  });
});
