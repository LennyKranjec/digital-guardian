import { formatAbsolute, formatRelative } from '../model/time';

export interface TimeProps {
  /** „Jetzt“ laut Server (`waechter.server_now`); ohne Wert nur absolute Zeit */
  now: Date | null;
  locale: string;
}

/**
 * Zeitpunkt relativ (nur gegen Serverzeit) und absolut in Europe/Prague. Fehlt der Zeitpunkt,
 * steht der übergebene Ersatztext („noch keine Eingabe“ …) statt eines leeren Feldes.
 */
export function TimeValue({
  iso,
  empty,
  allowFuture,
  now,
  locale,
}: TimeProps & { iso: string | null | undefined; empty: string; allowFuture: boolean }) {
  if (!iso) return <span>{empty}</span>;
  const relative = now ? formatRelative(iso, now, locale, { allowFuture }) : null;
  return (
    <span className="block min-w-0 break-words">
      {relative ? <span className="block font-semibold">{relative}</span> : null}
      <time dateTime={iso} className="block text-muted">
        {formatAbsolute(iso, locale)}
      </time>
    </span>
  );
}

/**
 * Zeitpunkt in einer Zeile: relativ (nur gegen Serverzeit) und/oder absolut (Europe/Prague).
 * `showAbsolute` ergänzt das Datum hinter der relativen Angabe, `onlyAbsolute` zeigt nur das Datum;
 * ohne Serverzeit steht immer das Datum. Fehlt der Zeitpunkt, steht der Ersatztext.
 */
export function TimeInline({
  iso,
  empty,
  allowFuture,
  now,
  locale,
  showAbsolute = false,
  onlyAbsolute = false,
}: TimeProps & {
  iso: string | null | undefined;
  empty: string;
  allowFuture: boolean;
  showAbsolute?: boolean;
  onlyAbsolute?: boolean;
}) {
  if (!iso) return <span>{empty}</span>;
  const relative = !onlyAbsolute && now ? formatRelative(iso, now, locale, { allowFuture }) : null;
  const absolute = formatAbsolute(iso, locale);
  const withDate = showAbsolute || onlyAbsolute || relative === null;
  return (
    <>
      {relative ? <span className="font-semibold">{relative}</span> : null}
      {withDate ? (
        <time dateTime={iso} className={relative ? 'text-muted' : ''}>
          {relative ? ` (${absolute})` : absolute}
        </time>
      ) : null}
    </>
  );
}
