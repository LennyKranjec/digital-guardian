import { useTranslation } from 'react-i18next';

import type { Alert } from '../api/client';
import { formatAbsolute } from '../model/time';
import { FactChip } from './FactChip';
import { TrafficLight } from './TrafficLight';
import { ReasonList, TriagePanel } from './TriagePanel';
import { hasSpan, lightOf } from '../model/triage';

const numberFormat = (value: number, locale: string): string =>
  new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);

interface ExplanationPanelProps {
  alert: Alert;
  locale: string;
  onOpenFact: (factId: string) => void;
  id: string;
}

/**
 * „Warum?“ – die vollständige, deterministische Erklärung einer Meldung: Regel, Version,
 * Parameter (Schwellen), beobachtete Werte, Baseline-Zeitraum, Zyklustag, Belege. Alles stammt
 * aus der Regel-Engine; die Oberfläche bewertet nichts selbst.
 */
export function ExplanationPanel({ alert, locale, onOpenFact, id }: ExplanationPanelProps) {
  const { t } = useTranslation();
  const { explanation } = alert;
  const params = Object.entries(explanation.params);
  const observed = Object.entries(explanation.observed);
  const unavailable = t('waechter.clinic.alerts.notAvailable');
  const baselineWindow = explanation.baseline_window;

  return (
    <div id={id} className="space-y-3 border-t border-border pt-3" data-testid="explanation">
      <p className="text-base">
        <span className="font-semibold">
          {t(`waechter.clinic.alerts.kind.${explanation.kind}`)}
        </span>
        {' · '}
        {t('waechter.clinic.alerts.rule')}: {alert.rule_id}
        {' · '}
        {t('waechter.clinic.alerts.ruleVersion')}: {alert.rule_version}
      </p>
      {explanation.rationale ? (
        <p className="break-words text-base">{explanation.rationale}</p>
      ) : null}
      {explanation.triage ? <TriageExplanation alert={alert} triage={explanation.triage} /> : null}
      <dl className="m-0 grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-base">
        {params.length > 0 ? (
          <>
            <dt className="col-span-2 font-semibold">{t('waechter.clinic.alerts.params')}</dt>
            {params.map(([key, value]) => (
              <ParamRow
                key={`p-${key}`}
                label={t(`waechter.clinic.alerts.paramNames.${key}`, { defaultValue: key })}
                value={numberFormat(value, locale)}
              />
            ))}
          </>
        ) : null}
        {observed.length > 0 ? (
          <>
            <dt className="col-span-2 mt-2 font-semibold">
              {t('waechter.clinic.alerts.observed')}
            </dt>
            {observed.map(([key, value]) => (
              <ParamRow
                key={`o-${key}`}
                label={t(`waechter.clinic.alerts.observedNames.${key}`, { defaultValue: key })}
                value={value === null ? unavailable : numberFormat(value, locale)}
              />
            ))}
          </>
        ) : null}
        {baselineWindow?.from || baselineWindow?.to ? (
          <ParamRow
            label={t('waechter.clinic.alerts.baselineWindow')}
            value={[baselineWindow.from, baselineWindow.to]
              .map((iso) => (iso ? formatAbsolute(iso, locale) : unavailable))
              .join(' – ')}
          />
        ) : null}
        {explanation.baseline_limit ? (
          <dt className="col-span-2 text-muted" data-testid="baseline-limit">
            {t('waechter.clinic.alerts.baselineLimit', {
              regimen: explanation.baseline_limit.regimen_id,
              since: formatAbsolute(explanation.baseline_limit.since, locale),
            })}
          </dt>
        ) : null}
        {explanation.cycle_day !== null && explanation.cycle_day !== undefined ? (
          <ParamRow
            label={t('waechter.clinic.alerts.cycleDay')}
            value={numberFormat(explanation.cycle_day, locale)}
          />
        ) : null}
      </dl>
      <div className="space-y-2">
        <p className="text-base font-semibold">{t('waechter.clinic.alerts.evidence')}</p>
        {explanation.evidence.length > 0 ? (
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {explanation.evidence.map((factId) => (
              <li key={factId}>
                <FactChip factId={factId} onOpen={onOpenFact} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-base text-muted">{t('waechter.clinic.alerts.noEvidence')}</p>
        )}
      </div>
    </div>
  );
}

function ParamRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="min-w-0 break-words text-muted">{label}</dt>
      <dd className="m-0 text-right font-semibold tabular">{value}</dd>
    </>
  );
}

/**
 * Triage-Erklärung einer Meldung (v2.8: Meldung R-TRI-RED/YEL aus dem kompilierten Baum oder an eine
 * Bestandsmeldung angehängt): Stufe (Text + Symbol) mit Spanne, Begründungen (Schutzboden mit Schloss
 * zuerst) und der aufklappbare Befund der zugehörigen Antwort. Stufe und Pfade kommen vom Server.
 */
function TriageExplanation({
  alert,
  triage,
}: {
  alert: Alert;
  triage: NonNullable<Alert['explanation']['triage']>;
}) {
  const { t } = useTranslation();
  const span =
    triage.level_lo &&
    triage.level_hi &&
    hasSpan({ level_lo: triage.level_lo, level_hi: triage.level_hi })
      ? { lo: triage.level_lo, hi: triage.level_hi }
      : null;
  return (
    <div className="space-y-3" data-testid="explanation-triage">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <TrafficLight
          level={lightOf(triage.level)}
          label={t(`waechter.clinic.triage.levels.${triage.level}`)}
        />
        {span ? (
          <p className="m-0 text-base" data-testid="explanation-triage-span">
            {t('waechter.clinic.triage.span', {
              lo: t(`waechter.clinic.triage.levelsShort.${span.lo}`),
              hi: t(`waechter.clinic.triage.levelsShort.${span.hi}`),
            })}
          </p>
        ) : null}
      </div>
      {triage.incomplete ? (
        <p
          role="note"
          className="rounded-md border border-border-strong p-3 text-base font-semibold"
        >
          {t('waechter.clinic.triage.incomplete')}
        </p>
      ) : null}
      <ReasonList reasons={triage.reason_codes ?? []} />
      <TriagePanel
        patientId={alert.patient_id}
        responseId={triage.response_id ?? null}
        label={t('waechter.clinic.alerts.triageOpen')}
      />
    </div>
  );
}
