import { useTranslation } from 'react-i18next';

import { questionNumber } from '../model/session';
import { PatientProgressBar } from './PatientProgressBar';

/**
 * Ruhiger Fortschritt: ein Balken mit dem Igel Bodlík und sichtbarem „x / y“ (Werte aus
 * `progress.asked` / `progress.max`); „Frage x (höchstens y)“ spricht der Screenreader (aria-valuetext).
 * `max` ist nur die Obergrenze, die der Server vorgibt – kein
 * Prozentwert, kein Versprechen, dass so viele Fragen kommen (der Server kann früher stoppen).
 */
export function SessionProgress({ progress }: { progress: { asked: number; max: number } }) {
  const { t } = useTranslation();
  const { current, max } = questionNumber(progress);
  return (
    <div data-testid="session-progress">
      <PatientProgressBar
        value={progress.asked}
        max={progress.max}
        valueText={t('waechter.patient.session.question', { current, max })}
      />
    </div>
  );
}
