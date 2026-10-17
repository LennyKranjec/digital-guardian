import { useTranslation } from 'react-i18next';

import type { Progress } from '../model/checkin';
import { PatientProgressBar } from './PatientProgressBar';

/** „x von y beantwortet“ als Text und Balken mit Igel Bodlík (Text trägt die Aussage, nie nur Farbe/Länge). */
export function ProgressStatus({ progress }: { progress: Progress }) {
  const { t } = useTranslation();
  const text =
    t('waechter.patient.progress', { answered: progress.answered, total: progress.total }) +
    (progress.skipped > 0
      ? ` · ${t('waechter.patient.progressSkipped', { count: progress.skipped })}`
      : '');
  return (
    <div role="status" data-testid="checkin-progress">
      <PatientProgressBar
        value={progress.answered}
        max={progress.total}
        valueText={text}
        label={text}
      />
    </div>
  );
}
