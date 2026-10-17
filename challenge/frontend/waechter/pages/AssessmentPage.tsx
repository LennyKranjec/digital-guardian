import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  NotFoundState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { toLang, type AssessmentTemplate } from '../api/client';
import { AssessmentTermCard } from '../components/AssessmentTermCard';
import { TrafficLight } from '../components/TrafficLight';
import { useCreateAssessment, useAssessmentTemplate } from '../hooks/useAssessment';
import { useOverview } from '../hooks/useCockpit';
import {
  assessmentFingerprint,
  buildItems,
  draftOf,
  mapFieldErrors,
  type DraftMap,
  type TermDraft,
} from '../model/assessment';

/** Standardlink zum Originalprodukt, falls die Vorlage keinen eigenen liefert (NCI verlangt Quelle + Link). */
const NCI_FALLBACK_URL = 'https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events';

function sourceOf(template: AssessmentTemplate): { title: string | null; url: string } {
  const source = template.source;
  if (typeof source === 'string') return { title: source, url: NCI_FALLBACK_URL };
  return { title: source?.title ?? null, url: source?.url ?? NCI_FALLBACK_URL };
}

function submitErrorKey(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return 'network';
    if (error.status === 422) return 'invalid';
    if (error.status === 404) return 'notFound';
    if (error.status === 401 || error.status === 403) return 'forbidden';
  }
  return 'generic';
}

function AssessmentForm({
  patientId,
  template,
}: {
  patientId: string;
  template: AssessmentTemplate;
}) {
  const { t, i18n } = useTranslation();
  const locale = toLang(i18n.resolvedLanguage ?? i18n.language);
  const navigate = useNavigate();
  const overview = useOverview(patientId);
  const { mutation, submit } = useCreateAssessment(patientId);
  const [drafts, setDrafts] = useState<DraftMap>({});
  // Standard: alle offenen Meldungen der Patientin verknüpft; abgewählte merken wir uns.
  const [unlinked, setUnlinked] = useState<ReadonlySet<string>>(new Set());
  const [needOne, setNeedOne] = useState(false);

  const openAlerts = useMemo(
    () => (overview.data?.open_alerts ?? []).filter((alert) => alert.status === 'open'),
    [overview.data],
  );
  const relatedIds = openAlerts.map((alert) => alert.alert_id).filter((id) => !unlinked.has(id));
  const items = buildItems(template, drafts);
  const source = sourceOf(template);

  const sentItems = mutation.variables?.items ?? [];
  const fieldErrors =
    mutation.error instanceof ApiClientError && mutation.error.status === 422
      ? mapFieldErrors(mutation.error.fieldErrors, sentItems)
      : { byTerm: new Map<string, string[]>(), general: [] as string[] };
  const errorKey = mutation.isError ? submitErrorKey(mutation.error) : null;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending) return;
    if (items.length === 0) {
      setNeedOne(true);
      return;
    }
    setNeedOne(false);
    submit(assessmentFingerprint(patientId, items, relatedIds), {
      items,
      ...(relatedIds.length > 0 ? { related_alert_ids: relatedIds } : {}),
    });
  }

  // Erfolg: zurück ins Cockpit (der Verlauf lädt die Aufnahme neu).
  const saved = mutation.isSuccess;
  useEffect(() => {
    if (saved) {
      void navigate(`/clinic/patients/${encodeURIComponent(patientId)}`, {
        replace: true,
        state: { assessmentSaved: true },
      });
    }
  }, [saved, navigate, patientId]);

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4" data-testid="assessment-form">
      <p className="text-base" data-testid="assessment-source">
        {t('waechter.clinic.assess.sourceLine', {
          title:
            source.title ??
            t('waechter.clinic.assess.sourceDefault', { version: template.ctcae_version }),
        })}{' '}
        <a href={source.url} target="_blank" rel="noreferrer" className="font-semibold underline">
          {t('waechter.clinic.assess.sourceLink')}
        </a>
      </p>
      {template.terms.length === 0 ? (
        <EmptyState
          title={t('waechter.clinic.assess.emptyTitle')}
          body={t('waechter.clinic.assess.emptyBody')}
        />
      ) : (
        template.terms.map((term) => (
          <AssessmentTermCard
            key={term.ctcae_term_id}
            term={term}
            patientId={patientId}
            locale={locale}
            draft={draftOf(drafts, term.ctcae_term_id)}
            errors={fieldErrors.byTerm.get(term.ctcae_term_id) ?? []}
            onChange={(next: TermDraft) =>
              setDrafts((current) => ({ ...current, [term.ctcae_term_id]: next }))
            }
          />
        ))
      )}

      <fieldset className="m-0 min-w-0 space-y-2 rounded-lg border border-border bg-surface p-4">
        <legend className="px-1 text-lg font-semibold">
          {t('waechter.clinic.assess.relatedLegend')}
        </legend>
        {openAlerts.length === 0 ? (
          <p className="text-base text-muted">{t('waechter.clinic.assess.noOpenAlerts')}</p>
        ) : (
          openAlerts.map((alert) => (
            <label
              key={alert.alert_id}
              className="flex min-h-11 min-w-0 cursor-pointer items-center gap-3 rounded-md border border-border-strong px-3 py-2 text-base has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2"
            >
              <input
                type="checkbox"
                className="size-5 shrink-0"
                checked={!unlinked.has(alert.alert_id)}
                onChange={(event) =>
                  setUnlinked((current) => {
                    const next = new Set(current);
                    if (event.target.checked) next.delete(alert.alert_id);
                    else next.add(alert.alert_id);
                    return next;
                  })
                }
              />
              <span className="min-w-0 break-words">
                {alert.headline ?? alert.rule_id}{' '}
                <span className="text-muted">
                  ({t(`waechter.clinic.timeline.levels.${alert.level}`)})
                </span>
              </span>
            </label>
          ))
        )}
      </fieldset>

      {needOne ? (
        <p role="alert" className="rounded-md border border-danger p-3 text-base font-semibold">
          {t('waechter.clinic.assess.needOne')}
        </p>
      ) : null}
      {errorKey ? (
        <div
          role="alert"
          className="space-y-1 rounded-md border border-danger p-3 text-base font-semibold"
        >
          <p>{t(`waechter.clinic.assess.errors.${errorKey}`)}</p>
          {fieldErrors.general.map((message) => (
            <p key={message}>{t('waechter.clinic.assess.errors.fieldError', { message })}</p>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={mutation.isPending || mutation.isSuccess}>
          {mutation.isPending
            ? t('waechter.clinic.assess.sending')
            : errorKey === 'network'
              ? t('waechter.clinic.assess.resend')
              : t('waechter.clinic.assess.submit')}
        </Button>
        <LinkButton to={`/clinic/patients/${encodeURIComponent(patientId)}`}>
          {t('waechter.clinic.assess.cancel')}
        </LinkButton>
      </div>
    </form>
  );
}

/**
 * CTCAE-Aufnahme der Ärztin im Subraum der getrackten Symptome. Die Seite übernimmt keine Bewertung:
 * Grade wählt die Ärztin; PRO-Werte stehen nur als Hinweis neben jedem Begriff.
 */
export function AssessmentPage() {
  const { t } = useTranslation();
  const { patientId = '' } = useParams();
  const query = useAssessmentTemplate(patientId);
  const overview = useOverview(patientId);

  return (
    <section aria-labelledby="assess-title" className="mx-auto w-full max-w-3xl space-y-4">
      <LinkButton to={`/clinic/patients/${encodeURIComponent(patientId)}`}>
        {t('waechter.clinic.assess.back')}
      </LinkButton>
      <div className="space-y-2">
        <h1 id="assess-title" className="text-3xl font-bold leading-tight">
          {t('waechter.clinic.assess.title')}
        </h1>
        {overview.data ? (
          <p className="flex flex-wrap items-center gap-2 text-base" data-testid="assess-patient">
            <span className="font-semibold">{overview.data.patient.display_name}</span>
            <span className="text-muted">{overview.data.patient.pseudonym}</span>
            <TrafficLight level={overview.data.traffic_light} />
          </p>
        ) : null}
        <p className="text-base text-muted">{t('waechter.clinic.assess.intro')}</p>
      </div>
      {query.isPending ? <SkeletonBlock lines={6} /> : null}
      {query.isError ? (
        query.error instanceof ApiClientError && query.error.status === 404 ? (
          <NotFoundState />
        ) : query.error instanceof ApiClientError && query.error.status === 403 ? (
          <ForbiddenState />
        ) : (
          <ErrorState onRetry={() => void query.refetch()} />
        )
      ) : null}
      {query.data ? <AssessmentForm patientId={patientId} template={query.data} /> : null}
    </section>
  );
}
