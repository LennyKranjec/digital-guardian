import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import {
  EmptyState,
  ErrorState,
  ForbiddenState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import type { Questionnaire } from '../api/client';
import { PatientTheme } from '../components/PatientTheme';
import { ProgressStatus } from '../components/ProgressStatus';
import { ProCtcaeNotice } from '../components/ProCtcaeNotice';
import { QuestionGroup } from '../components/QuestionGroup';
import { FollowupCards } from '../components/FollowupCards';
import { SubmitConfirmation } from '../components/SubmitConfirmation';
import { useCheckin, useQuestionnaire } from '../hooks/useCheckin';
import { answerKey } from '../model/checkin';

function CheckinForm({ questionnaire }: { questionnaire: Questionnaire }) {
  const { t } = useTranslation();
  const checkin = useCheckin(questionnaire);

  if (checkin.receipt) return <SubmitConfirmation receipt={checkin.receipt} />;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!checkin.isSending) checkin.submit();
  }

  return (
    <div className="space-y-6">
      <FollowupCards />
      <form onSubmit={onSubmit} noValidate className="space-y-6" data-testid="checkin-form">
        <div className="space-y-2">
          {questionnaire.selection_reason ? (
            <p className="text-base" data-testid="selection-reason">
              {questionnaire.selection_reason}
            </p>
          ) : null}
          <p className="text-base text-muted" data-testid="recall-period">
            <span className="font-semibold">{t('waechter.patient.recallLabel')}: </span>
            {questionnaire.recall_period}
          </p>
        </div>
        <ProgressStatus progress={checkin.progress} />
        {questionnaire.items.map((item) => (
          <fieldset
            key={item.symptom_key}
            className="min-w-0 space-y-4 rounded-lg border border-border bg-surface p-4"
          >
            <legend className="px-1 text-lg font-semibold">{item.label}</legend>
            {item.questions.map((question) => {
              const key = answerKey(item.symptom_key, question.attribute);
              return (
                <QuestionGroup
                  key={key}
                  question={question}
                  value={checkin.answers[key]}
                  onChange={(value) => checkin.setAnswer(key, value)}
                />
              );
            })}
          </fieldset>
        ))}
        {checkin.errorKey ? (
          <p role="alert" className="rounded-md border border-danger p-4 text-base font-semibold">
            {t(`waechter.patient.errors.${checkin.errorKey}`)}
          </p>
        ) : null}
        <Button type="submit" disabled={checkin.isSending} className="w-full sm:w-auto">
          {checkin.isSending
            ? t('waechter.patient.sending')
            : checkin.errorKey === 'network'
              ? t('waechter.patient.resend')
              : t('waechter.patient.send')}
        </Button>
      </form>
    </div>
  );
}

/** Check-in der Patientin (Handy, 375 px): Fragebogen laden, ausfüllen, senden, neutral bestätigen. */
export function PatientCheckinPage() {
  const { t } = useTranslation();
  const query = useQuestionnaire();

  return (
    <PatientTheme>
      <section aria-labelledby="checkin-title" className="mx-auto w-full max-w-2xl space-y-6">
        <div className="space-y-2">
          <h1
            id="checkin-title"
            className="text-3xl font-bold leading-tight text-[var(--wp-title)]"
          >
            {t('waechter.patient.title')}
          </h1>
          <p className="text-base text-muted">{t('waechter.patient.intro')}</p>
        </div>
        {query.isPending ? <SkeletonBlock lines={4} /> : null}
        {query.isError ? (
          query.error instanceof ApiClientError && query.error.status === 403 ? (
            <ForbiddenState />
          ) : (
            <ErrorState onRetry={() => void query.refetch()} />
          )
        ) : null}
        {query.data && query.data.items.length === 0 ? (
          <EmptyState
            title={t('waechter.patient.empty.title')}
            body={t('waechter.patient.empty.body')}
          />
        ) : null}
        {query.data && query.data.items.length > 0 ? (
          <CheckinForm key={query.data.questionnaire_id} questionnaire={query.data} />
        ) : null}
        {query.data && query.data.items.length > 0 ? <ProCtcaeNotice /> : null}
      </section>
    </PatientTheme>
  );
}
