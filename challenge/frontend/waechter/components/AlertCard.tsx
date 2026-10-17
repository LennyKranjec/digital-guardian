import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import type { Alert } from '../api/client';
import { alertSymptoms } from '../model/freetext';
import { formatAbsolute } from '../model/time';
import { ExplanationPanel } from './ExplanationPanel';
import { FreeTextMentions } from './FreeTextMentions';
import { TrafficLight } from './TrafficLight';

interface AlertCardProps {
  alert: Alert;
  locale: string;
  persisting: boolean;
  onOpenFact: (factId: string) => void;
  /** Quittieren-Knopf an offenen Meldungen; ohne Angabe gibt es keinen Knopf */
  onAcknowledge?: (alert: Alert) => void;
  /** Erklärung („Warum?“) von Anfang an aufgeklappt (Detailseite) */
  defaultExpanded?: boolean;
}

/** Meldung als Karte: Stufe (Icon + Text), Überschrift, Zeit, „Warum?“, „Quittieren“; quittierte zeigen wer/wann/Entscheidung. */
export function AlertCard({
  alert,
  locale,
  persisting,
  onOpenFact,
  onAcknowledge,
  defaultExpanded = false,
}: AlertCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const titleId = useId();
  const panelId = useId();
  const ack = alert.acknowledgement;

  return (
    <article
      id={`alert-${alert.alert_id}`}
      aria-labelledby={titleId}
      data-testid="alert-card"
      data-level={alert.level}
      data-status={alert.status}
      className="space-y-1 rounded-lg border border-border bg-surface p-2"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2" data-testid="alert-card-head">
        <div className="min-w-0 flex-1 basis-56 space-y-1">
          <h3
            id={titleId}
            title={alert.headline ?? alert.rule_id}
            className="m-0 break-words text-base font-semibold leading-snug min-[1200px]:line-clamp-2"
          >
            {alert.headline ?? alert.rule_id}
          </h3>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <TrafficLight level={alert.level} />
            <p className="m-0 text-base text-muted">
              <span className="sr-only">{t('waechter.clinic.alerts.created')}: </span>
              <time dateTime={alert.created_at}>{formatAbsolute(alert.created_at, locale)}</time>
            </p>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {alert.status === 'open' && onAcknowledge ? (
            <Button id={`ack-${alert.alert_id}`} onClick={() => onAcknowledge(alert)}>
              {t('waechter.clinic.actions.acknowledge')}
            </Button>
          ) : null}
          <Button
            variant="secondary"
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={() => setExpanded((open) => !open)}
          >
            {t('waechter.clinic.alerts.why')}
          </Button>
        </div>
      </div>
      <FreeTextMentions
        patientId={alert.patient_id}
        symptomKeys={alertSymptoms(alert)}
        locale={locale}
      />
      {alert.status === 'acknowledged' ? (
        <div
          data-testid="ack-info"
          className="flex flex-wrap gap-x-4 gap-y-0 rounded-md border border-border-strong px-3 py-1 text-base"
        >
          <p className="font-semibold">
            {ack?.by
              ? t('waechter.clinic.ack.by', {
                  by: ack.by,
                  date: ack.at ? formatAbsolute(ack.at, locale) : '–',
                })
              : t('waechter.clinic.ack.acknowledged')}
          </p>
          {ack?.decision ? (
            <p>
              {t('waechter.clinic.ack.decisionLine', {
                decision: t(`waechter.clinic.ack.decisions.${ack.decision}`),
              })}
            </p>
          ) : null}
          {ack?.note ? (
            <p className="break-words">{t('waechter.clinic.ack.noteLine', { note: ack.note })}</p>
          ) : null}
        </div>
      ) : null}
      {persisting ? (
        <p role="note" className="m-0 px-1 text-base font-semibold">
          {t('waechter.clinic.alerts.persisting')}
        </p>
      ) : null}
      {expanded ? (
        <ExplanationPanel id={panelId} alert={alert} locale={locale} onOpenFact={onOpenFact} />
      ) : null}
    </article>
  );
}
