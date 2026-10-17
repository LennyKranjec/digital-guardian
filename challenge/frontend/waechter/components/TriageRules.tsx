import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { SkeletonBlock } from '../../../../platform/frontend/src/shared/ui/StateViews';
import type { TriageProfile } from '../api/client';
import { useTriageConfig } from '../hooks/useTriage';
import {
  shortHash,
  sortRulesRedFirst,
  verificationClean,
  verificationPassed,
  verificationScope,
} from '../model/triage';
import { LockIcon } from './TriagePanel';

function levelWord(level: string, t: (key: string) => string): string {
  const key = level.toUpperCase();
  return ['RED', 'YELLOW', 'GREEN'].includes(key)
    ? t(`waechter.clinic.triage.levelsShort.${key}`)
    : level;
}

function Profile({ profile, open }: { profile: TriageProfile; open: boolean }) {
  const { t } = useTranslation();
  const verification = profile.verification;
  const clean = verification ? verificationClean(verification) : false;
  const trees = profile.trees;
  const rules = sortRulesRedFirst(profile.rules ?? []);
  const floors = profile.floors ?? [];
  const placeholders = profile.placeholders ?? [];

  return (
    <details
      open={open}
      data-testid="triage-profile"
      data-profile={profile.profile_id}
      className="rounded-lg border border-border bg-surface px-3"
    >
      <summary className="inline-flex min-h-11 w-full cursor-pointer items-center break-words text-base font-semibold">
        {profile.profile_id}
        {(profile.regimen_ids ?? []).length > 0 ? (
          <span className="ml-2 font-normal text-muted">
            ({(profile.regimen_ids ?? []).join(', ')})
          </span>
        ) : null}
      </summary>
      <div className="space-y-3 pb-3">
        {verification ? (
          <div
            role="status"
            data-testid="triage-verification"
            data-clean={clean}
            data-scope={verificationScope(verification.scope)}
            data-passed={verificationPassed(verification)}
            className="space-y-1 rounded-md border border-border-strong p-3 text-base"
          >
            <p className="m-0 flex flex-wrap items-start gap-2 font-semibold">
              <span aria-hidden="true">{verificationPassed(verification) ? '✓' : '!'}</span>
              <span className="min-w-0 break-words">
                {t(
                  clean
                    ? 'waechter.clinic.settings.triage.verified'
                    : 'waechter.clinic.settings.triage.notVerified',
                )}
                {': '}
                {t(
                  `waechter.clinic.settings.triage.scope.${verificationScope(verification.scope)}`,
                  {
                    points: verification.points,
                  },
                )}
              </span>
            </p>
            <p className="m-0 break-words">
              {t('waechter.clinic.settings.triage.verification', {
                under: verification.under,
                over: verification.over,
                violations: verification.monotone_violations,
              })}
            </p>
            <p className="m-0 font-semibold" data-testid="triage-banner-placeholder">
              {t('waechter.clinic.triage.placeholder')}
            </p>
          </div>
        ) : (
          <p className="text-base text-muted">
            {t('waechter.clinic.settings.triage.noVerification')}
          </p>
        )}

        {trees ? (
          <p
            className="break-all text-base"
            data-testid="triage-trees"
            title={profile.tree_version ?? undefined}
          >
            {t('waechter.clinic.settings.triage.trees', {
              yl: trees.yellow?.leaves ?? '–',
              yd: trees.yellow?.depth ?? '–',
              rl: trees.red?.leaves ?? '–',
              rd: trees.red?.depth ?? '–',
            })}
            {profile.tree_version ? ` · ${shortHash(profile.tree_version, 12)}` : ''}
          </p>
        ) : null}

        <section aria-label={t('waechter.clinic.settings.triage.rules')} className="space-y-2">
          <h4 className="text-base font-semibold">{t('waechter.clinic.settings.triage.rules')}</h4>
          {rules.length === 0 ? (
            <p className="text-base text-muted">{t('waechter.clinic.settings.triage.noRules')}</p>
          ) : (
            <ol className="m-0 list-none space-y-2 p-0" data-testid="triage-rules">
              {rules.map((rule, index) => (
                <li
                  key={`${rule.leaf_id ?? rule.text}-${index}`}
                  data-level={rule.level.toUpperCase()}
                  className="space-y-1 rounded-md border border-border p-2 text-base"
                >
                  <p className="break-words">
                    <span className="font-semibold">{levelWord(rule.level, t)}: </span>
                    {rule.text}
                  </p>
                  {rule.leaf_id ? (
                    <p className="break-words text-muted">
                      {t('waechter.clinic.settings.triage.leaf')}: {shortHash(rule.leaf_id, 12)}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section aria-label={t('waechter.clinic.settings.triage.floors')} className="space-y-2">
          <h4 className="text-base font-semibold">{t('waechter.clinic.settings.triage.floors')}</h4>
          {floors.length === 0 ? (
            <p className="text-base text-muted">{t('waechter.clinic.settings.triage.noFloors')}</p>
          ) : (
            <ul className="m-0 list-none space-y-2 p-0" data-testid="triage-floors">
              {floors.map((floor) => (
                <li
                  key={floor.id}
                  data-locked={floor.locked === true}
                  className="flex flex-wrap items-start gap-2 rounded-md border border-border p-2 text-base"
                >
                  {floor.locked ? (
                    <span className="inline-flex items-center gap-1 font-semibold">
                      <LockIcon />
                      {t('waechter.clinic.settings.triage.locked')}
                    </span>
                  ) : null}
                  <span className="min-w-0 break-words">
                    {floor.text} – {t('waechter.clinic.settings.triage.minLevel')}:{' '}
                    {levelWord(floor.min_level, t)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {placeholders.length > 0 ? (
          <section
            aria-label={t('waechter.clinic.settings.triage.placeholders')}
            className="space-y-1"
            data-testid="triage-placeholders"
          >
            <h4 className="text-base font-semibold">
              {t('waechter.clinic.settings.triage.placeholders')}
            </h4>
            <ul className="m-0 list-disc space-y-1 pl-6 text-base">
              {placeholders.map((entry) => (
                <li key={entry} className="break-words">
                  {entry}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
    </details>
  );
}

/**
 * Triage-Regelkarte (Einstellungen, nur lesen): je Profil Verifikationsbanner, Blätter/Tiefe, Regeln rot
 * zuerst, Böden mit Schloss und die Liste der Platzhalter. Alles vom Server; fehlt die Route, steht ein
 * ehrlicher Hinweis statt eines leeren Bereichs.
 */
export function TriageRules() {
  const { t } = useTranslation();
  const query = useTriageConfig();
  const notFound = query.error instanceof ApiClientError && query.error.status === 404;

  return (
    <section
      aria-labelledby="triage-rules-title"
      className="space-y-3"
      data-testid="triage-rules-section"
    >
      <h2 id="triage-rules-title" className="text-lg font-semibold">
        {t('waechter.clinic.settings.triage.title')}
      </h2>
      <p className="text-base text-muted">{t('waechter.clinic.settings.triage.intro')}</p>
      {query.isPending ? <SkeletonBlock lines={3} /> : null}
      {query.isError ? (
        notFound ? (
          <p className="text-base text-muted" data-testid="triage-rules-unavailable">
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
      {query.data ? (
        <>
          <p className="break-words text-base text-muted" data-testid="triage-kb">
            {t('waechter.clinic.settings.triage.kb', {
              kb: shortHash(query.data.kb_version, 12),
              compiler: query.data.compiler_version ?? '–',
            })}
          </p>
          <div className="space-y-3">
            {query.data.profiles.map((profile, index) => (
              <Profile key={profile.profile_id} profile={profile} open={index === 0} />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
