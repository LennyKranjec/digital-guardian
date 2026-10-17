import { useTranslation } from 'react-i18next';

import type { SinceLastVisitRow } from '../api/client';
import { useMediaQuery } from '../hooks/useMediaQuery';

const ARROW: Record<NonNullable<SinceLastVisitRow['direction']>, string> = {
  up: '↑',
  down: '↓',
  flat: '→',
  unknown: '?',
};

function useRowText() {
  const { t } = useTranslation();
  const value = (entry: number | null | undefined) =>
    entry === null || entry === undefined ? t('waechter.clinic.since.noValue') : String(entry);
  return {
    t,
    range: (row: SinceLastVisitRow) => `${value(row.first)} → ${value(row.last)}`,
    max: (row: SinceLastVisitRow) => value(row.max),
    attribute: (row: SinceLastVisitRow) =>
      row.attribute
        ? t(`waechter.clinic.since.attr.${row.attribute}`, { defaultValue: row.attribute })
        : '',
  };
}

/** Verlaufsrichtung als Pfeil und Text (nie nur Pfeil oder Farbe). */
function Direction({ direction = 'unknown' }: { direction?: SinceLastVisitRow['direction'] }) {
  const { t } = useTranslation();
  return (
    <span className="whitespace-normal">
      <span aria-hidden="true">{ARROW[direction ?? 'unknown']} </span>
      {t(`waechter.clinic.since.dir.${direction ?? 'unknown'}`)}
    </span>
  );
}

/** „Seit dem letzten Termin“: je Symptom erster → letzter Wert, Maximum, Richtung, Meldungen, fehlende Tage. */
export function SinceLastVisitTable({ rows }: { rows: readonly SinceLastVisitRow[] }) {
  const wide = useMediaQuery('(min-width: 768px)');
  const text = useRowText();
  const { t } = text;

  return (
    <section aria-labelledby="since-title" className="space-y-3">
      <h2 id="since-title" className="text-lg font-semibold">
        {t('waechter.clinic.since.title')}
      </h2>
      {rows.length === 0 ? (
        <p className="text-base text-muted">{t('waechter.clinic.since.empty')}</p>
      ) : wide ? (
        <table className="w-full table-fixed border-collapse" data-testid="since-table">
          <thead>
            <tr className="border-b border-border-strong">
              {(['symptom', 'range', 'max', 'direction', 'alerts', 'missing'] as const).map(
                (key) => (
                  <th
                    key={key}
                    scope="col"
                    className="px-3 py-2 text-left text-base font-semibold text-muted"
                  >
                    {t(`waechter.clinic.since.${key}`)}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={`${row.symptom_key}-${row.attribute ?? ''}`}
                className="border-b border-border"
              >
                <th scope="row" className="px-3 py-2 text-left align-top text-base font-semibold">
                  {row.label}
                  <span className="block font-normal text-muted">{text.attribute(row)}</span>
                </th>
                <td className="px-3 py-2 align-top text-base tabular">{text.range(row)}</td>
                <td className="px-3 py-2 align-top text-base tabular">{text.max(row)}</td>
                <td className="px-3 py-2 align-top text-base">
                  <Direction direction={row.direction} />
                </td>
                <td className="px-3 py-2 align-top text-base tabular">{row.alerts ?? 0}</td>
                <td className="px-3 py-2 align-top text-base tabular">{row.missing_days ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ul className="m-0 list-none space-y-3 p-0" data-testid="since-cards">
          {rows.map((row) => (
            <li
              key={`${row.symptom_key}-${row.attribute ?? ''}`}
              className="rounded-lg border border-border bg-surface p-4"
            >
              <p className="text-base font-semibold">
                {row.label}
                <span className="block font-normal text-muted">{text.attribute(row)}</span>
              </p>
              <dl className="m-0 mt-2 grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 text-base">
                <dt className="text-muted">{t('waechter.clinic.since.range')}</dt>
                <dd className="m-0 text-right tabular">{text.range(row)}</dd>
                <dt className="text-muted">{t('waechter.clinic.since.max')}</dt>
                <dd className="m-0 text-right tabular">{text.max(row)}</dd>
                <dt className="text-muted">{t('waechter.clinic.since.direction')}</dt>
                <dd className="m-0 text-right">
                  <Direction direction={row.direction} />
                </dd>
                <dt className="text-muted">{t('waechter.clinic.since.alerts')}</dt>
                <dd className="m-0 text-right tabular">{row.alerts ?? 0}</dd>
                <dt className="text-muted">{t('waechter.clinic.since.missing')}</dt>
                <dd className="m-0 text-right tabular">{row.missing_days ?? 0}</dd>
              </dl>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
