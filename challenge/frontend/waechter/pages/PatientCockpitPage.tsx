import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useParams } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  ErrorState,
  ForbiddenState,
  NotFoundState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { toLang, type Alert, type Decision, type Overview } from '../api/client';
import { AcknowledgeDialog } from '../components/AcknowledgeDialog';
import { AlertCard } from '../components/AlertCard';
import { CockpitActions } from '../components/CockpitActions';
import { CockpitHeader } from '../components/CockpitHeader';
import { CockpitTabs } from '../components/CockpitTabs';
import { DocumentsPanel } from '../components/DocumentsPanel';
import { FactDrawer } from '../components/FactDrawer';
import { FhirPanel } from '../components/FhirPanel';
import { FreeTextPanel } from '../components/FreeTextPanel';
import { SinceLastVisitTable } from '../components/SinceLastVisitTable';
import { TimelineCompact } from '../components/TimelineCompact';
import { TimelineSection } from '../components/TimelineSection';
import { SummaryPanel } from '../components/SummaryPanel';
import { TrackedSymptoms } from '../components/TrackedSymptoms';
import { TriagePanel } from '../components/TriagePanel';
import { useGenerateSummary, useOverview, sortAlerts } from '../hooks/useCockpit';
import { useServerNow } from '../hooks/useServerNow';

/** So viele offene Meldungen stehen sofort sichtbar, weitere hinter „Weitere Meldungen“. */
const VISIBLE_ALERTS = 2;

function WatchNotes({ notes }: { notes: readonly string[] }) {
  const { t } = useTranslation();
  if (notes.length === 0) return null;
  return (
    <section aria-labelledby="watch-title" className="space-y-2" data-testid="watch-notes">
      <h2 id="watch-title" className="text-lg font-semibold">
        {t('waechter.clinic.watch.title')}
      </h2>
      <ul className="m-0 list-disc space-y-1 pl-6 text-base">
        {notes.map((note) => (
          <li key={note} className="break-words">
            {note}
          </li>
        ))}
      </ul>
      <p className="text-base text-muted">{t('waechter.clinic.watch.source')}</p>
    </section>
  );
}

/** Navigationszustand von der Aufnahmeseite: Hinweis „Aufnahme gespeichert“. */
function savedFromState(state: unknown): boolean {
  return typeof state === 'object' && state !== null && 'assessmentSaved' in state;
}

function Cockpit({ overview, patientId }: { overview: Overview; patientId: string }) {
  const { t, i18n } = useTranslation();
  const locale = toLang(i18n.resolvedLanguage ?? i18n.language);
  const now = useServerNow();
  const generate = useGenerateSummary(patientId);
  const [factId, setFactId] = useState<string | null>(null);
  const [ackAlert, setAckAlert] = useState<Alert | null>(null);
  const location = useLocation();
  const [notice, setNotice] = useState<string | null>(() =>
    savedFromState(location.state) ? t('waechter.clinic.assess.saved') : null,
  );
  const alerts = sortAlerts(overview.open_alerts);
  const persistingAlerts = sortAlerts(overview.persisting_alerts ?? []);
  const shownAlerts = alerts.slice(0, VISIBLE_ALERTS);
  const moreAlerts = alerts.slice(VISIBLE_ALERTS);

  function alertItems(list: readonly Alert[]) {
    return list.map((alert) => (
      <li key={alert.alert_id}>
        <AlertCard
          alert={alert}
          locale={locale}
          persisting={false}
          onOpenFact={setFactId}
          onAcknowledge={setAckAlert}
        />
      </li>
    ));
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2" data-testid="cockpit-toolbar">
        <LinkButton to="/clinic">{t('waechter.clinic.patient.back')}</LinkButton>
        <CockpitActions
          patientId={patientId}
          pseudonym={overview.patient.pseudonym}
          alerts={overview.open_alerts}
        />
      </div>
      {notice ? (
        <p
          role="status"
          data-testid="cockpit-notice"
          className="rounded-md border border-border-strong bg-surface p-3 text-base font-semibold"
        >
          {notice}
        </p>
      ) : null}
      <div
        data-testid="cockpit-grid"
        className="grid gap-3 min-[1200px]:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] min-[1200px]:items-start"
      >
        <div className="min-w-0 space-y-3">
          <CockpitHeader overview={overview} now={now} locale={locale} />
          <section
            aria-labelledby="alerts-title"
            className="space-y-2"
            data-testid="alerts-section"
          >
            <h2 id="alerts-title" className="m-0 text-lg font-semibold">
              {t('waechter.clinic.alerts.title')}
            </h2>
            <TrackedSymptoms symptoms={overview.tracked_symptoms} />
            {overview.evaluation_pending ? (
              <p
                role="note"
                data-testid="evaluation-pending"
                className="rounded-md border border-border-strong p-3 text-base font-semibold"
              >
                {t('waechter.clinic.alerts.evaluationPending')}
              </p>
            ) : null}
            {overview.persisting && (overview.persisting_alerts ?? []).length === 0 ? (
              <p
                role="note"
                className="rounded-md border border-border-strong p-3 text-base font-semibold"
              >
                {t('waechter.clinic.alerts.persisting')}
              </p>
            ) : null}
            {alerts.length === 0 ? (
              <p className="text-base text-muted">{t('waechter.clinic.alerts.none')}</p>
            ) : (
              <>
                <ul className="m-0 list-none space-y-2 p-0">{alertItems(shownAlerts)}</ul>
                {moreAlerts.length > 0 ? (
                  <details data-testid="more-alerts">
                    <summary className="inline-flex min-h-11 cursor-pointer items-center text-base font-semibold underline">
                      {t('waechter.clinic.alerts.more', { count: moreAlerts.length })}
                    </summary>
                    <ul className="m-0 list-none space-y-2 p-0">{alertItems(moreAlerts)}</ul>
                  </details>
                ) : null}
              </>
            )}
            {persistingAlerts.length > 0 ? (
              <details
                data-testid="persisting-alerts"
                // ohne offene Meldung steht sie sofort sichtbar da (sonst eine Zeile, um Platz zu sparen)
                open={alerts.length === 0}
              >
                <summary className="inline-flex min-h-11 cursor-pointer items-center text-base font-semibold">
                  {t('waechter.clinic.alerts.persistingTitle')}
                  <span className="ml-1 text-muted">({persistingAlerts.length})</span>
                </summary>
                <ul className="m-0 list-none space-y-2 p-0">
                  {persistingAlerts.map((alert) => (
                    <li key={alert.alert_id}>
                      <AlertCard alert={alert} locale={locale} persisting onOpenFact={setFactId} />
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </section>
        </div>
        <div className="min-w-0 space-y-3" data-testid="cockpit-right">
          <SummaryPanel
            summary={overview.summary}
            locale={locale}
            isGenerating={generate.isPending}
            hasError={generate.isError}
            onGenerate={() => generate.mutate()}
            onOpenFact={setFactId}
            tracked={overview.tracked_symptoms}
          />
          <TimelineCompact
            patientId={patientId}
            lastVisitAt={overview.last_visit_at}
            serverNow={now}
          />
        </div>
      </div>
      <CockpitTabs
        label={t('waechter.clinic.patient.tabsLabel')}
        initial="history"
        tabs={[
          {
            id: 'history',
            label: t('waechter.clinic.patient.tabs.history'),
            content: (
              <>
                <SinceLastVisitTable rows={overview.since_last_visit} />
                <TimelineSection
                  patientId={patientId}
                  lastVisitAt={overview.last_visit_at}
                  serverNow={now}
                  locale={locale}
                  onOpenFact={setFactId}
                />
              </>
            ),
          },
          {
            id: 'texts',
            label: t('waechter.clinic.patient.tabs.texts'),
            content: (
              <>
                <FreeTextPanel patientId={patientId} />
                <DocumentsPanel patientId={patientId} />
              </>
            ),
          },
          {
            id: 'triage',
            label: t('waechter.clinic.patient.tabs.triage'),
            content: (
              <>
                <TriagePanel patientId={patientId} />
                <WatchNotes notes={overview.therapy.watch_notes ?? []} />
              </>
            ),
          },
          {
            id: 'export',
            label: t('waechter.clinic.patient.tabs.export'),
            content: <FhirPanel patientId={patientId} pseudonym={overview.patient.pseudonym} />,
          },
        ]}
      />
      {ackAlert ? (
        <AcknowledgeDialog
          key={ackAlert.alert_id}
          alert={ackAlert}
          onClose={() => setAckAlert(null)}
          onDone={(acknowledged: Alert, decision: Decision) => {
            setAckAlert(null);
            setNotice(
              t('waechter.clinic.ack.done', {
                headline: acknowledged.headline ?? acknowledged.rule_id,
                decision: t(`waechter.clinic.ack.decisions.${decision}`),
              }),
            );
          }}
        />
      ) : null}
      {factId ? (
        <FactDrawer
          key={factId}
          patientId={patientId}
          factId={factId}
          locale={locale}
          onClose={() => setFactId(null)}
        />
      ) : null}
    </div>
  );
}

/**
 * Patienten-Cockpit der Ärztin: Lage (Kopfzeile, Ampel), offene Meldungen mit Begründung und
 * KI-Kurzfassung mit Belegen. Fremde oder unbekannte Patientinnen ergeben 404 vom Server.
 */
export function PatientCockpitPage() {
  const { t } = useTranslation();
  const { patientId = '' } = useParams();
  const query = useOverview(patientId);

  return (
    <div className="space-y-4">
      {query.data ? null : (
        <LinkButton to="/clinic">{t('waechter.clinic.patient.back')}</LinkButton>
      )}
      {query.data ? <Cockpit overview={query.data} patientId={patientId} /> : null}
      {query.data ? null : (
        <section aria-labelledby="cockpit-title" className="space-y-4">
          <h1 id="cockpit-title" className="text-3xl font-bold leading-tight">
            {t('waechter.clinic.patient.title')}
          </h1>
          {query.isPending ? <SkeletonBlock lines={6} /> : null}
          {query.isError ? (
            <CockpitError error={query.error} onRetry={() => void query.refetch()} />
          ) : null}
        </section>
      )}
    </div>
  );
}

function CockpitError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (error instanceof ApiClientError && error.status === 404) return <NotFoundState />;
  if (error instanceof ApiClientError && error.status === 403) return <ForbiddenState />;
  return <ErrorState onRetry={onRetry} />;
}
