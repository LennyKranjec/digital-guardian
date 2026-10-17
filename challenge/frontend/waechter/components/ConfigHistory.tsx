import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { SkeletonBlock } from '../../../../platform/frontend/src/shared/ui/StateViews';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { useConfigHistory } from '../hooks/useSettings';
import { formatAbsolute } from '../model/time';

const COLUMNS = ['version', 'changedAt', 'changedBy', 'note', 'state'] as const;
/** Zelle: als Karte Zeile mit Beschriftung davor, ab 640 px Tabellenzelle. */
const CELL =
  'block break-words px-2 py-1 text-left align-top text-base before:mr-1 before:font-semibold before:text-muted before:content-[attr(data-label)] sm:table-cell sm:py-2 sm:before:content-none';

/**
 * Versionshistorie einer Konfiguration (wer, wann, Notiz, aktiv). Fehlt die Route im Backend (404),
 * steht ein ehrlicher Hinweis statt eines leeren Bereichs.
 */
export function ConfigHistory({ kind, locale }: { kind: 'rules' | 'report'; locale: string }) {
  const { t } = useTranslation();
  const query = useConfigHistory(kind);
  const title = t(`waechter.clinic.settings.history.${kind}`);

  return (
    <section aria-label={title} data-testid={`history-${kind}`} className="space-y-2">
      <h3 className="text-base font-semibold">{title}</h3>
      {query.isPending ? <SkeletonBlock lines={3} /> : null}
      {query.isError ? (
        <div className="space-y-2" role="status">
          <p className="text-base text-muted">
            {query.error instanceof ApiClientError && query.error.status === 404
              ? t('waechter.clinic.settings.history.unavailable')
              : t('waechter.clinic.settings.history.error')}
          </p>
          <Button variant="secondary" onClick={() => void query.refetch()}>
            {t('states.retry')}
          </Button>
        </div>
      ) : null}
      {query.data && query.data.length === 0 ? (
        <p className="text-base text-muted">{t('waechter.clinic.settings.history.empty')}</p>
      ) : null}
      {query.data && query.data.length > 0 ? (
        // Unter 640 px werden die Zeilen zu Karten (Beschriftung je Zelle per data-label), darüber Tabelle.
        // Die Rollen halten die Tabellensemantik, obwohl display:block sie in manchen Browsern auflöst.
        <table role="table" className="block w-full border-collapse sm:table sm:table-fixed">
          <thead role="rowgroup" className="sr-only sm:not-sr-only sm:table-header-group">
            <tr role="row" className="border-b border-border-strong">
              {COLUMNS.map((key) => (
                <th
                  key={key}
                  role="columnheader"
                  scope="col"
                  className="px-2 py-2 text-left text-base font-semibold text-muted"
                >
                  {t(`waechter.clinic.settings.history.columns.${key}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody role="rowgroup" className="block sm:table-row-group">
            {query.data.map((row) => (
              <tr
                key={row.version}
                role="row"
                data-active={row.active}
                className="mb-2 block rounded-md border border-border p-2 sm:mb-0 sm:table-row sm:rounded-none sm:border-0 sm:border-b sm:p-0"
              >
                <th
                  role="rowheader"
                  scope="row"
                  data-label={t('waechter.clinic.settings.history.columns.version')}
                  className={`${CELL} font-normal`}
                >
                  {row.version}
                </th>
                <td
                  role="cell"
                  data-label={t('waechter.clinic.settings.history.columns.changedAt')}
                  className={CELL}
                >
                  {formatAbsolute(row.changed_at, locale)}
                </td>
                <td
                  role="cell"
                  data-label={t('waechter.clinic.settings.history.columns.changedBy')}
                  className={CELL}
                >
                  {row.changed_by ?? '–'}
                </td>
                <td
                  role="cell"
                  data-label={t('waechter.clinic.settings.history.columns.note')}
                  className={CELL}
                >
                  {row.change_note ?? '–'}
                </td>
                <td
                  role="cell"
                  data-label={t('waechter.clinic.settings.history.columns.state')}
                  className={`${CELL} font-semibold`}
                >
                  {row.active
                    ? t('waechter.clinic.settings.history.activeNow')
                    : t('waechter.clinic.settings.history.replaced')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}
