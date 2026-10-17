import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { DECISIONS, NOTE_MAX_LENGTH, type Alert, type Decision } from '../api/client';
import { ackErrorKey, useAcknowledge, useInvalidateClinicData } from '../hooks/useAcknowledge';
import { useDialogFocus } from '../hooks/useDialogFocus';

interface AcknowledgeDialogProps {
  alert: Alert;
  onClose: () => void;
  /** nach erfolgreichem Quittieren (mit der quittierten Meldung laut Server) */
  onDone: (acknowledged: Alert, decision: Decision) => void;
}

/**
 * Quittieren mit Entscheidung (Audit): Radiogruppe mit vier neutralen Entscheidungen, optionale
 * Notiz bis 500 Zeichen mit Zähler. 409 (bereits quittiert) wird erklärt und bietet „Neu laden“ an.
 * Kein Text zur Therapie – die Ärztin hält nur fest, wie sie mit der Meldung umgeht.
 */
export function AcknowledgeDialog({ alert, onClose, onDone }: AcknowledgeDialogProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const noteId = useId();
  const counterId = useId();
  const name = useId();
  const { ref, onKeyDown } = useDialogFocus(onClose);
  const mutation = useAcknowledge(alert.alert_id);
  const reload = useInvalidateClinicData();
  const [decision, setDecision] = useState<Decision | null>(null);
  const [note, setNote] = useState('');
  const [missingDecision, setMissingDecision] = useState(false);

  const errorKey = mutation.isError ? ackErrorKey(mutation.error) : null;
  const conflict = errorKey === 'conflict';

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending) return;
    if (!decision) {
      setMissingDecision(true);
      return;
    }
    setMissingDecision(false);
    const trimmed = note.trim();
    mutation.mutate(
      { decision, ...(trimmed ? { note: trimmed } : {}) },
      { onSuccess: (acknowledged) => onDone(acknowledged, decision) },
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      data-testid="ack-backdrop"
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        className="max-h-full w-full max-w-lg space-y-4 overflow-y-auto rounded-t-lg bg-surface p-4 shadow-card outline-none sm:rounded-lg"
      >
        <h2 id={titleId} className="text-lg font-semibold">
          {t('waechter.clinic.ack.title')}
        </h2>
        <p className="break-words text-base font-semibold" data-testid="ack-alert-headline">
          {alert.headline ?? alert.rule_id}
        </p>
        <p className="text-base text-muted">{t('waechter.clinic.ack.intro')}</p>

        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <fieldset className="m-0 min-w-0 space-y-2 border-0 p-0">
            <legend className="text-base font-semibold">
              {t('waechter.clinic.ack.decisionLegend')}
            </legend>
            <div className="grid grid-cols-1 gap-2">
              {DECISIONS.map((option) => (
                <label
                  key={option}
                  className="flex min-h-11 min-w-0 cursor-pointer items-center gap-3 rounded-md border border-border-strong bg-surface px-3 py-2 text-base has-[:checked]:border-accent has-[:checked]:bg-accent-subtle has-[:checked]:ring-2 has-[:checked]:ring-accent has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2"
                >
                  <input
                    type="radio"
                    name={name}
                    className="size-5 shrink-0"
                    checked={decision === option}
                    onChange={() => {
                      setDecision(option);
                      setMissingDecision(false);
                    }}
                  />
                  <span className="min-w-0 break-words">
                    {t(`waechter.clinic.ack.decisions.${option}`)}
                  </span>
                </label>
              ))}
            </div>
            {missingDecision ? (
              <p role="alert" className="text-base font-semibold">
                {t('waechter.clinic.ack.needDecision')}
              </p>
            ) : null}
          </fieldset>

          <div className="space-y-1">
            <label htmlFor={noteId} className="block text-base font-semibold">
              {t('waechter.clinic.ack.note')}
            </label>
            <textarea
              id={noteId}
              value={note}
              maxLength={NOTE_MAX_LENGTH}
              rows={3}
              aria-describedby={counterId}
              onChange={(event) => setNote(event.target.value)}
              className="min-h-11 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink"
            />
            <p
              id={counterId}
              className="text-right text-base text-muted"
              data-testid="note-counter"
            >
              {t('waechter.clinic.ack.counter', { count: note.length, max: NOTE_MAX_LENGTH })}
            </p>
          </div>

          {errorKey ? (
            <p role="alert" className="rounded-md border border-danger p-3 text-base font-semibold">
              {t(`waechter.clinic.ack.errors.${errorKey}`)}
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              {t('waechter.clinic.ack.cancel')}
            </Button>
            {conflict ? (
              <Button
                onClick={() => {
                  void reload();
                  onClose();
                }}
              >
                {t('waechter.clinic.ack.reload')}
              </Button>
            ) : (
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending
                  ? t('waechter.clinic.ack.sending')
                  : errorKey === 'network'
                    ? t('waechter.clinic.ack.retry')
                    : t('waechter.clinic.ack.confirm')}
              </Button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
