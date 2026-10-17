import { useTranslation } from 'react-i18next';

import type { AdviceFile } from '../api/client';
import { adviceRows } from '../model/triage';
import { CardTable } from './CardTable';

/**
 * Tipp-Regeln für Patientinnen (Einstellungen, nur lesen): ID, Symptom, Wertebereich, Anzahl Tipps,
 * Quelle und Status. Die Auswertung (welche Regel feuert, Unterdrückung bei Akut) macht der Server;
 * fehlt der Block in der Konfiguration, steht ein ehrlicher Hinweis.
 */
export function AdviceRules({ advice }: { advice: AdviceFile | null | undefined }) {
  const { t } = useTranslation();
  const rows = advice ? adviceRows(advice) : [];

  return (
    <section aria-labelledby="advice-rules-title" className="space-y-3" data-testid="advice-rules">
      <h2 id="advice-rules-title" className="text-lg font-semibold">
        {t('waechter.clinic.settings.adviceRules.title')}
      </h2>
      <p className="text-base text-muted">{t('waechter.clinic.settings.adviceRules.intro')}</p>
      {rows.length === 0 ? (
        <p className="text-base text-muted" data-testid="advice-rules-empty">
          {t('waechter.clinic.settings.adviceRules.none')}
        </p>
      ) : (
        <CardTable
          testId="advice-rules-table"
          label={t('waechter.clinic.settings.adviceRules.title')}
          columns={[
            { key: 'id', label: t('waechter.clinic.settings.adviceRules.columns.id') },
            { key: 'symptom', label: t('waechter.clinic.settings.adviceRules.columns.symptom') },
            { key: 'range', label: t('waechter.clinic.settings.adviceRules.columns.range') },
            { key: 'tips', label: t('waechter.clinic.settings.adviceRules.columns.tips') },
            { key: 'source', label: t('waechter.clinic.settings.adviceRules.columns.source') },
            { key: 'status', label: t('waechter.clinic.settings.adviceRules.columns.status') },
          ]}
          rows={rows.map((row) => ({
            id: row.id,
            cells: [
              row.id,
              row.symptomKey,
              `${row.rangeMin}–${row.rangeMax}`,
              row.tipCount,
              row.sources.join('; ') || '–',
              row.status || '–',
            ],
          }))}
        />
      )}
    </section>
  );
}
