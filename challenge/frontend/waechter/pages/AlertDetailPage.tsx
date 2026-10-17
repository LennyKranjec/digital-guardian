import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  ErrorState,
  ForbiddenState,
  NotFoundState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { toLang, type Alert, type Decision } from '../api/client';
import { AcknowledgeDialog } from '../components/AcknowledgeDialog';
import { AlertCard } from '../components/AlertCard';
import { FactDrawer } from '../components/FactDrawer';
import { useAlert } from '../hooks/useAcknowledge';

/**
 * Detailseite einer Meldung (`/clinic/alerts/:id`): Karte mit Begründung („Warum?“ aufgeklappt),
 * Quittieren und Link zur Patientenakte. Fremde oder unbekannte Meldungen ergeben 404 vom Server.
 */
export function AlertDetailPage() {
  const { t, i18n } = useTranslation();
  const { alertId = '' } = useParams();
  const query = useAlert(alertId);
  const locale = toLang(i18n.resolvedLanguage ?? i18n.language);
  const [ack, setAck] = useState<Alert | null>(null);
  const [factId, setFactId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const alert = query.data;

  return (
    <section aria-labelledby="alert-title" className="mx-auto w-full max-w-3xl space-y-4">
      <div className="flex flex-wrap gap-2">
        <LinkButton to="/clinic">{t('waechter.clinic.alertPage.toList')}</LinkButton>
        {alert ? (
          <LinkButton to={`/clinic/patients/${encodeURIComponent(alert.patient_id)}`}>
            {t('waechter.clinic.alertPage.toPatient')}
          </LinkButton>
        ) : null}
      </div>
      <h1 id="alert-title" className="break-words text-3xl font-bold leading-tight">
        {alert?.headline ?? t('waechter.clinic.alertPage.title')}
      </h1>
      {query.isPending ? <SkeletonBlock lines={4} /> : null}
      {query.isError ? (
        query.error instanceof ApiClientError && query.error.status === 404 ? (
          <NotFoundState />
        ) : query.error instanceof ApiClientError && query.error.status === 403 ? (
          <ForbiddenState />
        ) : (
          <ErrorState onRetry={() => void query.refetch()} />
        )
      ) : null}
      {notice ? (
        <p
          role="status"
          data-testid="alert-notice"
          className="rounded-md border border-border-strong bg-surface p-3 text-base font-semibold"
        >
          {notice}
        </p>
      ) : null}
      {alert ? (
        <AlertCard
          alert={alert}
          locale={locale}
          persisting={false}
          defaultExpanded
          onOpenFact={setFactId}
          onAcknowledge={setAck}
        />
      ) : null}
      {ack ? (
        <AcknowledgeDialog
          key={ack.alert_id}
          alert={ack}
          onClose={() => setAck(null)}
          onDone={(acknowledged: Alert, decision: Decision) => {
            setAck(null);
            setNotice(
              t('waechter.clinic.ack.done', {
                headline: acknowledged.headline ?? acknowledged.rule_id,
                decision: t(`waechter.clinic.ack.decisions.${decision}`),
              }),
            );
          }}
        />
      ) : null}
      {factId && alert ? (
        <FactDrawer
          key={factId}
          patientId={alert.patient_id}
          factId={factId}
          locale={locale}
          onClose={() => setFactId(null)}
        />
      ) : null}
    </section>
  );
}
