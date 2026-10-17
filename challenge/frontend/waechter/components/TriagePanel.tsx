import { useId, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { SkeletonBlock } from '../../../../platform/frontend/src/shared/ui/StateViews';
import type { ReasonCode, TriageDecision } from '../api/client';
import { useTriage } from '../hooks/useTriage';
import {
  askedOf,
  hasSpan,
  isPlaceholderStatus,
  lightOf,
  orderReasons,
  shortHash,
  splitCounterfactuals,
} from '../model/triage';
import { CardTable } from './CardTable';
import { TrafficLight } from './TrafficLight';

/** Schloss-Symbol für Schutzböden (Symbol und Wort, nie nur Farbe). */
export function LockIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
    >
      <rect x="4" y="9" width="12" height="8" rx="1.5" />
      <path d="M7 9V6.5a3 3 0 016 0V9" />
    </svg>
  );
}

/** Begründungen geordnet: Schutzboden (Schloss) zuerst, dann Pfad mit beteiligten Symptomen. */
export function ReasonList({ reasons: raw }: { reasons: readonly ReasonCode[] }) {
  const { t } = useTranslation();
  const titleId = useId();
  const reasons = orderReasons(raw);
  return (
    <section aria-labelledby={titleId} className="space-y-2">
      <h3 id={titleId} className="text-base font-semibold">
        {t('waechter.clinic.triage.why')}
      </h3>
      {reasons.length === 0 ? (
        <p className="text-base text-muted">{t('waechter.clinic.triage.noReasons')}</p>
      ) : (
        <ol className="m-0 list-none space-y-2 p-0" data-testid="triage-reasons">
          {reasons.map((reason, index) => (
            <li
              key={`${reason.code}-${index}`}
              data-kind={reason.kind ?? 'path'}
              className="space-y-1 rounded-md border border-border p-2 text-base"
            >
              <p className="flex flex-wrap items-start gap-2">
                {reason.kind === 'shield' ? (
                  <span className="inline-flex items-center gap-1 font-semibold">
                    <LockIcon />
                    {t('waechter.clinic.triage.shield')}:
                  </span>
                ) : null}
                {reason.kind === 'shield' ? ' ' : null}
                <span className="min-w-0 break-words">{reason.text}</span>
              </p>
              {(reason.items ?? []).length > 0 ? (
                <p className="break-words text-muted">
                  {t('waechter.clinic.triage.involved')}: {(reason.items ?? []).join(', ')}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Reasons({ decision }: { decision: TriageDecision }) {
  return <ReasonList reasons={decision.reason_codes} />;
}

function Counterfactuals({ decision }: { decision: TriageDecision }) {
  const { t } = useTranslation();
  const titleId = useId();
  const { lower, raise, shields } = splitCounterfactuals(decision);
  return (
    <section aria-labelledby={titleId} className="space-y-2">
      <h3 id={titleId} className="text-base font-semibold">
        {t('waechter.clinic.triage.change')}
      </h3>
      {lower.length === 0 && raise.length === 0 && shields.length === 0 ? (
        <p className="text-base text-muted">{t('waechter.clinic.triage.noChange')}</p>
      ) : null}
      {lower.length > 0 ? (
        <div data-testid="triage-lower">
          <p className="text-base font-semibold">{t('waechter.clinic.triage.lower')}</p>
          <ul className="m-0 list-disc space-y-1 pl-6 text-base">
            {lower.map((text) => (
              <li key={text} className="break-words">
                {text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {shields.length > 0 ? (
        <ul className="m-0 list-none space-y-1 p-0" data-testid="triage-shield-notes">
          {shields.map((text) => (
            <li key={text} className="flex flex-wrap items-start gap-2 text-base">
              <span className="inline-flex items-center gap-1 font-semibold">
                <LockIcon />
                {t('waechter.clinic.triage.shield')}:
              </span>{' '}
              <span className="min-w-0 break-words">{text}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {raise.length > 0 ? (
        <div data-testid="triage-raise">
          <p className="text-base font-semibold">{t('waechter.clinic.triage.raise')}</p>
          <ul className="m-0 list-disc space-y-1 pl-6 text-base">
            {raise.map((text) => (
              <li key={text} className="break-words">
                {text}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/** Tipps, die die Patientin erhielt (Regel-ID, Symptom, Wert, angezeigt/unterdrückt) – nur für die Ärztin. */
function PatientTips({ decision }: { decision: TriageDecision }) {
  const { t } = useTranslation();
  const titleId = useId();
  const rows = decision.recommendations ?? [];
  return (
    <section aria-labelledby={titleId} className="space-y-2">
      <h3 id={titleId} className="text-base font-semibold">
        {t('waechter.clinic.triage.tips')}
      </h3>
      {rows.length === 0 ? (
        <p className="text-base text-muted">{t('waechter.clinic.triage.noTips')}</p>
      ) : (
        <CardTable
          testId="triage-tips-table"
          label={t('waechter.clinic.triage.tips')}
          columns={[
            { key: 'rule', label: t('waechter.clinic.triage.columns.rule') },
            { key: 'symptom', label: t('waechter.clinic.triage.columns.symptom') },
            { key: 'value', label: t('waechter.clinic.triage.columns.value') },
            { key: 'outcome', label: t('waechter.clinic.triage.columns.outcome') },
          ]}
          rows={rows.map((row, index) => ({
            id: `${row.rule_id}-${index}`,
            cells: [
              row.rule_id,
              row.symptom_key,
              row.value ?? '–',
              <span key="o" data-outcome={row.outcome} className="font-semibold">
                {t(`waechter.clinic.triage.outcomes.${row.outcome}`)}
              </span>,
            ],
          }))}
        />
      )}
    </section>
  );
}

function Finding({ decision }: { decision: TriageDecision }) {
  const { t } = useTranslation();
  const asked = askedOf(decision);
  return (
    <div className="space-y-3" data-testid="triage-finding">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <TrafficLight
          level={lightOf(decision.level)}
          label={t(`waechter.clinic.triage.levels.${decision.level}`)}
        />
        {hasSpan(decision) ? (
          <p className="m-0 text-base" data-testid="triage-span">
            {t('waechter.clinic.triage.span', {
              lo: t(`waechter.clinic.triage.levelsShort.${decision.level_lo}`),
              hi: t(`waechter.clinic.triage.levelsShort.${decision.level_hi}`),
            })}
          </p>
        ) : null}
      </div>
      {decision.incomplete ? (
        <p
          role="note"
          data-testid="triage-incomplete"
          className="rounded-md border border-border-strong p-3 text-base font-semibold"
        >
          {t('waechter.clinic.triage.incomplete')}
        </p>
      ) : null}
      <Reasons decision={decision} />
      <Counterfactuals decision={decision} />
      {asked ? (
        <p className="text-base" data-testid="triage-asked">
          {t('waechter.clinic.triage.asked', asked)}
        </p>
      ) : null}
      <PatientTips decision={decision} />
      <div className="space-y-1 border-t border-border pt-2 text-base text-muted">
        <p
          className="break-all"
          data-testid="triage-versions"
          title={`${decision.rule_version} · ${decision.tree_version}`}
        >
          {t('waechter.clinic.triage.versions', {
            rule: shortHash(decision.rule_version),
            tree: shortHash(decision.tree_version, 12),
          })}
          {decision.profile_id ? ` · ${decision.profile_id}` : ''}
        </p>
        {isPlaceholderStatus(decision.status) ? (
          <p className="font-semibold" data-testid="triage-placeholder">
            {t('waechter.clinic.triage.placeholder')}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Triage-Befund im Cockpit (eingeklappt, damit der erste Bildschirm S5 unverändert bleibt): warum diese
 * Stufe, was sie ändern würde, welche Tipps die Patientin bekam. Wird erst beim Öffnen geladen; fehlt die
 * Triage (404), steht ein dezenter Hinweis. Stufe und Pfade kommen vom Server, hier wird nichts bewertet.
 */
export function TriagePanel({
  patientId,
  responseId = null,
  label,
}: {
  patientId: string;
  responseId?: string | null;
  /** Beschriftung der Zusammenfassung (Standard: „Triage-Befund“) */
  label?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const query = useTriage(patientId, responseId, open);

  function toggle(event: MouseEvent<HTMLElement>) {
    event.preventDefault();
    setOpen((current) => !current);
  }

  const notFound = query.error instanceof ApiClientError && query.error.status === 404;

  return (
    <details
      open={open}
      data-testid="triage-panel"
      className="rounded-lg border border-border bg-surface px-3"
    >
      <summary
        onClick={toggle}
        className="inline-flex min-h-11 w-full cursor-pointer items-center text-base font-semibold"
      >
        {label ?? t('waechter.clinic.triage.title')}
      </summary>
      {open ? (
        <div className="space-y-3 pb-3">
          {query.isPending ? <SkeletonBlock lines={3} /> : null}
          {query.isError ? (
            notFound ? (
              <p className="text-base text-muted" data-testid="triage-unavailable">
                {t('waechter.clinic.triage.unavailable')}
              </p>
            ) : (
              <div className="space-y-2" role="status">
                <p className="text-base text-muted">{t('waechter.clinic.triage.error')}</p>
                <Button variant="secondary" onClick={() => void query.refetch()}>
                  {t('states.retry')}
                </Button>
              </div>
            )
          ) : null}
          {query.data ? <Finding decision={query.data} /> : null}
        </div>
      ) : null}
    </details>
  );
}
