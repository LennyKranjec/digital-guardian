import type { MouseEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { toLang, type WorklistRow } from '../api/client';
import { TimeValue } from './TimeText';
import { TrafficLight } from './TrafficLight';

/**
 * Darstellung der Arbeitsliste: ab 768 px Tabelle, darunter Karten (375 px). Die Reihenfolge
 * liefert der Server (rot > gelb > grau > grün, dann älteste Meldung) und wird nie umsortiert.
 */

export const patientPath = (row: Pick<WorklistRow, 'patient_id'>): string =>
  `/clinic/patients/${encodeURIComponent(row.patient_id)}`;

function PatientIdentity({ row, asLink }: { row: WorklistRow; asLink: boolean }) {
  const { t } = useTranslation();
  const name = <span className="font-semibold underline">{row.display_name}</span>;
  return (
    <span className="block min-w-0 break-words">
      {asLink ? <Link to={patientPath(row)}>{name}</Link> : name}
      <span className="block text-muted">{row.pseudonym}</span>
      {row.synthetic !== false ? (
        <span className="mt-1 inline-block rounded-md border border-border-strong px-2 text-base">
          {t('waechter.clinic.synthetic')}
        </span>
      ) : null}
    </span>
  );
}

function Therapy({ row }: { row: WorklistRow }) {
  const { t } = useTranslation();
  return (
    <span className="block min-w-0 break-words">
      <span className="block">{row.regimen_label ?? row.regimen_id}</span>
      {row.cycle_day !== null && row.cycle_day !== undefined ? (
        <span className="block text-muted">
          {t('waechter.clinic.cycleDay', { day: row.cycle_day })}
        </span>
      ) : null}
    </span>
  );
}

function Alerts({ row }: { row: WorklistRow }) {
  const { t } = useTranslation();
  return (
    <span className="block min-w-0 break-words">
      <span className="block font-semibold">
        {t('waechter.clinic.openAlerts', { count: row.open_alerts })}
      </span>
      <span className="block text-muted">
        {row.top_alert?.headline ?? t('waechter.clinic.noTopAlert')}
      </span>
      {row.persisting ? (
        <span className="block font-semibold">{t('waechter.clinic.alerts.persisting')}</span>
      ) : null}
      {(row.free_text_unconfirmed ?? 0) > 0 ? (
        <span className="block" data-testid="free-text-unconfirmed">
          {t('waechter.clinic.freeTextUnconfirmed', { count: row.free_text_unconfirmed })}
        </span>
      ) : null}
      {row.evaluation_pending ? (
        <span className="block font-semibold">{t('waechter.clinic.pending')}</span>
      ) : null}
    </span>
  );
}

function LastResponse({
  row,
  now,
  locale,
}: {
  row: WorklistRow;
  now: Date | null;
  locale: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <TimeValue
        iso={row.last_response_at}
        empty={t('waechter.clinic.noResponse')}
        allowFuture={false}
        now={now}
        locale={locale}
      />
      {row.days_without_response !== null && row.days_without_response !== undefined ? (
        <span className="block text-muted">
          {t('waechter.clinic.daysWithout', { count: row.days_without_response })}
        </span>
      ) : null}
    </>
  );
}

function useListContext(): { t: ReturnType<typeof useTranslation>['t']; locale: string } {
  const { t, i18n } = useTranslation();
  return { t, locale: toLang(i18n.resolvedLanguage ?? i18n.language) };
}

export function WorklistTable({ rows, now }: { rows: readonly WorklistRow[]; now: Date | null }) {
  const { t, locale } = useListContext();
  const navigate = useNavigate();

  function onRowClick(event: MouseEvent<HTMLTableRowElement>, row: WorklistRow) {
    // Links und Knöpfe in der Zeile behalten ihr eigenes Verhalten.
    if ((event.target as HTMLElement).closest('a, button')) return;
    void navigate(patientPath(row));
  }

  const head = 'px-3 py-2 text-left text-base font-semibold text-muted';
  const cell = 'min-w-0 px-3 py-3 align-top';
  return (
    <table className="w-full table-fixed border-collapse" data-testid="worklist-table">
      <caption className="sr-only">{t('waechter.clinic.listLabel')}</caption>
      <thead>
        <tr className="border-b border-border-strong">
          <th scope="col" className={head}>
            {t('waechter.clinic.columns.light')}
          </th>
          <th scope="col" className={head}>
            {t('waechter.clinic.columns.patient')}
          </th>
          <th scope="col" className={head}>
            {t('waechter.clinic.columns.therapy')}
          </th>
          <th scope="col" className={head}>
            {t('waechter.clinic.columns.alerts')}
          </th>
          <th scope="col" className={head}>
            {t('waechter.clinic.columns.lastResponse')}
          </th>
          <th scope="col" className={head}>
            {t('waechter.clinic.columns.nextVisit')}
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.patient_id}
            data-testid="worklist-row"
            onClick={(event) => onRowClick(event, row)}
            className="cursor-pointer border-b border-border hover:bg-sunken"
          >
            <td className={cell}>
              <TrafficLight level={row.traffic_light} />
            </td>
            <td className={cell}>
              <PatientIdentity row={row} asLink />
            </td>
            <td className={cell}>
              <Therapy row={row} />
            </td>
            <td className={cell}>
              <Alerts row={row} />
            </td>
            <td className={cell}>
              <LastResponse row={row} now={now} locale={locale} />
            </td>
            <td className={cell}>
              <TimeValue
                iso={row.next_visit_at}
                empty={t('waechter.clinic.noVisit')}
                allowFuture
                now={now}
                locale={locale}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CardField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-base text-muted">{label}</dt>
      <dd className="m-0 min-w-0">{children}</dd>
    </div>
  );
}

export function WorklistCards({ rows, now }: { rows: readonly WorklistRow[]; now: Date | null }) {
  const { t, locale } = useListContext();
  return (
    <ul
      className="space-y-3"
      aria-label={t('waechter.clinic.listLabel')}
      data-testid="worklist-cards"
    >
      {rows.map((row) => (
        <li key={row.patient_id} data-testid="worklist-row">
          <Link
            to={patientPath(row)}
            className="block min-w-0 space-y-3 rounded-lg border border-border bg-surface p-4 shadow-card hover:bg-sunken"
          >
            <span className="block">
              <TrafficLight level={row.traffic_light} />
            </span>
            <PatientIdentity row={row} asLink={false} />
            <dl className="m-0 grid grid-cols-1 gap-3">
              <CardField label={t('waechter.clinic.columns.therapy')}>
                <Therapy row={row} />
              </CardField>
              <CardField label={t('waechter.clinic.columns.alerts')}>
                <Alerts row={row} />
              </CardField>
              <CardField label={t('waechter.clinic.columns.lastResponse')}>
                <LastResponse row={row} now={now} locale={locale} />
              </CardField>
              <CardField label={t('waechter.clinic.columns.nextVisit')}>
                <TimeValue
                  iso={row.next_visit_at}
                  empty={t('waechter.clinic.noVisit')}
                  allowFuture
                  now={now}
                  locale={locale}
                />
              </CardField>
            </dl>
          </Link>
        </li>
      ))}
    </ul>
  );
}
