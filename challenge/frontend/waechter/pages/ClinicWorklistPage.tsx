import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { WorklistCards, WorklistTable } from '../components/WorklistView';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { useServerNow } from '../hooks/useServerNow';
import { useWorklist } from '../hooks/useWorklist';

/** Mindestbreite der Tabellenansicht; darunter Karten (375-px-Handy). */
export const TABLE_MEDIA_QUERY = '(min-width: 768px)';

/** Arbeitsliste der Ärztin: alle Patientinnen mit Ampel, Reihenfolge vom Server. */
export function ClinicWorklistPage() {
  const { t } = useTranslation();
  const query = useWorklist();
  const wide = useMediaQuery(TABLE_MEDIA_QUERY);
  const now = useServerNow();

  return (
    <section aria-labelledby="clinic-title" className="space-y-6">
      <div className="space-y-2">
        <h1 id="clinic-title" className="text-3xl font-bold leading-tight">
          {t('waechter.clinic.title')}
        </h1>
        <p className="text-base text-muted">{t('waechter.clinic.intro')}</p>
        <div className="flex flex-wrap gap-3">
          {/* Route ist serverseitig und per RequireRole auf clinician/admin beschränkt */}
          <LinkButton to="/clinic/patients/new" variant="primary" data-testid="enroll-link">
            {t('waechter.enroll.newPatient')}
          </LinkButton>
          <LinkButton to="/clinic/medications" data-testid="medications-link">
            {t('waechter.nav.medications')}
          </LinkButton>
        </div>
      </div>
      {query.isPending ? <SkeletonBlock lines={5} /> : null}
      {query.isError ? (
        query.error instanceof ApiClientError && query.error.status === 403 ? (
          <ForbiddenState />
        ) : (
          <ErrorState onRetry={() => void query.refetch()} />
        )
      ) : null}
      {query.data && query.data.length === 0 ? (
        <EmptyState title={t('waechter.clinic.emptyTitle')} body={t('waechter.clinic.emptyBody')} />
      ) : null}
      {query.data && query.data.length > 0 ? (
        wide ? (
          <WorklistTable rows={query.data} now={now} />
        ) : (
          <WorklistCards rows={query.data} now={now} />
        )
      ) : null}
    </section>
  );
}
