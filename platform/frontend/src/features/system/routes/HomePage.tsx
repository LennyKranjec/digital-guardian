import { useTranslation } from 'react-i18next';

import { QueryErrorView } from '../../../shared/ui/QueryErrorView';
import { SkeletonBlock } from '../../../shared/ui/StateViews';
import { useMeta } from '../api';

/** Startseite: ohne Challenge-Paket der Platzhalter „Noch keine Challenge-Funktionen geladen“. */
export function HomePage() {
  const { t } = useTranslation();
  const meta = useMeta();

  return (
    <section aria-labelledby="home-title" className="space-y-6">
      <h1 id="home-title" data-testid="home-title" className="text-3xl font-bold leading-tight">
        {meta.data?.app_name ?? t('home.title')}
      </h1>
      {meta.isPending ? <SkeletonBlock lines={3} /> : null}
      {meta.isError ? (
        <QueryErrorView error={meta.error} onRetry={() => void meta.refetch()} />
      ) : null}
      {meta.data && !meta.data.challenge_loaded ? (
        <p
          role="status"
          data-testid="no-challenge"
          className="rounded-lg border border-border bg-sunken p-6 text-lg"
        >
          {t('home.noChallenge')}
        </p>
      ) : null}
      {meta.data ? (
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-[max-content_1fr]" data-testid="meta-list">
          <dt className="text-muted">{t('home.version')}</dt>
          <dd data-testid="meta-version">{meta.data.version}</dd>
          <dt className="text-muted">{t('home.demoMode')}</dt>
          <dd>{meta.data.demo_mode ? t('home.yes') : t('home.no')}</dd>
          <dt className="text-muted">{t('home.syntheticData')}</dt>
          <dd>{t('home.syntheticYes')}</dd>
        </dl>
      ) : null}
    </section>
  );
}
