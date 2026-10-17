import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';

/** Pflichtzustände aus ui.md §2. Texte kommen aus i18n, die Aktion vom Aufrufer. */

export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{t('states.loading')}</span>
      <div className="space-y-3" aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <div key={index} className="rk-skeleton h-5" style={{ width: `${100 - index * 12}%` }} />
        ))}
      </div>
    </div>
  );
}

/**
 * `headingLevel={1}` für Zustände, die die ganze Seite ersetzen (403/404/Fehlerseite): jede Seite hat
 * genau eine `h1` (ui.md v1.2). Eingebettete Zustände bleiben `h2`.
 */
export interface PageLevel {
  headingLevel?: 1 | 2;
}

interface StatePanelProps extends PageLevel {
  title: string;
  body: string;
  action?: ReactNode;
  role?: 'alert' | 'status';
}

function StatePanel({ title, body, action, role, headingLevel = 2 }: StatePanelProps) {
  return (
    <section role={role} className="rounded-lg border border-border bg-surface p-6 shadow-card">
      {headingLevel === 1 ? (
        <h1 className="text-3xl font-bold leading-tight">{title}</h1>
      ) : (
        <h2 className="text-lg font-semibold">{title}</h2>
      )}
      <p className="mt-2 text-muted">{body}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </section>
  );
}

/** Leerzustand; Titel und Text sind überschreibbar (sonst allgemeine Standardtexte). */
export function EmptyState({
  action,
  title,
  body,
}: {
  action?: ReactNode;
  title?: string;
  body?: string;
}) {
  const { t } = useTranslation();
  return (
    <StatePanel
      title={title ?? t('states.emptyTitle')}
      body={body ?? t('states.emptyBody')}
      action={action}
    />
  );
}

export function ErrorState({ onRetry, headingLevel }: { onRetry: () => void } & PageLevel) {
  const { t } = useTranslation();
  return (
    <StatePanel
      role="alert"
      headingLevel={headingLevel}
      title={t('states.errorTitle')}
      body={t('states.errorBody')}
      action={<Button onClick={onRetry}>{t('states.retry')}</Button>}
    />
  );
}

export function OfflineState() {
  const { t } = useTranslation();
  return (
    <StatePanel role="status" title={t('states.offlineTitle')} body={t('states.offlineBody')} />
  );
}

export function ForbiddenState({ action, headingLevel }: { action?: ReactNode } & PageLevel) {
  const { t } = useTranslation();
  return (
    <StatePanel
      headingLevel={headingLevel}
      title={t('states.forbiddenTitle')}
      body={t('states.forbiddenBody')}
      action={action}
    />
  );
}

export function NotFoundState({ action, headingLevel }: { action?: ReactNode } & PageLevel) {
  const { t } = useTranslation();
  return (
    <StatePanel
      headingLevel={headingLevel}
      title={t('states.notFoundTitle')}
      body={t('states.notFoundBody')}
      action={action}
    />
  );
}
