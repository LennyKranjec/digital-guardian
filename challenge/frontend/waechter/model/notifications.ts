import type { Notification } from '../api/client';

/** Lokal gemerkte, bereits gesehene Benachrichtigungen (Vertrag G-17); Speicher kann fehlen oder blockiert sein. */
export const SEEN_STORAGE_KEY = 'waechter.notifications.seen';
const MAX_REMEMBERED = 200;

export function readSeen(): ReadonlySet<string> {
  try {
    const raw = localStorage.getItem(SEEN_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((entry): entry is string => typeof entry === 'string'));
  } catch {
    return new Set();
  }
}

export function writeSeen(ids: ReadonlySet<string>): void {
  try {
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify([...ids].slice(-MAX_REMEMBERED)));
  } catch {
    // Speicher blockiert: „gesehen“ gilt nur bis zum Neuladen.
  }
}

/** Bannerliste: nur rote, ungesehene Benachrichtigungen, neueste zuerst (Reihenfolge sonst stabil). */
export function bannerNotifications(
  notifications: readonly Notification[],
  seen: ReadonlySet<string>,
): Notification[] {
  return notifications
    .filter((entry) => entry.level === 'red' && !seen.has(entry.notification_id))
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => b.entry.at.localeCompare(a.entry.at) || a.index - b.index)
    .map(({ entry }) => entry);
}
