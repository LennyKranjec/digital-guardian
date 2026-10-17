import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMe } from '../../../../platform/frontend/src/features/auth/api';
import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  ErrorState,
  ForbiddenState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import {
  CHANGE_NOTE_MAX_LENGTH,
  type AlertLevel,
  type ConfigState,
  type Lang,
  type RulesFile,
} from '../api/client';
import { AdviceRules } from '../components/AdviceRules';
import { ConfigHistory } from '../components/ConfigHistory';
import { RegimenProfiles } from '../components/RegimenProfiles';
import { ReportSettings } from '../components/ReportSettings';
import { RuleCard } from '../components/RuleCard';
import { TriageRules } from '../components/TriageRules';
import { useInvalidateClinicData } from '../hooks/useAcknowledge';
import { useLang } from '../hooks/useLang';
import { settingsErrorKey, useUpdateRules } from '../hooks/useSettings';
import { useConfig } from '../hooks/useTimeline';
import {
  buildRulesUpdate,
  hasActiveRedRule,
  initialDrafts,
  initialNoise,
  invalidParams,
  isCooldownValid,
  mapRuleErrors,
  parseParam,
  rulesChanged,
  type NoiseDraft,
  type RuleDrafts,
} from '../model/settings';

const LEVELS: AlertLevel[] = ['red', 'yellow', 'grey'];

function RulesEditor({
  file,
  lang,
  editable,
  locale,
  onSaved,
}: {
  file: RulesFile;
  lang: Lang;
  editable: boolean;
  locale: string;
  onSaved: (state: ConfigState) => void;
}) {
  const { t } = useTranslation();
  const update = useUpdateRules();
  const reload = useInvalidateClinicData();
  const [drafts, setDrafts] = useState<RuleDrafts>(() => initialDrafts(file.rules));
  const [noise, setNoise] = useState<NoiseDraft>(() => initialNoise(file.noise));
  const [note, setNote] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const changed = rulesChanged(file, drafts, noise);
  const bad = invalidParams(file.rules, drafts);
  const sent = update.variables?.rules.rules ?? [];
  const serverErrors =
    update.error instanceof ApiClientError && update.error.status === 422
      ? mapRuleErrors(update.error.fieldErrors, sent)
      : { byRule: new Map<string, string[]>(), general: [] as string[] };
  const errorKey = update.isError ? settingsErrorKey(update.error) : null;
  const conflict = errorKey === 'conflict';
  // Rote Sofortbenachrichtigung betrifft die Rauschbremse: Meldung steht dort, nicht unten.
  const noiseError =
    localError === 'noRedNotification' || errorKey === 'noRedNotification'
      ? 'noRedNotification'
      : null;

  function save() {
    if (update.isPending) return;
    if (Object.keys(bad).length > 0 || !isCooldownValid(noise)) {
      setLocalError('invalidNumber');
      return;
    }
    if (!hasActiveRedRule(file.rules, drafts)) {
      setLocalError('noRedRule');
      return;
    }
    if (file.noise && !noise.notify.includes('red')) {
      setLocalError('noRedNotification');
      return;
    }
    if (note.trim() === '') {
      setLocalError('needNote');
      return;
    }
    setLocalError(null);
    update.mutate(buildRulesUpdate(file, drafts, noise, lang, note), {
      onSuccess: (state) => onSaved(state),
    });
  }

  return (
    <div className="space-y-4">
      <ul
        className="m-0 list-none space-y-3 p-0"
        aria-label={t('waechter.clinic.settings.rules.list')}
      >
        {file.rules.map((rule) => (
          <li key={rule.id}>
            <RuleCard
              rule={rule}
              lang={lang}
              editable={editable}
              draft={drafts[rule.id] ?? { enabled: rule.enabled, params: {} }}
              errors={serverErrors.byRule.get(rule.id) ?? []}
              onChange={(next) => setDrafts((current) => ({ ...current, [rule.id]: next }))}
            />
          </li>
        ))}
      </ul>

      {file.noise ? (
        <fieldset
          data-testid="noise"
          className="m-0 min-w-0 space-y-3 rounded-lg border border-border bg-surface p-4"
        >
          <legend className="px-1 text-lg font-semibold">
            {t('waechter.clinic.settings.noise.title')}
          </legend>
          <div className="space-y-1">
            <label htmlFor="noise-cooldown" className="block text-base font-semibold">
              {t('waechter.clinic.settings.noise.cooldown')}
            </label>
            {editable ? (
              <input
                id="noise-cooldown"
                type="text"
                inputMode="decimal"
                value={noise.cooldown}
                aria-invalid={parseParam(noise.cooldown) === null}
                onChange={(event) =>
                  setNoise((current) => ({ ...current, cooldown: event.target.value }))
                }
                className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink sm:max-w-xs"
              />
            ) : (
              <output id="noise-cooldown" className="block text-base">
                {noise.cooldown}
              </output>
            )}
            <p className="text-base text-muted">
              {t('waechter.clinic.settings.noise.cooldownHint')}
            </p>
          </div>
          <div className="space-y-2">
            <p className="text-base font-semibold">{t('waechter.clinic.settings.noise.notify')}</p>
            <div className="flex flex-wrap gap-2">
              {LEVELS.map((level) => (
                <label
                  key={level}
                  className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-border-strong px-3 py-2 text-base has-[:disabled]:cursor-default has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2"
                >
                  <input
                    type="checkbox"
                    className="size-5"
                    checked={noise.notify.includes(level)}
                    disabled={!editable}
                    onChange={(event) =>
                      setNoise((current) => ({
                        ...current,
                        notify: event.target.checked
                          ? [...current.notify, level]
                          : current.notify.filter((entry) => entry !== level),
                      }))
                    }
                  />
                  {t(`waechter.clinic.timeline.levels.${level}`)}
                </label>
              ))}
            </div>
            {noiseError ? (
              <p
                role="alert"
                data-testid="noise-error"
                className="rounded-md border border-danger p-3 text-base font-semibold"
              >
                {t(`waechter.clinic.settings.errors.${noiseError}`)}
              </p>
            ) : null}
          </div>
        </fieldset>
      ) : null}

      {editable ? (
        <div className="space-y-2 rounded-lg border border-border bg-surface p-4">
          <label htmlFor="change-note" className="block text-base font-semibold">
            {t('waechter.clinic.settings.changeNote')}
          </label>
          <textarea
            id="change-note"
            value={note}
            rows={2}
            maxLength={CHANGE_NOTE_MAX_LENGTH}
            required
            aria-describedby="change-note-counter"
            onChange={(event) => setNote(event.target.value)}
            className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink"
          />
          <p id="change-note-counter" className="text-right text-base text-muted">
            {t('waechter.clinic.ack.counter', { count: note.length, max: CHANGE_NOTE_MAX_LENGTH })}
          </p>
          {localError && localError !== 'noRedNotification' ? (
            <p role="alert" className="rounded-md border border-danger p-3 text-base font-semibold">
              {t(`waechter.clinic.settings.errors.${localError}`)}
            </p>
          ) : null}
          {errorKey && errorKey !== 'noRedNotification' ? (
            <div
              role="alert"
              className="space-y-1 rounded-md border border-danger p-3 text-base font-semibold"
            >
              <p>{t(`waechter.clinic.settings.errors.${errorKey}`)}</p>
              {serverErrors.general.map((message) => (
                <p key={message}>{t('waechter.clinic.assess.errors.fieldError', { message })}</p>
              ))}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {conflict ? (
              <Button
                onClick={() => {
                  void reload();
                }}
              >
                {t('waechter.clinic.ack.reload')}
              </Button>
            ) : (
              <Button disabled={!changed || update.isPending} onClick={save}>
                {update.isPending
                  ? t('waechter.clinic.settings.saving')
                  : t('waechter.clinic.settings.rules.save')}
              </Button>
            )}
          </div>
        </div>
      ) : null}
      <ConfigHistory kind="rules" locale={locale} />
    </div>
  );
}

/**
 * Einstellungen („Konfigurierbarkeit sichtbar machen“): aktive Regeln mit Parametern, Begründung und
 * Quelle, Versionshistorie, Berichtsinhalt und die Fragebogen-Profile je Therapie. Ärztinnen lesen,
 * Administration ändert; die Rolle prüft der Server (hier nur Anzeige).
 */
export function SettingsPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const locale = lang;
  const me = useMe();
  const config = useConfig();
  const [saved, setSaved] = useState<string | null>(null);
  const editable = me.data?.role === 'admin';

  return (
    <section aria-labelledby="settings-title" className="mx-auto w-full max-w-4xl space-y-6">
      <div className="space-y-2">
        <LinkButton to="/clinic">{t('waechter.clinic.alertPage.toList')}</LinkButton>
        <h1 id="settings-title" className="text-3xl font-bold leading-tight">
          {t('waechter.clinic.settings.title')}
        </h1>
        <p className="text-base text-muted" data-testid="settings-role-note">
          {editable
            ? t('waechter.clinic.settings.introAdmin')
            : t('waechter.clinic.settings.introReadOnly')}
        </p>
      </div>
      {config.isPending ? <SkeletonBlock lines={6} /> : null}
      {config.isError ? (
        config.error instanceof ApiClientError && config.error.status === 403 ? (
          <ForbiddenState />
        ) : (
          <ErrorState onRetry={() => void config.refetch()} />
        )
      ) : null}
      {saved ? (
        <p
          role="status"
          data-testid="rules-saved"
          className="rounded-md border border-border-strong bg-surface p-3 text-base font-semibold"
        >
          {saved}
        </p>
      ) : null}
      {config.data ? (
        <>
          <section aria-labelledby="rules-title" className="space-y-3" data-testid="rules-section">
            <h2 id="rules-title" className="text-lg font-semibold">
              {t('waechter.clinic.settings.rules.title')}
            </h2>
            <p className="text-base text-muted">
              {t('waechter.clinic.settings.rules.version', { version: config.data.rules.version })}
            </p>
            <RulesEditor
              key={config.data.rules.version}
              file={config.data.rules}
              lang={lang}
              editable={editable}
              locale={locale}
              onSaved={(state) =>
                setSaved(t('waechter.clinic.settings.rules.saved', { version: state.version }))
              }
            />
          </section>
          <ReportSettings
            key={config.data.report.version}
            report={config.data.report}
            editable={editable}
            locale={locale}
          />
          <RegimenProfiles config={config.data} lang={lang} />
          <TriageRules />
          <AdviceRules advice={config.data.advice} />
        </>
      ) : null}
    </section>
  );
}
