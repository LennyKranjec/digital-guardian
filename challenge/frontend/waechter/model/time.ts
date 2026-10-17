/**
 * Zeitanzeige der Arbeitsliste. Tagesgrenzen und Anzeige in Europe/Prague (Vertrag G-04);
 * „jetzt“ wird übergeben (nie versteckt gelesen), damit Tests auf fester Ankerzeit laufen.
 */

export const DISPLAY_TIME_ZONE = 'Europe/Prague';

export type RelativeUnit = 'minute' | 'hour' | 'day';
export interface RelativeValue {
  /** negativ = Vergangenheit, positiv = Zukunft */
  value: number;
  unit: RelativeUnit;
}

function parse(iso: string): Date | null {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatAbsolute(iso: string, locale: string): string {
  const date = parse(iso);
  if (!date) return iso;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: DISPLAY_TIME_ZONE,
  }).format(date);
}

/** Kalendertag in Prag als Tageszähler (für „Differenz der Kalendertage“). */
function pragueDayNumber(date: Date): number {
  const iso = new Intl.DateTimeFormat('en-CA', {
    timeZone: DISPLAY_TIME_ZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
  const [year, month, day] = iso.split('-').map(Number);
  return Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1) / 86_400_000;
}

/** Minuten unter einer Stunde, Stunden unter 24 h, sonst Differenz der Prager Kalendertage. */
export function relativeValue(iso: string, now: Date): RelativeValue | null {
  const target = parse(iso);
  if (!target) return null;
  const diffMs = target.getTime() - now.getTime();
  const abs = Math.abs(diffMs);
  if (abs < 3_600_000) return { value: Math.trunc(diffMs / 60_000) || 0, unit: 'minute' };
  if (abs < 86_400_000) return { value: Math.trunc(diffMs / 3_600_000) || 0, unit: 'hour' };
  return { value: pragueDayNumber(target) - pragueDayNumber(now), unit: 'day' };
}

/**
 * Relativer Text („vor 3 Stunden“). Zukünftige Zeitpunkte nur mit `allowFuture` (Termine);
 * eine „letzte Eingabe“ in der Zukunft (Uhrabweichung) zeigt nur die absolute Zeit.
 */
export function formatRelative(
  iso: string,
  now: Date,
  locale: string,
  options: { allowFuture?: boolean } = {},
): string | null {
  const relative = relativeValue(iso, now);
  if (!relative) return null;
  if (relative.value > 0 && !options.allowFuture) return null;
  return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(
    relative.value,
    relative.unit,
  );
}

/** Nur das Datum (Prager Kalendertag) eines Zeitpunkts, z. B. für ganze Tage ohne Eingabe. */
export function formatDay(ms: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeZone: DISPLAY_TIME_ZONE,
  }).format(new Date(ms));
}
