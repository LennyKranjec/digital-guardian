import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import { ErrorState, SkeletonBlock } from '../../../../platform/frontend/src/shared/ui/StateViews';
import {
  enrollPatient,
  LANGS,
  localized,
  type EnrollmentCreate,
  type EnrollmentReceipt,
} from '../api/client';
import { uploadDocument } from '../api/documents';
import { useLang } from '../hooks/useLang';
import { fileProblem } from '../model/documents';
import { useConfig } from '../hooks/useTimeline';
import {
  parseEnrollment,
  serverFieldErrors,
  type EnrollErrors,
  type EnrollField,
  type EnrollmentForm,
} from '../model/enrollment';

const INPUT =
  'min-h-11 w-full max-w-full rounded-md border border-border-strong bg-surface px-3 text-base text-ink';

/** Heutiges Datum in Europe/Prague als `YYYY-MM-DD` (Vorgabe für den Zyklusstart). */
export function pragueToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Prague' }).format(now);
}

function newRequestId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** T-34: neue synthetische Patientin mit Therapie anlegen (nur Klinik-Datensatz, kein Konto). */
export function EnrollPatientPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const config = useConfig();
  const [requestId] = useState(newRequestId);
  const [form, setForm] = useState<EnrollmentForm>({
    diagnosis_code: '',
    regimen_id: '',
    cycle_start: pragueToday(),
    language: lang,
  });
  const [errors, setErrors] = useState<EnrollErrors>({});
  // T-37: optionale Dokumente (Text/Markdown/CSV) – nach dem Anlegen über denselben Upload wie im Cockpit
  const [files, setFiles] = useState<File[]>([]);
  const [fileIssue, setFileIssue] = useState<string | null>(null);
  const mutation = useMutation<EnrollmentReceipt, Error, EnrollmentCreate>({
    mutationFn: enrollPatient,
    onSuccess: async (receipt) => {
      for (const file of files) {
        try {
          await uploadDocument(receipt.patient_id, file.name, await file.text());
        } catch {
          // Patientin ist angelegt; ein fehlgeschlagenes Dokument lässt sich im Cockpit erneut hochladen.
        }
      }
      await queryClient.invalidateQueries({ queryKey: ['waechter'] });
      void navigate(`/clinic/patients/${encodeURIComponent(receipt.patient_id)}`);
    },
    onError: (error) => {
      if (error instanceof ApiClientError && error.status === 422) {
        setErrors(serverFieldErrors(error.fieldErrors));
      }
    },
  });

  const update = (field: EnrollField, value: string) =>
    setForm((previous) => ({ ...previous, [field]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parseEnrollment(form);
    if (!parsed.ok) {
      setErrors(parsed.errors);
      return;
    }
    setErrors({});
    mutation.mutate({ ...parsed.body, client_request_id: requestId });
  };

  const errorText = (field: EnrollField) => {
    const key = errors[field];
    return key ? (
      <p id={`${field}-error`} role="alert" className="text-base font-semibold text-danger">
        {t(`waechter.enroll.errors.${key}`)}
      </p>
    ) : null;
  };
  const describedBy = (field: EnrollField, hint?: string) =>
    [hint, errors[field] ? `${field}-error` : undefined].filter(Boolean).join(' ') || undefined;

  const regimens = config.data?.regimens.regimens ?? [];
  const generalError =
    mutation.isError &&
    !(mutation.error instanceof ApiClientError && mutation.error.status === 422);

  return (
    <section aria-labelledby="enroll-title" className="min-w-0 max-w-xl space-y-6">
      <div className="space-y-2">
        <h1 id="enroll-title" className="text-3xl font-bold leading-tight">
          {t('waechter.enroll.title')}
        </h1>
        <p className="text-base text-muted">{t('waechter.enroll.intro')}</p>
      </div>
      {config.isPending ? <SkeletonBlock lines={4} /> : null}
      {config.isError ? <ErrorState onRetry={() => void config.refetch()} /> : null}
      {config.data ? (
        <form noValidate onSubmit={submit} className="space-y-5" data-testid="enroll-form">
          <div className="space-y-1">
            <label htmlFor="enroll-diagnosis" className="block font-semibold">
              {t('waechter.enroll.diagnosis')}
            </label>
            <p id="enroll-diagnosis-hint" className="text-base text-muted">
              {t('waechter.enroll.diagnosisHint')}
            </p>
            <input
              id="enroll-diagnosis"
              name="diagnosis_code"
              type="text"
              autoComplete="off"
              maxLength={16}
              className={INPUT}
              value={form.diagnosis_code}
              aria-invalid={errors.diagnosis_code ? true : undefined}
              aria-describedby={describedBy('diagnosis_code', 'enroll-diagnosis-hint')}
              onChange={(event) => update('diagnosis_code', event.target.value)}
            />
            {errorText('diagnosis_code')}
          </div>
          <div className="space-y-1">
            <label htmlFor="enroll-regimen" className="block font-semibold">
              {t('waechter.enroll.regimen')}
            </label>
            <select
              id="enroll-regimen"
              name="regimen_id"
              required
              className={INPUT}
              value={form.regimen_id}
              aria-invalid={errors.regimen_id ? true : undefined}
              aria-describedby={describedBy('regimen_id')}
              onChange={(event) => update('regimen_id', event.target.value)}
            >
              <option value="">{t('waechter.enroll.regimenPlaceholder')}</option>
              {regimens.map((regimen) => (
                <option key={regimen.id} value={regimen.id}>
                  {localized(regimen.label, lang)}
                </option>
              ))}
            </select>
            {errorText('regimen_id')}
          </div>
          <div className="space-y-1">
            <label htmlFor="enroll-cycle-start" className="block font-semibold">
              {t('waechter.enroll.cycleStart')}
            </label>
            <input
              id="enroll-cycle-start"
              name="cycle_start"
              type="date"
              required
              className={INPUT}
              value={form.cycle_start}
              aria-invalid={errors.cycle_start ? true : undefined}
              aria-describedby={describedBy('cycle_start')}
              onChange={(event) => update('cycle_start', event.target.value)}
            />
            {errorText('cycle_start')}
          </div>
          <div className="space-y-1">
            <label htmlFor="enroll-language" className="block font-semibold">
              {t('waechter.enroll.language')}
            </label>
            <select
              id="enroll-language"
              name="language"
              className={INPUT}
              value={form.language}
              aria-describedby={describedBy('language')}
              onChange={(event) => update('language', event.target.value)}
            >
              {LANGS.map((code) => (
                <option key={code} value={code}>
                  {t(`waechter.enroll.languages.${code}`)}
                </option>
              ))}
            </select>
            {errorText('language')}
          </div>
          <div className="space-y-1">
            <label htmlFor="enroll-documents" className="block text-base font-semibold">
              {t('waechter.enroll.documents')}
            </label>
            <p id="enroll-documents-hint" className="m-0 text-base text-muted">
              {t('waechter.clinic.documents.formats')}
            </p>
            <input
              id="enroll-documents"
              data-testid="enroll-documents"
              type="file"
              multiple
              accept=".txt,.md,.csv,text/plain,text/markdown,text/csv"
              aria-describedby="enroll-documents-hint"
              className="block min-h-11 w-full text-base"
              onChange={(event) => {
                const chosen = Array.from(event.currentTarget.files ?? []);
                const problem = chosen.map((f) => fileProblem(f.name, f.size)).find(Boolean);
                setFileIssue(problem ?? null);
                setFiles(chosen.filter((f) => !fileProblem(f.name, f.size)));
              }}
            />
            {fileIssue ? (
              <p role="alert" className="m-0 text-base font-semibold text-danger">
                {t(`waechter.clinic.documents.errors.${fileIssue}`)}
              </p>
            ) : null}
            {files.length > 0 ? (
              <p className="m-0 text-base" data-testid="enroll-documents-list">
                {files.map((f) => f.name).join(', ')}
              </p>
            ) : null}
          </div>
          <p className="text-base text-muted">{t('waechter.enroll.syntheticNote')}</p>
          {generalError ? (
            <p role="alert" className="text-base font-semibold text-danger">
              {t('waechter.enroll.errors.general')}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={mutation.isPending} data-testid="enroll-submit">
              {mutation.isPending ? t('waechter.enroll.saving') : t('waechter.enroll.submit')}
            </Button>
            <LinkButton to="/clinic">{t('waechter.enroll.cancel')}</LinkButton>
          </div>
        </form>
      ) : null}
    </section>
  );
}
