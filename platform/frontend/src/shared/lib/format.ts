/** Datumsanzeige. Reine Datumswerte (YYYY-MM-DD) bleiben UTC-stabil. */

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function parse(value: string): Date | null {
  const date = new Date(DATE_ONLY.test(value) ? `${value}T00:00:00Z` : value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string, locale: string): string {
  const date = parse(value);
  if (!date) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(date);
}

export function formatDateTime(value: string, locale: string): string {
  const date = parse(value);
  if (!date) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

/** Kurzes Datum für Diagrammachsen. */
export function formatShortDate(value: string, locale: string): string {
  const date = parse(value);
  if (!date) return value;
  return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(date);
}
