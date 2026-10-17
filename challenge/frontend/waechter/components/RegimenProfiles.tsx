import { useTranslation } from 'react-i18next';

import { localized, type ConfigBundle, type Lang } from '../api/client';

/**
 * Fragebogen-Profile je Therapie (schreibgeschützt): zeigt, dass die Auswahl der Fragen aus der
 * Medikation folgt – Wirkstoffe (ATC) und die dazu gehörenden Symptome.
 */
export function RegimenProfiles({ config, lang }: { config: ConfigBundle; lang: Lang }) {
  const { t } = useTranslation();
  const symptomLabel = (key: string) =>
    localized(config.items.items.find((item) => item.symptom_key === key)?.label, lang) || key;
  const coreKeys = config.items.items.filter((item) => item.core).map((item) => item.symptom_key);

  return (
    <section aria-labelledby="profiles-title" className="space-y-3" data-testid="regimen-profiles">
      <h2 id="profiles-title" className="text-lg font-semibold">
        {t('waechter.clinic.settings.profiles.title')}
      </h2>
      <p className="text-base text-muted">{t('waechter.clinic.settings.profiles.intro')}</p>
      {coreKeys.length > 0 ? (
        <p className="text-base" data-testid="core-symptoms">
          <span className="font-semibold">{t('waechter.clinic.settings.profiles.core')}: </span>
          {coreKeys.map(symptomLabel).join(', ')}
        </p>
      ) : null}
      <ul className="m-0 list-none space-y-3 p-0">
        {config.regimens.regimens.map((regimen) => {
          const profile = regimen.symptom_keys ?? [];
          return (
            <li
              key={regimen.id}
              data-testid="regimen-card"
              className="space-y-2 rounded-lg border border-border bg-surface p-4"
            >
              <h3 className="break-words text-base font-semibold">
                {localized(regimen.label, lang)}
              </h3>
              <p className="break-words text-base">
                <span className="text-muted">{t('waechter.clinic.cockpit.drugs')}: </span>
                {(regimen.drugs ?? [])
                  .map((drug) => (drug.atc ? `${drug.name} (${drug.atc})` : drug.name))
                  .join(', ') || t('waechter.clinic.cockpit.noValue')}
              </p>
              {regimen.cycle_length_days ? (
                <p className="text-base">
                  <span className="text-muted">
                    {t('waechter.clinic.settings.profiles.cycle')}:{' '}
                  </span>
                  {t('waechter.clinic.settings.profiles.days', {
                    count: regimen.cycle_length_days,
                  })}
                </p>
              ) : null}
              <p className="break-words text-base">
                <span className="text-muted">
                  {t('waechter.clinic.settings.profiles.symptoms')}:{' '}
                </span>
                {profile.map(symptomLabel).join(', ') || t('waechter.clinic.cockpit.noValue')}
              </p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
