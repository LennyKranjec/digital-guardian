import { useTranslation } from 'react-i18next';

import { FhirActions } from './ExportButton';

/**
 * „FHIR-Export und -Senden“ im Cockpit: eingeklappt unter dem Raster (wie der Triage-Befund), damit die
 * Aktionsleiste und der erste Bildschirm (S5) unverändert bleiben.
 */
export function FhirPanel({ patientId, pseudonym }: { patientId: string; pseudonym: string }) {
  const { t } = useTranslation();
  return (
    <details data-testid="fhir-panel" className="rounded-lg border border-border bg-surface px-3">
      <summary className="inline-flex min-h-11 w-full cursor-pointer items-center text-base font-semibold">
        {t('waechter.clinic.actions.fhirMore')}
      </summary>
      <div className="space-y-2 pb-3">
        <p className="m-0 text-base text-muted">{t('waechter.clinic.actions.fhirMoreHint')}</p>
        <FhirActions patientId={patientId} pseudonym={pseudonym} />
      </div>
    </details>
  );
}
