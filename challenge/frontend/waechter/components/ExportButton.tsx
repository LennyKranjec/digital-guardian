import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useMe } from '../../../../platform/frontend/src/features/auth/api';
import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { downloadFhirBundle, pushFhir, type FhirBundleType } from '../api/client';
import {
  outcomeOf,
  outcomeOfError,
  transactionFileName,
  type PushOutcome,
} from '../model/fhirPush';

/** Dateiname `<pseudonym>-bundle.json`; nur sichere Zeichen. */
export function bundleFileName(pseudonym: string): string {
  const safe = pseudonym.replace(/[^A-Za-z0-9_-]/g, '_');
  return `${safe || 'patient'}-bundle.json`;
}

type State =
  | { kind: 'idle' }
  | { kind: 'working' }
  | { kind: 'done'; file: string }
  | { kind: 'unavailable' }
  | { kind: 'failed' };

/** Eine Bundle-Variante als Datei laden; Zustand und Statuszeile je Knopf. */
function DownloadButton({
  patientId,
  type,
  fileName,
  label,
  statusId,
}: {
  patientId: string;
  type: FhirBundleType;
  fileName: string;
  label: string;
  statusId: string;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<State>({ kind: 'idle' });

  async function run() {
    if (state.kind === 'working') return;
    setState({ kind: 'working' });
    try {
      const blob = await downloadFhirBundle(patientId, undefined, type);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fileName;
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setState({ kind: 'done', file: fileName });
    } catch (error) {
      setState({
        kind: error instanceof ApiClientError && error.status === 404 ? 'unavailable' : 'failed',
      });
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button variant="secondary" disabled={state.kind === 'working'} onClick={() => void run()}>
        {state.kind === 'working' ? t('waechter.clinic.actions.exportWorking') : label}
      </Button>
      <span role="status" className="text-base text-muted" data-testid={statusId}>
        {state.kind === 'done'
          ? t('waechter.clinic.actions.exportDone', { file: state.file })
          : state.kind === 'unavailable'
            ? t('waechter.clinic.actions.exportUnavailable')
            : state.kind === 'failed'
              ? t('waechter.clinic.actions.exportFailed')
              : ''}
      </span>
    </span>
  );
}

/** Statuszeile des Push; der Server liefert Zahlen und Kurztexte, die Oberfläche bewertet nichts. */
function pushText(
  outcome: PushOutcome,
  t: (key: string, values?: Record<string, unknown>) => string,
) {
  switch (outcome.kind) {
    case 'sent':
      return t('waechter.clinic.actions.pushSent', {
        entries: outcome.entries,
        created: outcome.created,
        updated: outcome.updated,
      });
    case 'disabled':
      return t('waechter.clinic.actions.pushDisabled');
    case 'failed': {
      const base = t('waechter.clinic.actions.pushFailed');
      const parts = [
        outcome.httpStatus
          ? t('waechter.clinic.actions.pushHttp', { status: outcome.httpStatus })
          : null,
        outcome.error,
      ].filter((part): part is string => !!part);
      return parts.length > 0 ? `${base} ${parts.join(' · ')}` : base;
    }
    default:
      return t(`waechter.clinic.actions.pushErrors.${outcome.kind}`);
  }
}

/** „An FHIR-Server senden“ (nur Administration; der Server prüft die Rolle trotzdem). */
function PushButton({ patientId }: { patientId: string }) {
  const { t } = useTranslation();
  const [working, setWorking] = useState(false);
  const [outcome, setOutcome] = useState<PushOutcome | null>(null);

  async function run() {
    if (working) return;
    setWorking(true);
    setOutcome(null);
    try {
      setOutcome(outcomeOf(await pushFhir(patientId)));
    } catch (error) {
      setOutcome(outcomeOfError(error));
    } finally {
      setWorking(false);
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button variant="secondary" disabled={working} onClick={() => void run()}>
        {working ? t('waechter.clinic.actions.pushWorking') : t('waechter.clinic.actions.pushFhir')}
      </Button>
      <span
        role="status"
        className="min-w-0 break-words text-base text-muted"
        data-testid="push-status"
        data-outcome={outcome?.kind ?? 'idle'}
      >
        {outcome ? pushText(outcome, t) : ''}
      </span>
    </span>
  );
}

/**
 * FHIR-R4-Bundle (collection) als Datei – der bisherige Export-Knopf der Aktionsleiste und des Berichts.
 * Fehlt die Route im Backend (404), steht „Export noch nicht verfügbar“.
 */
export function ExportButton({ patientId, pseudonym }: { patientId: string; pseudonym: string }) {
  const { t } = useTranslation();
  return (
    <DownloadButton
      patientId={patientId}
      type="collection"
      fileName={bundleFileName(pseudonym)}
      label={t('waechter.clinic.actions.exportFhir')}
      statusId="export-status"
    />
  );
}

/**
 * Weitere FHIR-Aktionen (v2.6): Transaction-Bundle als Datei (alle Klinikrollen) und „An FHIR-Server
 * senden“ (nur Administration; der Server prüft die Rolle trotzdem). Der Push zeigt gesendet / nicht
 * konfiguriert / fehlgeschlagen / nur synthetische Daten.
 */
export function FhirActions({ patientId, pseudonym }: { patientId: string; pseudonym: string }) {
  const { t } = useTranslation();
  const me = useMe();
  const isAdmin = me.data?.role === 'admin';
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2" data-testid="fhir-actions">
      <DownloadButton
        patientId={patientId}
        type="transaction"
        fileName={transactionFileName(pseudonym)}
        label={t('waechter.clinic.actions.exportTransaction')}
        statusId="export-tx-status"
      />
      {isAdmin ? <PushButton patientId={patientId} /> : null}
    </div>
  );
}
