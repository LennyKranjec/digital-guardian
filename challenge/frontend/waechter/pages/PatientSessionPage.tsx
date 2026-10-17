import { useTranslation } from 'react-i18next';

import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import {
  ForbiddenState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import type { Due } from '../api/client';
import { ProCtcaeNotice } from '../components/ProCtcaeNotice';
import { SessionCard } from '../components/SessionCard';
import { PatientTheme } from '../components/PatientTheme';
import { SessionProgress } from '../components/SessionProgress';
import { UndoButton } from '../components/UndoButton';
import { FollowupCards } from '../components/FollowupCards';
import { SubmitConfirmation } from '../components/SubmitConfirmation';
import { useServerNow } from '../hooks/useServerNow';
import { useSession } from '../hooks/useSession';
import { dueView } from '../model/session';
import { formatAbsolute, formatRelative } from '../model/time';
import { PatientCheckinPage } from './PatientCheckinPage';

export const FULL_CHECKIN_PATH = '/patient/full';

/** Nächste Fälligkeit (Prager Zeit, relativ zur Serveruhr, nie zur Browseruhr). */
function DueLine({ due }: { due: Due | null | undefined }) {
  const { t, i18n } = useTranslation();
  const now = useServerNow();
  const view = dueView(due);
  if (!view) return null;
  const locale = i18n.resolvedLanguage ?? i18n.language;
  let text: string;
  if (view.overdue) {
    text = t('waechter.patient.session.dueNow');
  } else if (view.at) {
    const relative = now ? formatRelative(view.at, now, locale, { allowFuture: true }) : null;
    const absolute = formatAbsolute(view.at, locale);
    text = t('waechter.patient.session.dueNext', {
      when: relative ? `${relative} (${absolute})` : absolute,
    });
  } else {
    return null;
  }
  return (
    <p className="text-base text-muted" data-testid="session-due">
      {text}
    </p>
  );
}

function errorKeyOf(action: string): string {
  return ['network', 'forbidden', 'invalid'].includes(action) ? action : 'generic';
}

/**
 * Adaptiver Check-in der Patientin (Handy, 375 px): eine Frage pro Karte, der Server bestimmt Folgefrage
 * oder Stopp; danach Hinweis, Tipps und neutrale Bestätigung. Gibt es die Sitzungs-API (noch) nicht,
 * erscheint stattdessen der vollständige Fragebogen. Der Vollfragebogen bleibt unter `/patient/full`
 * (Rückfall, Papier/Telefon).
 */
export function PatientSessionPage() {
  const { t } = useTranslation();
  const session = useSession();
  const { state } = session;

  if (state.phase === 'fallback') return <PatientCheckinPage />;

  const done = state.phase === 'done';
  const shown = state.phase === 'loading' ? null : state.step;
  // Karte bleibt bei einem Sendefehler stehen (Auswahl bleibt, Fehlermeldung darin)
  const cardStep = (state.phase === 'ask' || state.phase === 'error') && shown?.next ? shown : null;

  // Zurück-Pfeil nur bei offener Sitzung mit mindestens einer gegebenen Antwort
  const canUndo = cardStep !== null && cardStep.progress.asked >= 1;

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
          {done ? null : (
            <p className="text-base text-muted">{t('waechter.patient.session.intro')}</p>
          )}
          {shown?.selection_reason && !done ? (
            <p className="text-base" data-testid="selection-reason">
              {shown.selection_reason}
            </p>
          ) : null}
          {done ? null : <DueLine due={shown?.due} />}
        </div>

        {done ? null : <FollowupCards />}

        {state.phase === 'loading' ? <SkeletonBlock lines={4} /> : null}

        {cardStep ? (
          <>
            {cardStep.next ? (
              <SessionCard
                key={`${cardStep.next.symptom_key}:${cardStep.next.attribute}:${cardStep.progress.asked}`}
                question={cardStep.next}
                isSending={session.isSending}
                errorKey={state.phase === 'error' ? errorKeyOf(state.action) : null}
                progress={<SessionProgress progress={cardStep.progress} />}
                back={
                  canUndo ? (
                    <UndoButton onClick={session.undo} disabled={session.isSending} />
                  ) : null
                }
                onSubmit={(value) =>
                  cardStep.next
                    ? session.answer({
                        symptom_key: cardStep.next.symptom_key,
                        attribute: cardStep.next.attribute,
                        value,
                      })
                    : undefined
                }
              />
            ) : null}
          </>
        ) : null}

        {state.phase === 'error' && !cardStep ? (
          state.action === 'forbidden' ? (
            <ForbiddenState />
          ) : (
            <div
              role="alert"
              data-testid="session-error"
              className="space-y-3 rounded-lg border border-danger bg-surface p-4"
            >
              <p className="text-base font-semibold">
                {t(`waechter.patient.errors.${errorKeyOf(state.action)}`)}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={session.reload}>{t('waechter.patient.session.retry')}</Button>
                <LinkButton to={FULL_CHECKIN_PATH}>
                  {t('waechter.patient.session.fullForm')}
                </LinkButton>
              </div>
            </div>
          )
        ) : null}

        {state.phase === 'done' ? (
          <>
            {state.step.receipt ? (
              <SubmitConfirmation receipt={state.step.receipt} />
            ) : (
              <p role="status" className="text-base">
                {t('waechter.patient.response.saved')}
              </p>
            )}
            <DueLine due={state.step.due} />
            <Button variant="secondary" onClick={session.newCheckin} data-testid="new-checkin">
              {t('waechter.patient.session.newCheckin')}
            </Button>
          </>
        ) : null}

        {cardStep ? <ProCtcaeNotice /> : null}
      </section>
    </PatientTheme>
  );
}
