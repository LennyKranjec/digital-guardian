import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';

import type { AdviceBlock, SubmitReceipt } from '../api/client';
import { safeUrl } from '../model/session';
import { EscalationNotice } from './EscalationNotice';
import { FollowupCards } from './FollowupCards';
import { FreeTextForm } from './FreeTextForm';

/** Rady pacientovi: Tipps je Symptom mit Quelle (Wortlaut vom Server, deterministisch, keine KI). */
function AdviceList({ advice }: { advice: readonly AdviceBlock[] }) {
  const { t } = useTranslation();
  const blocks = advice.filter((block) => block.tips.length > 0);
  if (blocks.length === 0) return null;
  return (
    <section aria-labelledby="advice-title" className="space-y-3" data-testid="advice">
      <h2 id="advice-title" className="text-lg font-semibold">
        {t('waechter.patient.advice.title')}
      </h2>
      {blocks.map((block) => (
        <div
          key={block.symptom_key}
          data-testid="advice-block"
          className="space-y-2 rounded-lg border border-border bg-surface p-4"
        >
          <h3 className="text-base font-semibold">{block.label}</h3>
          <ul className="m-0 list-disc space-y-1 pl-6 text-base">
            {block.tips.map((tip) => (
              <li key={tip} className="break-words">
                {tip}
              </li>
            ))}
          </ul>
          {(block.sources ?? []).length > 0 ? (
            <p className="text-base text-muted" data-testid="advice-sources">
              <span className="font-semibold">{t('waechter.patient.advice.source')}: </span>
              {(block.sources ?? []).map((source, index) => {
                const title = source.title ?? source.id ?? '';
                const url = safeUrl(source.url);
                return (
                  <span key={`${source.id ?? title}-${index}`}>
                    {index > 0 ? '; ' : ''}
                    {url ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex min-h-11 items-center break-words underline"
                      >
                        {title}
                      </a>
                    ) : (
                      title
                    )}
                  </span>
                );
              })}
            </p>
          ) : null}
        </div>
      ))}
    </section>
  );
}

/**
 * Abschluss nach dem Senden. Reihenfolge laut Vertrag v1.10: zuerst der Hinweis (bei „akut“ hervorgehoben,
 * auf 375 px ohne Scrollen sichtbar), dann die Tipps je Symptom mit Quelle, zuletzt die neutrale Bestätigung
 * aus `message_key`. Keine Ampel, kein Grad, keine Beruhigung, keine Reaktionszusage (Vertrag §2).
 * Platzhalter in `text`/`ambulance_phone` („[…]“) werden nie angezeigt. Liefert der Server gar keine `escalation`
 * (Backend vor v1.9), steht wie bisher der Hinweis „Text der Klinik folgt“ (nur dann).
 */
export function SubmitConfirmation({ receipt }: { receipt: SubmitReceipt }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLElement>(null);
  const message = t(`waechter.${receipt.message_key}`, {
    defaultValue: t('waechter.patient.response.saved'),
  });
  const hasCounts = receipt.answered != null && receipt.skipped != null;

  // Screenreader und Tastatur beginnen oben beim Abschluss
  useEffect(() => {
    ref.current?.focus({ preventScroll: true });
  }, []);

  return (
    <section
      ref={ref}
      tabIndex={-1}
      role="status"
      aria-labelledby="checkin-saved-title"
      data-testid="checkin-confirmation"
      className="space-y-4 outline-none"
    >
      {receipt.escalation ? <EscalationNotice escalation={receipt.escalation} /> : null}
      <AdviceList advice={receipt.advice ?? []} />
      <div className="space-y-2 rounded-lg border border-border bg-surface p-4 shadow-card">
        <h2 id="checkin-saved-title" className="text-lg font-semibold">
          {t('waechter.patient.response.title')}
        </h2>
        <p className="text-base">{message}</p>
        {hasCounts ? (
          <p className="text-base text-muted">
            {t('waechter.patient.response.counts', {
              answered: receipt.answered,
              skipped: receipt.skipped,
            })}
          </p>
        ) : null}
      </div>
      <FreeTextForm responseId={receipt.response_id} />
      <FollowupCards />
      {receipt.escalation ? null : (
        <div className="rounded-md border border-dashed border-border-strong p-4">
          <h3 className="text-base font-semibold">
            {t('waechter.patient.response.escalationTitle')}
          </h3>
          <p className="text-base" data-testid="escalation-placeholder">
            {t('waechter.patient.response.escalation')}
          </p>
        </div>
      )}
    </section>
  );
}
