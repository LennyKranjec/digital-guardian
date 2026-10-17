import { useTranslation } from 'react-i18next';

import type { Escalation } from '../api/client';
import { escalationView } from '../model/session';

/**
 * Akut-Hinweis (Ambulanz / 155) zuerst und hervorgehoben (DR-022). Symbol und Text tragen die
 * Aussage, nie nur Farbe. Platzhalter in eckigen Klammern werden nicht angezeigt; ist der Text nur ein
 * Platzhalter, steht bei „akut“ der Klinikwortlaut aus dem Katalog.
 */
export function EscalationNotice({ escalation }: { escalation: Escalation }) {
  const { t } = useTranslation();
  const view = escalationView(escalation);
  const text = view.text !== '' ? view.text : view.acute ? t('waechter.patient.acuteFallback') : '';
  if (text === '' && !view.phone) return null;

  return (
    <div
      data-testid={view.acute ? 'escalation-acute' : 'escalation-general'}
      className={`space-y-2 rounded-lg p-4 ${
        view.acute
          ? 'border-2 border-border-strong bg-status-caution-bg text-status-caution-fg'
          : 'border border-border-strong bg-surface'
      }`}
    >
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        {view.acute ? (
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <path d="M10 2.5l8 14H2z" />
            <path d="M10 8v4" />
            <path d="M10 14.5h.01" />
          </svg>
        ) : null}
        <span>
          {t(
            view.acute
              ? 'waechter.patient.escalationAcute'
              : 'waechter.patient.response.escalationTitle',
          )}
        </span>
      </h2>
      {text !== '' ? <p className="text-base font-semibold">{text}</p> : null}
      {view.phone ? (
        <p className="text-base">
          <a
            href={`tel:${view.phone.replace(/\s+/g, '')}`}
            className="inline-flex min-h-11 items-center font-semibold underline"
          >
            {t('waechter.patient.callClinic', { phone: view.phone })}
          </a>
        </p>
      ) : null}
    </div>
  );
}
