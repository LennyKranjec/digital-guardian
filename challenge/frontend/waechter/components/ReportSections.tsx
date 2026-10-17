import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { formatAbsolute, formatDay } from '../model/time';
import { pragueDayStartMs } from '../model/timeline';
import { footnoteOrder, useAudit, useFootnoteFacts } from '../hooks/useReport';
import type { Assessment, Overview, Timeline } from '../api/client';
import { CardTable } from './CardTable';
import { LevelBadge } from './LevelBadge';
import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';

export function ReportSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={`report-${id}`}
      data-testid={`report-section-${id}`}
      className="space-y-3 break-inside-avoid"
    >
      <h2 id={`report-${id}`} className="text-lg font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** Therapie: Regime, Wirkstoffe, Zyklustag, Termine, letzte Eingabe. */
export function TherapyBlock({ overview, locale }: { overview: Overview; locale: string }) {
  const { t } = useTranslation();
  const { therapy } = overview;
  const none = t('waechter.clinic.cockpit.noValue');
  const rows: [string, string][] = [
    [t('waechter.clinic.cockpit.therapy'), therapy.regimen_label ?? therapy.regimen_id],
    [
      t('waechter.clinic.cockpit.drugs'),
      (therapy.drugs ?? [])
        .map((drug) => (drug.atc ? `${drug.name} (${drug.atc})` : drug.name))
        .join(', ') || none,
    ],
    [
      t('waechter.clinic.settings.profiles.cycle'),
      therapy.cycle_day === null || therapy.cycle_day === undefined
        ? none
        : t('waechter.clinic.cycleDay', { day: therapy.cycle_day }),
    ],
    [
      t('waechter.clinic.cockpit.lastVisit'),
      overview.last_visit_at ? formatAbsolute(overview.last_visit_at, locale) : none,
    ],
    [
      t('waechter.clinic.cockpit.nextVisit'),
      overview.next_visit_at ? formatAbsolute(overview.next_visit_at, locale) : none,
    ],
    [
      t('waechter.clinic.cockpit.lastResponse'),
      overview.last_response_at ? formatAbsolute(overview.last_response_at, locale) : none,
    ],
  ];
  return (
    <dl className="m-0 grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-x-4 gap-y-1 text-base">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted">{label}</dt>
          <dd className="m-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** KI-Kurzfassung: Sätze mit Fußnotennummern, darunter die Belege (Datum, Beschriftung, Kennung). */
export function SummaryBlock({
  overview,
  patientId,
  locale,
}: {
  overview: Overview;
  patientId: string;
  locale: string;
}) {
  const { t } = useTranslation();
  const summary = overview.summary;
  const order = footnoteOrder(summary?.sentences ?? []);
  const facts = useFootnoteFacts(patientId, order);
  if (!summary) return <p className="text-base text-muted">{t('waechter.clinic.summary.none')}</p>;
  return (
    <div className="space-y-3">
      <p className="rounded-md border border-border-strong p-3 text-base font-semibold">
        {t(`waechter.${summary.disclaimer_key}`, {
          defaultValue: t('waechter.clinic.summary.draft'),
        })}
      </p>
      <p className="text-base text-muted">
        {t('waechter.clinic.report.summaryMeta', {
          generator: summary.generator,
          mode: t(`waechter.clinic.summary.modes.${summary.mode}`),
          date: formatAbsolute(summary.generated_at, locale),
          dropped: summary.dropped_sentences,
        })}
      </p>
      <ol className="m-0 list-decimal space-y-2 pl-6">
        {summary.sentences.map((sentence, index) => (
          <li key={`${index}-${sentence.text}`} className="break-words text-base">
            {sentence.text}
            {sentence.refs.map((ref) => (
              <sup key={ref} className="ml-0.5 text-base font-semibold leading-none">
                [{order.indexOf(ref) + 1}]
              </sup>
            ))}
            {sentence.verified ? null : (
              <span className="font-semibold"> ({t('waechter.clinic.summary.unverified')})</span>
            )}
          </li>
        ))}
      </ol>
      {summary.unknown_topics && summary.unknown_topics.length > 0 ? (
        <p className="text-base">
          <span className="font-semibold">{t('waechter.clinic.summary.unknown')} </span>
          {summary.unknown_topics.join(', ')}
        </p>
      ) : null}
      {order.length > 0 ? (
        <div data-testid="footnotes" className="space-y-1">
          <h3 className="text-base font-semibold">{t('waechter.clinic.report.footnotes')}</h3>
          <ol className="m-0 list-none space-y-1 p-0 text-base">
            {order.map((ref, index) => {
              const fact = facts[index]?.data;
              return (
                <li key={ref} className="break-words">
                  [{index + 1}]{' '}
                  {fact
                    ? t('waechter.clinic.report.footnote', {
                        label: fact.label,
                        date: formatAbsolute(fact.at, locale),
                        id: ref,
                      })
                    : t('waechter.clinic.report.footnoteUnavailable', { id: ref })}
                </li>
              );
            })}
          </ol>
        </div>
      ) : null}
    </div>
  );
}

/** Meldungen im Zeitraum: Stufe, Text, Status (offen/quittiert mit wer/wann/Entscheidung). */
export function AlertsBlock({ timeline, locale }: { timeline: Timeline; locale: string }) {
  const { t } = useTranslation();
  const alerts = [...timeline.alerts].sort((a, b) => a.created_at.localeCompare(b.created_at));
  if (alerts.length === 0)
    return <p className="text-base text-muted">{t('waechter.clinic.report.alertsNone')}</p>;
  const columns = (['time', 'level', 'alert', 'state'] as const).map((key) => ({
    key,
    label: t(`waechter.clinic.report.alertColumns.${key}`),
  }));
  const rows = alerts.map((alert) => {
    const ack = alert.acknowledgement;
    return {
      id: alert.alert_id,
      cells: [
        formatAbsolute(alert.created_at, locale),
        <LevelBadge key="level" level={alert.level} />,
        alert.headline ?? alert.rule_id,
        alert.status === 'open' ? (
          <span key="state" className="font-semibold">
            {t('waechter.clinic.report.stateOpen')}
          </span>
        ) : (
          <span key="state">
            <span className="font-semibold">{t('waechter.clinic.report.stateAcknowledged')}</span>
            {ack?.by ? (
              <span className="block">
                {t('waechter.clinic.ack.by', {
                  by: ack.by,
                  date: ack.at ? formatAbsolute(ack.at, locale) : '–',
                })}
              </span>
            ) : null}
            {ack?.decision ? (
              <span className="block">
                {t('waechter.clinic.ack.decisionLine', {
                  decision: t(`waechter.clinic.ack.decisions.${ack.decision}`),
                })}
              </span>
            ) : null}
          </span>
        ),
      ],
    };
  });
  return (
    <CardTable label={t('waechter.clinic.report.sections.alerts')} columns={columns} rows={rows} />
  );
}

/** Arztaufnahmen (CTCAE) im Zeitraum. */
export function AssessmentsBlock({
  assessments,
  locale,
}: {
  assessments: readonly Assessment[];
  locale: string;
}) {
  const { t } = useTranslation();
  if (assessments.length === 0) {
    return <p className="text-base text-muted">{t('waechter.clinic.report.assessmentsNone')}</p>;
  }
  const columns = (['time', 'by', 'items'] as const).map((key) => ({
    key,
    label: t(`waechter.clinic.report.assessmentColumns.${key}`),
  }));
  const rows = assessments.map((assessment) => ({
    id: assessment.assessment_id,
    cells: [
      formatAbsolute(assessment.assessed_at, locale),
      assessment.assessed_by ?? '–',
      <span key="items">
        {assessment.items.map((item) => (
          <span key={item.ctcae_term_id} className="block">
            {t('waechter.clinic.timeline.events.gradeItem', {
              term: item.term_en ?? item.ctcae_term_id,
              grade: item.grade,
            })}
            {item.attribution
              ? ` · ${t(`waechter.clinic.assess.attributions.${item.attribution}`, { defaultValue: item.attribution })}`
              : ''}
            {item.note ? ` · ${item.note}` : ''}
          </span>
        ))}
      </span>,
    ],
  }));
  return (
    <CardTable
      label={t('waechter.clinic.report.sections.assessments')}
      columns={columns}
      rows={rows}
    />
  );
}

/** Fehlende Daten: Tage ohne Eingabe, Tage seit der letzten Eingabe, ausstehende Auswertung, unbekannte Themen. */
export function MissingBlock({
  timeline,
  overview,
  locale,
}: {
  timeline: Timeline;
  overview: Overview;
  locale: string;
}) {
  const { t } = useTranslation();
  const days = timeline.missing_days
    .map((date) => ({ date, ms: pragueDayStartMs(date) }))
    .filter((entry): entry is { date: string; ms: number } => entry.ms !== null);
  const unknown = overview.summary?.unknown_topics ?? [];
  const nothing =
    days.length === 0 &&
    unknown.length === 0 &&
    !overview.evaluation_pending &&
    (overview.days_without_response === null || overview.days_without_response === undefined);
  if (nothing)
    return <p className="text-base text-muted">{t('waechter.clinic.report.missingNone')}</p>;
  return (
    <ul className="m-0 list-disc space-y-1 pl-6 text-base">
      {days.length > 0 ? (
        <li data-testid="missing-days">
          {t('waechter.clinic.report.missingDays', {
            dates: days.map((entry) => formatDay(entry.ms, locale)).join(', '),
          })}
        </li>
      ) : null}
      {overview.days_without_response !== null && overview.days_without_response !== undefined ? (
        <li>{t('waechter.clinic.daysWithout', { count: overview.days_without_response })}</li>
      ) : null}
      {overview.evaluation_pending ? (
        <li>{t('waechter.clinic.alerts.evaluationPending')}</li>
      ) : null}
      {unknown.length > 0 ? (
        <li>
          {t('waechter.clinic.summary.unknown')} {unknown.join(', ')}
        </li>
      ) : null}
    </ul>
  );
}

/** Audit-Auszug (letzte Einträge). Fehlt die Route oder die Berechtigung, steht ein Hinweis statt Fehler. */
export function AuditBlock({ patientId, locale }: { patientId: string; locale: string }) {
  const { t } = useTranslation();
  const query = useAudit(patientId, true);
  if (query.isPending) return <p className="text-base text-muted">{t('states.loading')}</p>;
  if (query.isError) {
    return (
      <p className="text-base text-muted" data-testid="audit-unavailable">
        {query.error instanceof ApiClientError && [403, 404].includes(query.error.status)
          ? t('waechter.clinic.report.auditUnavailable')
          : t('waechter.clinic.report.auditError')}
      </p>
    );
  }
  const rows = [...query.data].sort((a, b) => b.at.localeCompare(a.at)).slice(0, 10);
  if (rows.length === 0)
    return <p className="text-base text-muted">{t('waechter.clinic.report.auditNone')}</p>;
  const columns = (['at', 'role', 'action', 'target'] as const).map((key) => ({
    key,
    label: t(`waechter.clinic.report.auditColumns.${key}`),
  }));
  const cardRows = rows.map((row, index) => ({
    id: `${row.at}-${row.action}-${index}`,
    cells: [
      formatAbsolute(row.at, locale),
      row.actor_role ?? '–',
      row.action,
      [row.target_type, row.target_id].filter(Boolean).join(' ') || '–',
    ],
  }));
  return (
    <CardTable
      label={t('waechter.clinic.report.sections.audit')}
      columns={columns}
      rows={cardRows}
    />
  );
}
