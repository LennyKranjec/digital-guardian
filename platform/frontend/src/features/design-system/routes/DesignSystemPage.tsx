import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../shared/ui/Button';
import { STATUSES, StatusBadge } from '../../../shared/ui/StatusBadge';
import {
  EmptyState,
  ErrorState,
  NotFoundState,
  OfflineState,
  SkeletonBlock,
} from '../../../shared/ui/StateViews';
import { useMeta } from '../../system/api';
import { ChartExample } from '../components/ChartExample';
import { ContrastTable } from '../components/ContrastTable';
import { FormsExample } from '../components/FormsExample';

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-4">
      <h2 id={id} className="text-xl font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Swatch({ className, label }: { className: string; label: string }) {
  return (
    <div className={`rounded-lg border border-border p-4 ${className}`}>
      <p className="font-semibold">{label}</p>
      <p className="text-sm text-muted">{label}</p>
    </div>
  );
}

function Body() {
  const { t } = useTranslation();
  const [lastAction, setLastAction] = useState<string | null>(null);

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl font-bold leading-tight">{t('ds.title')}</h1>
        <p className="mt-2 text-muted">{t('ds.intro')}</p>
      </header>

      <Section id="ds-typography" title={t('ds.typography')}>
        <div className="space-y-2 rounded-lg border border-border bg-surface p-6">
          <p className="text-3xl font-bold leading-tight">{t('ds.pageTitleSample')}</p>
          <p className="text-xl font-semibold">{t('ds.headingSample')}</p>
          <p>{t('ds.bodySample')}</p>
          <p className="text-sm text-muted">{t('ds.mutedSample')}</p>
          <p className="tabular">{t('ds.tabularSample')}</p>
        </div>
      </Section>

      <Section id="ds-surfaces" title={t('ds.surfaces')}>
        <div className="grid gap-4 sm:grid-cols-3">
          <Swatch className="bg-bg" label={t('ds.surfaceBg')} />
          <Swatch className="bg-surface shadow-card" label={t('ds.surfaceCard')} />
          <Swatch className="bg-sunken" label={t('ds.surfaceSunken')} />
        </div>
      </Section>

      <Section id="ds-contrast" title={t('ds.contrast')}>
        <p className="text-muted">{t('ds.contrastIntro')}</p>
        <ContrastTable />
      </Section>

      <Section id="ds-forms" title={t('ds.forms')}>
        <FormsExample />
      </Section>

      <Section id="ds-buttons" title={t('ds.buttons')}>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => setLastAction(t('ds.btnPrimary'))}>{t('ds.btnPrimary')}</Button>
          <Button variant="secondary" onClick={() => setLastAction(t('ds.btnSecondary'))}>
            {t('ds.btnSecondary')}
          </Button>
          <Button disabled>{t('ds.btnDisabled')}</Button>
        </div>
        <p role="status" className="text-muted">
          {t('ds.lastAction')}: {lastAction ?? t('ds.lastActionNone')}
        </p>
      </Section>

      <Section id="ds-statuses" title={t('ds.statusTitle')}>
        <p className="text-muted">{t('ds.statusNote')}</p>
        <ul className="flex flex-wrap gap-3">
          {STATUSES.map((status) => (
            <li key={status}>
              <StatusBadge status={status} />
            </li>
          ))}
        </ul>
      </Section>

      <Section id="ds-chart" title={t('ds.chart')}>
        <ChartExample />
      </Section>

      <Section id="ds-states" title={t('ds.states')}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-border bg-surface p-6">
            <h3 className="mb-3 font-semibold">{t('ds.stateLoading')}</h3>
            <SkeletonBlock />
          </div>
          <EmptyState />
          <ErrorState onRetry={() => setLastAction(t('states.retry'))} />
          <OfflineState />
        </div>
      </Section>
    </div>
  );
}

/** Token-Showcase: nur im Demo-Modus erreichbar, sonst 404. */
export function DesignSystemPage() {
  const meta = useMeta();
  if (meta.isPending) return <SkeletonBlock lines={5} />;
  if (meta.isError) return <ErrorState headingLevel={1} onRetry={() => void meta.refetch()} />;
  if (!meta.data.demo_mode) return <NotFoundState headingLevel={1} />;
  return <Body />;
}
