import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import type { Alert } from '../api/client';
import { ExportButton } from './ExportButton';

/** Erste offene rote Meldung, sonst die erste offene (Ziel von „Quittieren“ in der Aktionsleiste). */
export function firstAlertToAcknowledge(alerts: readonly Alert[]): Alert | undefined {
  const open = alerts.filter((alert) => alert.status === 'open');
  return open.find((alert) => alert.level === 'red') ?? open[0];
}

/**
 * Aktionsleiste des Cockpits: „Quittieren“ springt zur ersten offenen roten Meldung (Fokus auf deren
 * Quittieren-Knopf), „CTCAE-Aufnahme“ öffnet die Aufnahme, „Bericht“ die Druckansicht und
 * „FHIR-Bundle“ lädt den Export herunter.
 */
export function CockpitActions({
  patientId,
  pseudonym,
  alerts,
}: {
  patientId: string;
  pseudonym: string;
  alerts: readonly Alert[];
}) {
  const { t } = useTranslation();
  const target = firstAlertToAcknowledge(alerts);

  function jump() {
    if (!target) return;
    const button = document.getElementById(`ack-${target.alert_id}`);
    button?.scrollIntoView?.({ block: 'center' });
    button?.focus();
  }

  return (
    <nav
      aria-label={t('waechter.clinic.actions.title')}
      className="flex min-w-0 flex-1 flex-wrap items-center gap-2"
      data-testid="cockpit-actions"
    >
      <Button
        onClick={jump}
        disabled={!target}
        aria-describedby={target ? undefined : 'no-ack-hint'}
      >
        {t('waechter.clinic.actions.acknowledge')}
      </Button>
      <LinkButton to={`/clinic/patients/${encodeURIComponent(patientId)}/assess`} variant="primary">
        {t('waechter.clinic.actions.assess')}
      </LinkButton>
      <LinkButton to={`/clinic/patients/${encodeURIComponent(patientId)}/report`}>
        {t('waechter.clinic.actions.report')}
      </LinkButton>
      <ExportButton patientId={patientId} pseudonym={pseudonym} />
      {target ? null : (
        <span id="no-ack-hint" className="text-base text-muted">
          {t('waechter.clinic.actions.noOpenAlert')}
        </span>
      )}
    </nav>
  );
}
