import { useId, useState, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import {
  DOCUMENT_ACCEPT,
  downloadDraftBundle,
  type ClinicDocument,
  type DocumentCandidate,
} from '../api/documents';
import { useDecideCandidate, useDocuments, useUploadDocument } from '../hooks/useDocuments';
import { documentErrorKey, fileProblem, valueText } from '../model/documents';

const TYPE_KEY: Record<DocumentCandidate['resource_type'], string> = {
  Condition: 'condition',
  MedicationStatement: 'medication',
  Observation: 'lab',
};

function CandidateRow({
  candidate,
  busy,
  onDecide,
}: {
  candidate: DocumentCandidate;
  busy: boolean;
  onDecide: (decision: 'confirm' | 'discard') => void;
}) {
  const { t } = useTranslation();
  const detail = [valueText(candidate.value, candidate.unit), candidate.date]
    .filter(Boolean)
    .join(' · ');
  return (
    <li
      data-testid="document-candidate"
      data-state={candidate.state}
      className="space-y-2 rounded-md border border-border p-3"
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-base font-semibold">
          {t(`waechter.clinic.documents.types.${TYPE_KEY[candidate.resource_type]}`)}
        </span>
        <code className="break-all text-base">{candidate.code}</code>
        {candidate.resource_type !== 'Condition' ? (
          <span className="text-base">{candidate.display}</span>
        ) : null}
        {detail ? <span className="text-base text-muted">{detail}</span> : null}
      </div>
      <blockquote className="m-0 break-words border-l-4 border-border-strong pl-3 text-base">
        <span className="text-muted">{t('waechter.clinic.documents.quote')}: </span>„
        {candidate.quote}“
      </blockquote>
      {candidate.state === 'draft' ? (
        <div className="flex flex-wrap items-center gap-2">
          <span data-testid="candidate-state" className="text-base font-semibold">
            {t('waechter.clinic.documents.states.draft')}
          </span>
          <Button
            disabled={busy}
            aria-label={t('waechter.clinic.documents.confirmFor', { code: candidate.code })}
            onClick={() => onDecide('confirm')}
          >
            {t('waechter.clinic.documents.confirm')}
          </Button>
          <Button
            variant="secondary"
            disabled={busy}
            aria-label={t('waechter.clinic.documents.discardFor', { code: candidate.code })}
            onClick={() => onDecide('discard')}
          >
            {t('waechter.clinic.documents.discard')}
          </Button>
        </div>
      ) : (
        <p data-testid="candidate-state" className="m-0 text-base font-semibold">
          {t(`waechter.clinic.documents.states.${candidate.state}`)}
        </p>
      )}
    </li>
  );
}

function DraftDownload({ patientId, documentId }: { patientId: string; documentId: string }) {
  const { t } = useTranslation();
  const [state, setState] = useState<'idle' | 'working' | 'done' | 'failed'>('idle');

  async function run() {
    if (state === 'working') return;
    setState('working');
    try {
      const blob = await downloadDraftBundle(patientId, documentId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `dokument-${documentId.slice(0, 8)}-entwurf.json`;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState('done');
    } catch {
      setState('failed');
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button variant="secondary" disabled={state === 'working'} onClick={() => void run()}>
        {t('waechter.clinic.documents.draftBundle')}
      </Button>
      <span role="status" className="text-base text-muted">
        {state === 'done'
          ? t('waechter.clinic.documents.draftBundleDone')
          : state === 'failed'
            ? t('waechter.clinic.documents.draftBundleFailed')
            : ''}
      </span>
    </span>
  );
}

function DocumentCard({
  patientId,
  doc,
  onError,
}: {
  patientId: string;
  doc: ClinicDocument;
  onError: (error: unknown) => void;
}) {
  const { t } = useTranslation();
  const decide = useDecideCandidate(patientId);
  const mode = doc.extractor.mode;
  return (
    <section
      aria-label={doc.filename}
      data-testid="document-card"
      className="space-y-2 rounded-lg border border-border bg-surface p-3"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="m-0 break-all text-base font-semibold">{doc.filename}</h3>
        <span className="text-base text-muted">
          {t('waechter.clinic.documents.counts', {
            draft: doc.counts.draft,
            confirmed: doc.counts.confirmed,
          })}
        </span>
      </div>
      <p data-testid="document-extractor" className="m-0 text-base text-muted">
        {t('waechter.clinic.documents.extractor', {
          extractor: doc.extractor.id,
          mode: t(`waechter.clinic.documents.modes.${mode}`),
        })}
      </p>
      {doc.candidates.length === 0 ? (
        <p className="m-0 text-base">{t('waechter.clinic.documents.noCandidates')}</p>
      ) : (
        <ul className="m-0 list-none space-y-2 p-0">
          {doc.candidates.map((candidate) => (
            <CandidateRow
              key={candidate.candidate_id}
              candidate={candidate}
              busy={decide.isPending}
              onDecide={(decision) =>
                decide.mutate(
                  { documentId: doc.document_id, candidateId: candidate.candidate_id, decision },
                  { onError },
                )
              }
            />
          ))}
        </ul>
      )}
      {doc.rejected.length > 0 ? (
        <details data-testid="document-rejected">
          <summary className="inline-flex min-h-11 cursor-pointer items-center text-base font-semibold">
            {t('waechter.clinic.documents.rejected', { count: doc.counts.rejected })}
          </summary>
          <p className="m-0 text-base text-muted">{t('waechter.clinic.documents.rejectedHint')}</p>
          <ul className="m-0 list-disc space-y-1 pl-6 text-base">
            {doc.rejected.map((item, index) => (
              <li key={`${item.code}-${index}`} className="break-words">
                <code>{item.code || '–'}</code>:{' '}
                {item.reasons
                  .map((reason) =>
                    t(`waechter.clinic.documents.reasons.${reason}`, { defaultValue: reason }),
                  )
                  .join(', ')}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <DraftDownload patientId={patientId} documentId={doc.document_id} />
    </section>
  );
}

/**
 * „Dokumente“ im Cockpit (T-21, Proof of Concept): synthetisches Textdokument hochladen, geprüfte
 * Kandidaten mit wörtlichem Zitat ansehen, je Ressource bestätigen oder verwerfen. Nur Bestätigtes steht
 * im FHIR-Export dieser Patientin. Eingeklappt (wie der FHIR-Bereich), damit der erste Bildschirm
 * unverändert bleibt; die Liste wird erst beim Öffnen geladen.
 */
export function DocumentsPanel({ patientId }: { patientId: string }) {
  const { t } = useTranslation();
  const inputId = useId();
  const [open, setOpen] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const documents = useDocuments(patientId, open);
  const upload = useUploadDocument(patientId);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    const issue = fileProblem(file.name, file.size);
    if (issue) {
      setProblem(issue);
      input.value = '';
      return;
    }
    setProblem(null);
    try {
      const text = await file.text();
      upload.mutate(
        { filename: file.name, text },
        { onError: (error) => setProblem(documentErrorKey(error)) },
      );
    } catch {
      setProblem('generic');
    }
    input.value = '';
  }

  const list = documents.data ?? [];
  return (
    <details
      data-testid="documents-panel"
      className="rounded-lg border border-border bg-surface px-3"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="inline-flex min-h-11 w-full cursor-pointer items-center text-base font-semibold">
        {t('waechter.clinic.documents.title')}
      </summary>
      <div className="space-y-3 pb-3">
        <p className="m-0 text-base text-muted">{t('waechter.clinic.documents.hint')}</p>
        <div className="space-y-1">
          <label htmlFor={inputId} className="block text-base font-semibold">
            {t('waechter.clinic.documents.upload')}
          </label>
          <input
            id={inputId}
            type="file"
            accept={DOCUMENT_ACCEPT}
            disabled={upload.isPending}
            onChange={(event) => void onFile(event)}
            className="block min-h-11 w-full max-w-full text-base"
          />
          <p className="m-0 text-base text-muted">{t('waechter.clinic.documents.formats')}</p>
          <p role="status" data-testid="documents-status" className="m-0 text-base font-semibold">
            {upload.isPending
              ? t('waechter.clinic.documents.uploading')
              : problem
                ? t(`waechter.clinic.documents.errors.${problem}`)
                : ''}
          </p>
        </div>
        {open && documents.isPending ? (
          <p className="m-0 text-base text-muted">{t('waechter.clinic.documents.loading')}</p>
        ) : null}
        {documents.isError ? (
          <p role="alert" className="m-0 text-base font-semibold">
            {t(`waechter.clinic.documents.errors.${documentErrorKey(documents.error)}`)}
          </p>
        ) : null}
        {open && documents.isSuccess && list.length === 0 ? (
          <p data-testid="documents-empty" className="m-0 text-base">
            {t('waechter.clinic.documents.empty')}
          </p>
        ) : null}
        <div className="space-y-3">
          {list.map((doc) => (
            <DocumentCard
              key={doc.document_id}
              patientId={patientId}
              doc={doc}
              onError={(error) => setProblem(documentErrorKey(error))}
            />
          ))}
        </div>
      </div>
    </details>
  );
}
