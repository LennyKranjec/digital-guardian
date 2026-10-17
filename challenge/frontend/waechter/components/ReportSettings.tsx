import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { REPORT_SECTIONS, REPORT_SINCE, type ReportFile, type ReportSince } from '../api/client';
import { settingsErrorKey, useUpdateReport } from '../hooks/useSettings';
import {
  normalizeSections,
  reportChanged,
  toggleSection,
  type ReportDraft,
} from '../model/settings';
import { ConfigHistory } from './ConfigHistory';

/**
 * Berichtsinhalt: Abschnitte (Checkboxen) und Zeitraum. Ärztinnen sehen die Auswahl schreibgeschützt,
 * Administration speichert eine neue Version (`PUT /config/report`, bedingt über `expected_version`).
 */
export function ReportSettings({
  report,
  editable,
  locale,
}: {
  report: ReportFile;
  editable: boolean;
  locale: string;
}) {
  const { t } = useTranslation();
  const update = useUpdateReport();
  const [draft, setDraft] = useState<ReportDraft>({
    since: report.since ?? 'last_visit',
    sections: normalizeSections(report.sections),
  });
  const changed = reportChanged(report, draft);
  const errorKey = update.isError ? settingsErrorKey(update.error) : null;

  return (
    <section
      aria-labelledby="report-settings-title"
      className="space-y-3"
      data-testid="report-settings"
    >
      <h2 id="report-settings-title" className="text-lg font-semibold">
        {t('waechter.clinic.settings.report.title')}
      </h2>
      <p className="text-base text-muted">
        {t('waechter.clinic.settings.report.version', { version: report.version })}
      </p>
      <fieldset className="m-0 min-w-0 space-y-2 border-0 p-0">
        <legend className="text-base font-semibold">
          {t('waechter.clinic.settings.report.sections')}
        </legend>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {REPORT_SECTIONS.map((section) => (
            <label
              key={section}
              className="flex min-h-11 min-w-0 cursor-pointer items-center gap-3 rounded-md border border-border-strong bg-surface px-3 py-2 text-base has-[:disabled]:cursor-default has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2"
            >
              <input
                type="checkbox"
                className="size-5 shrink-0"
                checked={draft.sections.includes(section)}
                disabled={!editable}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    sections: toggleSection(current.sections, section, event.target.checked),
                  }))
                }
              />
              <span className="min-w-0 break-words">
                {t(`waechter.clinic.report.sections.${section}`)}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="space-y-1">
        <label htmlFor="report-since" className="block text-base font-semibold">
          {t('waechter.clinic.settings.report.since')}
        </label>
        <select
          id="report-since"
          value={draft.since}
          disabled={!editable}
          onChange={(event) =>
            setDraft((current) => ({ ...current, since: event.target.value as ReportSince }))
          }
          className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink sm:max-w-xs"
        >
          {REPORT_SINCE.map((option) => (
            <option key={option} value={option}>
              {t(`waechter.clinic.settings.report.sinceOptions.${option}`)}
            </option>
          ))}
        </select>
      </div>
      {editable ? (
        <div className="space-y-2">
          {errorKey ? (
            <p role="alert" className="rounded-md border border-danger p-3 text-base font-semibold">
              {t(`waechter.clinic.settings.errors.${errorKey}`)}
            </p>
          ) : null}
          {update.isSuccess ? (
            <p role="status" className="text-base font-semibold" data-testid="report-saved">
              {t('waechter.clinic.settings.report.saved', { version: update.data.version })}
            </p>
          ) : null}
          <Button
            disabled={!changed || update.isPending}
            onClick={() =>
              update.mutate({
                expected_version: report.version,
                report: { since: draft.since, sections: [...draft.sections] },
              })
            }
          >
            {update.isPending
              ? t('waechter.clinic.settings.saving')
              : t('waechter.clinic.settings.report.save')}
          </Button>
        </div>
      ) : null}
      <ConfigHistory kind="report" locale={locale} />
    </section>
  );
}
