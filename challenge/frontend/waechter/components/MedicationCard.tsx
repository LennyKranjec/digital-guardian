import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { Lang, Medication, ConfigBundle } from '../api/client';
import { displayName, isSuklOnly, spcUrl, symptomLabels } from '../model/medications';

/**
 * Arzneimittel als Karte: Handelsname + Wirkstoff, kódSÚKL, ATC, „gefunden über …“ (nur in der Suche),
 * Regime mit den Symptomen des Fragebogens, SPC-Link (neuer Tab), Status und Patientenzahl.
 * Identifikation, nie Regel: nichts hier bestimmt Fragen, Ampel oder Meldungen.
 */
export function MedicationCard({
  medication,
  config,
  lang,
  detailLink = true,
}: {
  medication: Medication;
  config: Pick<ConfigBundle, 'items'> | undefined;
  lang: Lang;
  detailLink?: boolean;
}) {
  const { t } = useTranslation();
  const noValue = t('waechter.clinic.medications.noValue');
  const name = displayName(medication);
  const spc = medication.spc;
  const url = spcUrl(spc?.url);
  const status = medication.status ?? '';
  const suklOnly = isSuklOnly(medication);
  const sukl = medication.sukl;

  return (
    <article
      data-testid="medication-card"
      data-medication={medication.medication_id}
      className="space-y-2 rounded-lg border border-border bg-surface p-4"
    >
      <h2 className="m-0 break-words text-lg font-semibold">
        {detailLink ? (
          <Link
            to={`/clinic/medications/${encodeURIComponent(medication.medication_id)}`}
            className="inline-flex min-h-11 items-center underline"
          >
            {name}
          </Link>
        ) : (
          name
        )}
      </h2>
      {suklOnly ? (
        <p
          className="m-0 rounded-md border border-border-strong p-2 text-base font-semibold"
          data-testid="medication-sukl-only"
        >
          {t('waechter.clinic.medications.suklOnly')}
        </p>
      ) : null}
      {medication.trade_name ? (
        <p className="m-0 break-words text-base" data-testid="medication-inn">
          <span className="text-muted">{t('waechter.clinic.medications.inn')}: </span>
          {medication.inn}
        </p>
      ) : null}
      <dl className="m-0 grid grid-cols-1 gap-x-4 gap-y-1 text-base sm:grid-cols-2">
        <div>
          <dt className="text-muted">{t('waechter.clinic.medications.suklCode')}</dt>
          <dd className="m-0 break-words" data-testid="medication-sukl">
            {medication.sukl_code || noValue}
          </dd>
        </div>
        <div>
          <dt className="text-muted">{t('waechter.clinic.medications.atc')}</dt>
          <dd className="m-0 break-words" data-testid="medication-atc">
            {medication.atc}
          </dd>
        </div>
        {status ? (
          <div>
            <dt className="text-muted">{t('waechter.clinic.medications.status.label')}</dt>
            <dd className="m-0 font-semibold" data-testid="medication-status" data-status={status}>
              {t(`waechter.clinic.medications.status.values.${status}`, { defaultValue: status })}
            </dd>
          </div>
        ) : null}
        {suklOnly && sukl
          ? (['strength', 'form', 'package', 'holder'] as const).map((key) =>
              sukl[key] ? (
                <div key={key}>
                  <dt className="text-muted">{t(`waechter.clinic.medications.sukl.${key}`)}</dt>
                  <dd className="m-0 break-words" data-testid={`medication-sukl-${key}`}>
                    {sukl[key]}
                  </dd>
                </div>
              ) : null,
            )
          : null}
        {!suklOnly && typeof medication.patients_on_regimen === 'number' ? (
          <div>
            <dt className="text-muted">{t('waechter.clinic.medications.patients')}</dt>
            <dd className="m-0" data-testid="medication-patients">
              {medication.patients_on_regimen}
            </dd>
          </div>
        ) : null}
      </dl>
      {medication.match ? (
        <p className="m-0 text-base" data-testid="medication-match" data-match={medication.match}>
          {t('waechter.clinic.medications.foundVia', {
            how: t(`waechter.clinic.medications.match.${medication.match}`),
          })}
        </p>
      ) : null}
      {suklOnly ? null : (
        <section aria-label={t('waechter.clinic.medications.regimens')} className="space-y-1">
          <h3 className="m-0 text-base font-semibold">
            {t('waechter.clinic.medications.regimens')}
          </h3>
          {medication.regimens.length === 0 ? (
            <p className="m-0 text-base text-muted">{noValue}</p>
          ) : (
            <ul className="m-0 list-none space-y-1 p-0" data-testid="medication-regimens">
              {medication.regimens.map((regimen) => {
                const symptoms = symptomLabels(regimen.symptom_keys, config, lang);
                return (
                  <li key={regimen.regimen_id} className="break-words text-base">
                    <span className="font-semibold">{regimen.label || regimen.regimen_id}</span>
                    {symptoms.length > 0 ? (
                      <span className="text-muted">
                        {' – '}
                        {t('waechter.clinic.medications.symptoms')}: {symptoms.join(', ')}
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      )}
      {spc ? (
        <p className="m-0 text-base" data-testid="medication-spc">
          <span className="text-muted">{t('waechter.clinic.medications.spc')}: </span>
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center break-words underline"
            >
              {spc.title || url}
              <span className="sr-only"> ({t('waechter.clinic.medications.newTab')})</span>
            </a>
          ) : (
            (spc.title ?? noValue)
          )}
        </p>
      ) : null}
    </article>
  );
}
