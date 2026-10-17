import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  NotFoundState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import type { ReportSince } from '../api/client';
import { ExportButton, FhirActions } from '../components/ExportButton';
import {
  AlertsBlock,
  AssessmentsBlock,
  AuditBlock,
  MissingBlock,
  ReportSection,
  SummaryBlock,
  TherapyBlock,
} from '../components/ReportSections';
import { SinceLastVisitTable } from '../components/SinceLastVisitTable';
import { TimelineEventList } from '../components/TimelineEventList';
import { useOverview } from '../hooks/useCockpit';
import { useLang } from '../hooks/useLang';
import { useServerNow } from '../hooks/useServerNow';
import { useConfig, useTimeline } from '../hooks/useTimeline';
import { normalizeSections } from '../model/settings';
import { formatAbsolute } from '../model/time';
import { domainOf, timelineRange, type RangeMode } from '../model/timeline';

/**
 * Druckansicht: A4, ohne Navigation, mit Fußzeile auf jeder Seite. Die Plattformhülle (Kopfzeile,
 * Navigation, Banner) wird nur beim Drucken ausgeblendet; am Bildschirm bleibt alles bedienbar.
 */
export const PRINT_CSS = `
@page { size: A4; margin: 14mm; }
@media print {
  header, nav, a[href='#main'], [data-testid='demo-banner'], [data-testid='offline-banner'],
  [data-testid='notification-banner'], .no-print { display: none !important; }
  html, body { background: #fff !important; color: #000 !important; }
  main { max-width: none !important; padding: 0 !important; }
  .report-sheet { border: none !important; box-shadow: none !important; padding: 0 0 18mm !important; }
  .report-footer { position: fixed; right: 0; bottom: 0; left: 0; text-align: center; font-size: 12pt; background: #fff; }
  section, table, tr, li { break-inside: avoid; }
}
`;

const SINCE_MODE: Record<ReportSince, RangeMode> = {
  last_visit: 'visit',
  days_14: '14d',
  days_28: '28d',
};

export function ReportPage() {
  const { t } = useTranslation();
  const { patientId = '' } = useParams();
  const lang = useLang();
  const serverNow = useServerNow();
  const overview = useOverview(patientId);
  const config = useConfig();

  const since = config.data?.report.since ?? 'last_visit';
  const range = config.data
    ? timelineRange(SINCE_MODE[since], { serverNow, lastVisitAt: overview.data?.last_visit_at })
    : null;
  // Fehlt die Grundlage (kein Termin / keine Serverzeit), gilt der gesamte Verlauf – und wird so ausgewiesen.
  const wholeHistory = config.data !== undefined && range === null;
  const timeline = useTimeline(patientId, config.data && overview.data ? (range ?? {}) : null);

  const failed = overview.isError || config.isError || timeline.isError;
  const error = overview.error ?? config.error ?? timeline.error;
  const ready = overview.data && config.data && timeline.data;
  const sections = config.data ? normalizeSections(config.data.report.sections) : [];
  const domain = timeline.data ? domainOf(timeline.data) : null;

  return (
    <section aria-labelledby="report-title" className="report mx-auto w-full max-w-4xl space-y-4">
      <style>{PRINT_CSS}</style>
      <div className="no-print flex flex-wrap items-center gap-2" data-testid="report-toolbar">
        <LinkButton to={`/clinic/patients/${encodeURIComponent(patientId)}`}>
          {t('waechter.clinic.assess.back')}
        </LinkButton>
        <Button onClick={() => window.print()} disabled={!ready}>
          {t('waechter.clinic.report.print')}
        </Button>
        {overview.data ? (
          <>
            <ExportButton patientId={patientId} pseudonym={overview.data.patient.pseudonym} />
            <FhirActions patientId={patientId} pseudonym={overview.data.patient.pseudonym} />
          </>
        ) : null}
      </div>

      {ready ? null : (
        <h1 id="report-title" className="text-3xl font-bold leading-tight">
          {t('waechter.clinic.report.title')}
        </h1>
      )}
      {!failed && !ready ? <SkeletonBlock lines={6} /> : null}
      {failed ? (
        error instanceof ApiClientError && error.status === 404 ? (
          <NotFoundState />
        ) : error instanceof ApiClientError && error.status === 403 ? (
          <ForbiddenState />
        ) : (
          <ErrorState
            onRetry={() => {
              void overview.refetch();
              void config.refetch();
              void timeline.refetch();
            }}
          />
        )
      ) : null}

      {ready && overview.data && config.data && timeline.data ? (
        <article
          className="report-sheet space-y-6 rounded-lg border border-border bg-surface p-6"
          data-testid="report-sheet"
        >
          <div className="space-y-2">
            <h1 id="report-title" className="text-3xl font-bold leading-tight">
              {t('waechter.clinic.report.title')}
            </h1>
            <p className="break-words text-lg font-semibold">
              {overview.data.patient.display_name}{' '}
              <span className="font-normal text-muted">
                {overview.data.patient.pseudonym}
                {overview.data.patient.age !== undefined && overview.data.patient.age !== null
                  ? ` · ${t('waechter.clinic.cockpit.age', { age: overview.data.patient.age })}`
                  : ''}
              </span>
            </p>
            <p className="text-base" data-testid="report-period">
              <span className="font-semibold">{t('waechter.clinic.report.period')}: </span>
              {domain
                ? `${formatAbsolute(timeline.data.from, lang)} – ${formatAbsolute(timeline.data.to, lang)}`
                : t('waechter.clinic.report.periodUnknown')}
              {wholeHistory ? ` (${t('waechter.clinic.report.periodWhole')})` : ''}
            </p>
            <p className="text-base text-muted" data-testid="report-meta">
              {serverNow
                ? `${t('waechter.clinic.report.created')}: ${formatAbsolute(serverNow.toISOString(), lang)} · `
                : ''}
              {t('waechter.clinic.report.versions', {
                rules: config.data.rules.version,
                report: config.data.report.version,
              })}
            </p>
          </div>

          {sections.length === 0 ? (
            <EmptyState
              title={t('waechter.clinic.report.noSectionsTitle')}
              body={t('waechter.clinic.report.noSections')}
            />
          ) : null}

          {sections.map((section) => {
            switch (section) {
              case 'therapy':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.therapy')}
                  >
                    <TherapyBlock overview={overview.data} locale={lang} />
                  </ReportSection>
                );
              case 'summary':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.summary')}
                  >
                    <SummaryBlock overview={overview.data} patientId={patientId} locale={lang} />
                  </ReportSection>
                );
              case 'alerts':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.alerts')}
                  >
                    <AlertsBlock timeline={timeline.data} locale={lang} />
                  </ReportSection>
                );
              case 'since_last_visit':
                return (
                  <div key={section} data-testid="report-section-since_last_visit">
                    <SinceLastVisitTable rows={overview.data.since_last_visit} />
                  </div>
                );
              case 'timeline':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.timeline')}
                  >
                    <TimelineEventList
                      timeline={timeline.data}
                      locale={lang}
                      onOpenFact={() => undefined}
                      plain
                    />
                  </ReportSection>
                );
              case 'assessments':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.assessments')}
                  >
                    <AssessmentsBlock assessments={timeline.data.assessments} locale={lang} />
                  </ReportSection>
                );
              case 'missing_data':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.missing_data')}
                  >
                    <MissingBlock timeline={timeline.data} overview={overview.data} locale={lang} />
                  </ReportSection>
                );
              case 'audit':
                return (
                  <ReportSection
                    key={section}
                    id={section}
                    title={t('waechter.clinic.report.sections.audit')}
                  >
                    <AuditBlock patientId={patientId} locale={lang} />
                  </ReportSection>
                );
            }
          })}

          <p
            className="report-footer border-t border-border pt-3 text-center text-base text-muted"
            data-testid="report-footer"
          >
            {t('waechter.clinic.report.footer')}
          </p>
        </article>
      ) : null}
    </section>
  );
}
