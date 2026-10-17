import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  ErrorState,
  ForbiddenState,
  NotFoundState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { MedicationCard } from '../components/MedicationCard';
import { useLang } from '../hooks/useLang';
import { useMedication } from '../hooks/useMedications';
import { useConfig } from '../hooks/useTimeline';
import { displayName } from '../model/medications';
import { MedicationNote } from './MedicationsPage';

/** Detailansicht eines Arzneimittels (`/clinic/medications/:id`); unbekannte Kennung ⇒ 404 vom Server. */
export function MedicationDetailPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const { medicationId = '' } = useParams();
  const config = useConfig();
  const query = useMedication(medicationId);
  const status = query.error instanceof ApiClientError ? query.error.status : null;
  const back = (
    <LinkButton to="/clinic/medications">{t('waechter.clinic.medications.back')}</LinkButton>
  );

  return (
    <section aria-labelledby="medication-title" className="mx-auto w-full max-w-4xl space-y-4">
      <div className="space-y-2">
        {back}
        <h1 id="medication-title" className="text-3xl font-bold leading-tight">
          {query.data ? displayName(query.data) : t('waechter.clinic.medications.detailTitle')}
        </h1>
      </div>
      {query.isPending ? <SkeletonBlock lines={4} /> : null}
      {query.isError ? (
        status === 404 ? (
          <NotFoundState action={back} headingLevel={2} />
        ) : status === 403 ? (
          <ForbiddenState headingLevel={2} />
        ) : (
          <ErrorState onRetry={() => void query.refetch()} headingLevel={2} />
        )
      ) : null}
      {query.data ? (
        <MedicationCard
          medication={{ ...query.data, match: null }}
          config={config.data}
          lang={lang}
          detailLink={false}
        />
      ) : null}
      <MedicationNote />
    </section>
  );
}
