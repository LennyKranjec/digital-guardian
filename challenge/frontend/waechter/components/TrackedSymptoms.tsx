import { useTranslation } from 'react-i18next';

import type { TrackedSymptom } from '../api/client';

/**
 * „Sledované příznaky / Tracked symptoms / Beobachtete Symptome“: die Symptome des aktuellen
 * Fragebogens, also der CTCAE-Subraum der Ärztin (derselbe wie in der Aufnahmevorlage). Ohne Eintrag
 * entfällt die Zeile. Reine Anzeige, die Liste kommt vom Server.
 */
export function TrackedSymptoms({
  symptoms,
  testId = 'tracked-symptoms',
}: {
  symptoms: readonly TrackedSymptom[] | null | undefined;
  testId?: string;
}) {
  const { t } = useTranslation();
  if (!symptoms || symptoms.length === 0) return null;
  const list = symptoms.map((symptom) => symptom.label).join(', ');
  // A3 INT-5 (S5): genau eine Zeile, Rest abgeschnitten; volle Liste im title (1366×768 ohne Scrollen).
  return (
    <p
      data-testid={testId}
      className="m-0 truncate text-base text-muted"
      title={`${t('waechter.clinic.tracked.label')}: ${list}`}
    >
      <span className="font-semibold">{t('waechter.clinic.tracked.label')}:</span> {list}
    </p>
  );
}
