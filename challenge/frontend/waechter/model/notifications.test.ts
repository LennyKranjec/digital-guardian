import { afterEach, describe, expect, it, vi } from 'vitest';

import { NOTIFICATIONS } from '../testing/fixtures';
import { SEEN_STORAGE_KEY, bannerNotifications, readSeen, writeSeen } from './notifications';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('bannerNotifications', () => {
  it('zeigt nur rote, ungesehene Benachrichtigungen, neueste zuerst', () => {
    const result = bannerNotifications(NOTIFICATIONS, new Set());
    expect(result.map((entry) => entry.notification_id)).toEqual(['n-new', 'n-old']);
  });

  it('blendet gesehene IDs aus', () => {
    const result = bannerNotifications(NOTIFICATIONS, new Set(['n-new']));
    expect(result.map((entry) => entry.notification_id)).toEqual(['n-old']);
  });

  it('behält bei gleicher Zeit die Reihenfolge der Antwort', () => {
    const base = NOTIFICATIONS[0];
    if (!base) throw new Error('Fixture fehlt');
    const same = ['a', 'b', 'c'].map((id) => ({
      ...base,
      notification_id: id,
      at: '2026-10-17T08:00:00+02:00',
    }));
    expect(bannerNotifications(same, new Set()).map((entry) => entry.notification_id)).toEqual([
      'a',
      'b',
      'c',
    ]);
  });
});

describe('gesehen-Speicher', () => {
  it('speichert und liest IDs', () => {
    writeSeen(new Set(['x', 'y']));
    expect([...readSeen()].sort()).toEqual(['x', 'y']);
  });

  it('übersteht kaputten Inhalt', () => {
    localStorage.setItem(SEEN_STORAGE_KEY, '{kaputt');
    expect(readSeen().size).toBe(0);
    localStorage.setItem(SEEN_STORAGE_KEY, '{"a":1}');
    expect(readSeen().size).toBe(0);
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify(['ok', 5, null]));
    expect([...readSeen()]).toEqual(['ok']);
  });

  it('übersteht blockierten Speicher (Lesen und Schreiben)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blockiert');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blockiert');
    });
    expect(readSeen().size).toBe(0);
    expect(() => writeSeen(new Set(['x']))).not.toThrow();
  });

  it('begrenzt die Zahl gemerkter IDs', () => {
    writeSeen(new Set(Array.from({ length: 300 }, (_, index) => `id-${index}`)));
    const stored = readSeen();
    expect(stored.size).toBe(200);
    expect(stored.has('id-299')).toBe(true);
    expect(stored.has('id-0')).toBe(false);
  });
});
