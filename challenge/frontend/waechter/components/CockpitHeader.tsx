import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { Overview } from '../api/client';
import { medicationSearchPath } from '../model/medications';
import { TimeInline } from './TimeText';
import { TrafficLight } from './TrafficLight';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-wrap gap-x-2">
      <dt className="text-muted">{label}</dt>
      <dd className="m-0 min-w-0 break-words">{children}</dd>
    </div>
  );
}

function Dot() {
  return (
    <span aria-hidden="true" className="text-muted">
      {' · '}
    </span>
  );
}

/**
 * Kopfzeile des Cockpits (kompakt, damit Lage, Meldungen und Kurzfassung auf 1366×768 passen):
 * Name (die einzige h1 der Seite) mit großer Ampel, Pseudonym, „synthetisch“, Alter, Therapie mit
 * Zyklustag und die wichtigsten Zeiten (relativ). „Mehr Angaben“ enthält Grunderkrankung, Wirkstoffe
 * und die Zeiten mit Datum – nichts davon geht verloren, es steht nur eine Ebene tiefer.
 */
export function CockpitHeader({
  overview,
  now,
  locale,
}: {
  overview: Overview;
  now: Date | null;
  locale: string;
}) {
  const { t } = useTranslation();
  const { patient, therapy } = overview;
  const drugs = therapy.drugs ?? [];
  const none = t('waechter.clinic.cockpit.noValue');
  const time = { now, locale };
  const hasDays =
    overview.days_without_response !== null && overview.days_without_response !== undefined;

  return (
    <header
      data-testid="cockpit-header"
      className="space-y-1 rounded-lg border border-border bg-surface p-2"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h1 className="min-w-0 break-words text-2xl font-bold leading-tight">
          {patient.display_name}
        </h1>
        <TrafficLight level={overview.traffic_light} size="large" />
      </div>
      <div className="flex flex-wrap items-center gap-x-2 text-base text-muted">
        <span>{patient.pseudonym}</span>
        {patient.synthetic !== false ? (
          <span className="rounded-md border border-border-strong px-2 text-ink">
            {t('waechter.clinic.synthetic')}
          </span>
        ) : null}
        {patient.age !== undefined && patient.age !== null ? (
          <span>{t('waechter.clinic.cockpit.age', { age: patient.age })}</span>
        ) : null}
        <details data-testid="header-more" className="ml-auto text-ink open:w-full">
          <summary className="inline-flex min-h-11 cursor-pointer items-center text-base font-semibold underline">
            {t('waechter.clinic.cockpit.more')}
          </summary>
          <dl className="m-0 space-y-1 pb-1 text-base">
            {patient.diagnosis_text ? (
              <Row label={`${t('waechter.clinic.cockpit.condition')}:`}>
                {patient.diagnosis_text}
              </Row>
            ) : null}
            <Row label={`${t('waechter.clinic.cockpit.drugs')}:`}>
              {drugs.length > 0
                ? drugs.map((drug, index) => (
                    <span key={`${drug.name}-${drug.atc ?? ''}`}>
                      {index > 0 ? ', ' : ''}
                      <Link
                        to={medicationSearchPath(drug.name)}
                        className="inline-flex min-h-11 items-center underline"
                      >
                        {drug.atc ? `${drug.name} (${drug.atc})` : drug.name}
                      </Link>
                    </span>
                  ))
                : none}
            </Row>
            <Row label={`${t('waechter.clinic.cockpit.lastVisit')}:`}>
              <TimeInline
                iso={overview.last_visit_at}
                empty={none}
                allowFuture={false}
                showAbsolute
                {...time}
              />
            </Row>
            {now && overview.last_response_at ? (
              <Row label={`${t('waechter.clinic.cockpit.lastResponse')}:`}>
                <TimeInline
                  iso={overview.last_response_at}
                  empty={none}
                  allowFuture={false}
                  onlyAbsolute
                  {...time}
                />
              </Row>
            ) : null}
            {now && overview.next_visit_at ? (
              <Row label={`${t('waechter.clinic.cockpit.nextVisit')}:`}>
                <TimeInline
                  iso={overview.next_visit_at}
                  empty={none}
                  allowFuture
                  onlyAbsolute
                  {...time}
                />
              </Row>
            ) : null}
          </dl>
        </details>
      </div>
      <dl className="m-0 text-base">
        <Row label={`${t('waechter.clinic.cockpit.therapy')}:`}>
          <span>{therapy.regimen_label ?? therapy.regimen_id}</span>
          {therapy.cycle_day !== null && therapy.cycle_day !== undefined ? (
            <>
              <Dot />
              <span>{t('waechter.clinic.cycleDay', { day: therapy.cycle_day })}</span>
            </>
          ) : null}
        </Row>
        <Row label={`${t('waechter.clinic.cockpit.lastResponse')}:`}>
          <TimeInline
            iso={overview.last_response_at}
            empty={t('waechter.clinic.noResponse')}
            allowFuture={false}
            {...time}
          />
          {hasDays ? (
            <>
              <Dot />
              <span data-testid="days-without-response">
                {t('waechter.clinic.daysWithout', { count: overview.days_without_response })}
              </span>
            </>
          ) : null}
        </Row>
        <Row label={`${t('waechter.clinic.cockpit.nextVisit')}:`}>
          <TimeInline
            iso={overview.next_visit_at}
            empty={t('waechter.clinic.noVisit')}
            allowFuture
            {...time}
          />
        </Row>
      </dl>
    </header>
  );
}
