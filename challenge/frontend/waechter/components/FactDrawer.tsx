import { useId } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import {
  ErrorState,
  ForbiddenState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { useFact } from '../hooks/useCockpit';
import { useDialogFocus } from '../hooks/useDialogFocus';
import { formatAbsolute } from '../model/time';

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '–';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
}

interface FactDrawerProps {
  patientId: string;
  factId: string;
  locale: string;
  onClose: () => void;
}

/**
 * Belegschublade: zeigt zu einer Fakt-ID Datum, Angaben und Quelle (GET facts). Modal mit
 * Fokusfalle, Esc und Schließen-Knopf; beim Schließen kehrt der Fokus zum auslösenden Chip zurück.
 */
export function FactDrawer({ patientId, factId, locale, onClose }: FactDrawerProps) {
  const { t } = useTranslation();
  const query = useFact(patientId, factId);
  const titleId = useId();
  const { ref: dialogRef, onKeyDown } = useDialogFocus(onClose);

  const fact = query.data;
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      data-testid="fact-backdrop"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="flex h-full w-full max-w-md flex-col gap-4 overflow-y-auto bg-surface p-4 shadow-card outline-none"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 id={titleId} className="min-w-0 flex-1 break-words text-lg font-semibold">
            {t('waechter.clinic.fact.title')}: {factId}
          </h2>
          <Button variant="secondary" onClick={onClose}>
            {t('waechter.clinic.fact.close')}
          </Button>
        </div>
        {query.isPending ? <SkeletonBlock lines={4} /> : null}
        {query.isError ? (
          query.error instanceof ApiClientError && query.error.status === 404 ? (
            <p role="alert" className="text-base font-semibold">
              {t('waechter.clinic.fact.notFound')}
            </p>
          ) : query.error instanceof ApiClientError && query.error.status === 403 ? (
            <ForbiddenState />
          ) : (
            <ErrorState onRetry={() => void query.refetch()} />
          )
        ) : null}
        {fact ? (
          <div className="space-y-3" data-testid="fact-content">
            <p className="break-words text-base font-semibold">{fact.label}</p>
            <dl className="m-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-base">
              <dt className="text-muted">{t('waechter.clinic.fact.at')}</dt>
              <dd className="m-0">
                <time dateTime={fact.at}>{formatAbsolute(fact.at, locale)}</time>
              </dd>
              <dt className="text-muted">{t('waechter.clinic.fact.source')}</dt>
              <dd className="m-0 break-words">
                {t(`waechter.clinic.fact.kind.${fact.kind}`)} ({fact.fact_id})
              </dd>
              {Object.entries(fact.data).map(([key, value]) => (
                <FactField key={key} name={key} value={displayValue(value)} />
              ))}
            </dl>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FactField({ name, value }: { name: string; value: string }) {
  const { t } = useTranslation();
  return (
    <>
      <dt className="text-muted">
        {t(`waechter.clinic.fact.fields.${name}`, { defaultValue: name })}
      </dt>
      <dd className="m-0 break-words">{value}</dd>
    </>
  );
}
